"""Reproductor integrado (motor VLC): lista de reproducción, velocidad, audio, subtítulos y pantalla completa."""
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, ttk

from . import paths
from .theme import FONT_B, GREEN_DARK, button, choice

_vlc = None


def _load_vlc():
    """Carga python-vlc. Si hay un VLC incluido junto al programa (carpeta 'vlc') lo usa."""
    global _vlc
    if _vlc is not None:
        return _vlc or None
    d = os.path.join(paths.app_dir(), "vlc")
    lib = os.path.join(d, "libvlc.dll")
    if os.name == "nt" and os.path.isfile(lib):
        os.environ["PYTHON_VLC_LIB_PATH"] = lib
        os.environ["PYTHON_VLC_MODULE_PATH"] = os.path.join(d, "plugins")
        os.environ["VLC_PLUGIN_PATH"] = os.path.join(d, "plugins")
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(d)
        except Exception:
            pass
    try:
        import vlc  # noqa: WPS433
        _vlc = vlc
    except Exception:
        _vlc = False
    return _vlc or None


def vlc_available() -> bool:
    return _load_vlc() is not None


def fmt_time(ms):
    s = max(int(ms or 0), 0) // 1000
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _decode(n):
    return n.decode("utf-8", "ignore") if isinstance(n, bytes) else str(n)


class PlayerWindow(tk.Toplevel):
    SPEEDS = (0.5, 1.0, 1.5, 2.0)

    def __init__(self, master, cfg, plist, index=0):
        super().__init__(master)
        vlc = _load_vlc()
        self.vlc = vlc
        self.cfg = cfg
        self.paths = list(plist)
        self.index = max(0, min(index, len(self.paths) - 1))
        self.fs = False
        self.dragging = False
        self.ended = False
        self.controls_visible = True
        self.last_mouse = (0, 0)
        self.last_move = time.time()
        self.closed = False

        self.title("KonMusic")
        self.geometry("1000x640")
        self.minsize(680, 420)
        self.configure(bg="black")
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._build_controls()
        self.video = tk.Frame(self, bg="black")
        self.video.pack(fill="both", expand=True)

        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        try:
            self.player.video_set_mouse_input(False)
            self.player.video_set_key_input(False)
        except Exception:
            pass
        self.update_idletasks()
        self._embed()
        self._bind_keys()
        self._load(self.index)
        self.after(300, self._tick)
        self.focus_force()

    # -- interfaz ----------------------------------------------------------
    def _build_controls(self):
        self.controls = tk.Frame(self, bg=GREEN_DARK)
        self.controls.pack(side="bottom", fill="x")

        seek = tk.Frame(self.controls, bg=GREEN_DARK)
        seek.pack(fill="x", padx=12, pady=(10, 2))
        self.time_lbl = tk.Label(seek, text="0:00 / 0:00", bg=GREEN_DARK, fg="white", font=FONT_B, width=13)
        self.time_lbl.pack(side="left")
        self.scale = ttk.Scale(seek, from_=0, to=1000, orient="horizontal")
        self.scale.pack(side="left", fill="x", expand=True, padx=8)
        self.scale.bind("<ButtonPress-1>", lambda e: setattr(self, "dragging", True))
        self.scale.bind("<ButtonRelease-1>", self._seek_release)
        self.count_lbl = tk.Label(seek, text="", bg=GREEN_DARK, fg="white", font=FONT_B)
        self.count_lbl.pack(side="right")

        row = tk.Frame(self.controls, bg=GREEN_DARK)
        row.pack(pady=4)
        button(row, "⏮ Anterior", self.prev, "dark").pack(side="left", padx=4)
        button(row, "⏪ 10 s", lambda: self.skip(-10000), "dark").pack(side="left", padx=4)
        self.btn_play = button(row, "⏸ Pausa", self.toggle, "dark", width=12)
        self.btn_play.pack(side="left", padx=4)
        button(row, "10 s ⏩", lambda: self.skip(10000), "dark").pack(side="left", padx=4)
        button(row, "Siguiente ⏭", self.next, "dark").pack(side="left", padx=4)

        row2 = tk.Frame(self.controls, bg=GREEN_DARK)
        row2.pack(pady=(2, 10))
        self.speed_var = tk.DoubleVar(value=1.0)
        for s in self.SPEEDS:
            choice(row2, f"{s:g}x", self.speed_var, s, lambda s=s: self.set_speed(s), dark=True).pack(side="left", padx=3)
        button(row2, "⛶ Pantalla completa", self.toggle_fullscreen, "dark").pack(side="left", padx=(14, 3))
        self.btn_audio = button(row2, "🔊 Audio", self.audio_menu, "dark")
        self.btn_audio.pack(side="left", padx=3)
        self.btn_sub = button(row2, "💬 Subtítulos", self.sub_menu, "dark")
        self.btn_sub.pack(side="left", padx=3)
        tk.Label(row2, text="Vol", bg=GREEN_DARK, fg="white", font=FONT_B).pack(side="left", padx=(14, 2))
        self.vol = ttk.Scale(row2, from_=0, to=100, orient="horizontal", length=110, command=self._on_vol)
        self.vol.set(80)
        self.vol.pack(side="left")

    def _embed(self):
        wid = self.video.winfo_id()
        if os.name == "nt":
            self.player.set_hwnd(wid)
        elif sys.platform == "darwin":
            self.player.set_nsobject(wid)
        else:
            self.player.set_xwindow(wid)

    def _bind_keys(self):
        b = self.bind
        b("<space>", lambda e: self.toggle())
        b("<Left>", lambda e: self.skip(-10000))
        b("<Right>", lambda e: self.skip(10000))
        b("<Up>", lambda e: self._vol_delta(5))
        b("<Down>", lambda e: self._vol_delta(-5))
        b("<f>", lambda e: self.toggle_fullscreen())
        b("<F11>", lambda e: self.toggle_fullscreen())
        b("<Escape>", lambda e: self.toggle_fullscreen() if self.fs else None)
        b("<n>", lambda e: self.next())
        b("<p>", lambda e: self.prev())
        self.video.bind("<Double-Button-1>", lambda e: self.toggle_fullscreen())
        self.video.bind("<Button-1>", lambda e: self.toggle())

    # -- reproducción --------------------------------------------------------
    def _load(self, i):
        path = self.paths[i]
        self.index = i
        media = self.instance.media_new(path)
        self.player.set_media(media)
        self.player.play()
        self.ended = False
        self.title(f"{os.path.splitext(os.path.basename(path))[0]} — KonMusic")
        self.count_lbl.config(text=f"{i + 1} / {len(self.paths)}" if len(self.paths) > 1 else "")
        self.set_speed(self.speed_var.get())
        pos = self.cfg.get_pos(path)
        if pos > 5000:
            self.after(900, lambda: self.player.set_time(pos))

    def save_pos(self):
        try:
            path = self.paths[self.index]
            t, n = self.player.get_time(), self.player.get_length()
            self.cfg.set_pos(path, 0 if (n > 0 and n - t < 5000) else t)
        except Exception:
            pass

    def toggle(self):
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()

    def skip(self, ms):
        self.player.set_time(max(0, self.player.get_time() + ms))

    def next(self):
        if self.index < len(self.paths) - 1:
            self.save_pos()
            self._load(self.index + 1)

    def prev(self):
        if self.player.get_time() > 3000 or self.index == 0:
            self.player.set_time(0)
        else:
            self.save_pos()
            self._load(self.index - 1)

    def set_speed(self, s):
        self.speed_var.set(s)
        try:
            self.player.set_rate(s)
        except Exception:
            pass

    def _on_vol(self, v):
        try:
            self.player.audio_set_volume(int(float(v)))
        except Exception:
            pass

    def _vol_delta(self, d):
        self.vol.set(min(100, max(0, float(self.vol.get()) + d)))

    def _seek_release(self, _e):
        n = self.player.get_length()
        if n > 0:
            self.player.set_time(int(float(self.scale.get()) / 1000.0 * n))
        self.dragging = False

    # -- menús ---------------------------------------------------------------
    def audio_menu(self):
        m = tk.Menu(self, tearoff=0)
        tracks = self.player.audio_get_track_description() or []
        if not tracks:
            m.add_command(label="Sin pistas de audio", state="disabled")
        for tid, name in tracks:
            m.add_command(label=_decode(name), command=lambda t=tid: self.player.audio_set_track(t))
        m.tk_popup(self.btn_audio.winfo_rootx(), self.btn_audio.winfo_rooty() - 10)

    def sub_menu(self):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Cargar archivo de subtítulos...", command=self.load_sub)
        m.add_command(label="Desactivar", command=lambda: self.player.video_set_spu(-1))
        tracks = self.player.video_get_spu_description() or []
        if tracks:
            m.add_separator()
        for tid, name in tracks:
            if tid >= 0:
                m.add_command(label=_decode(name), command=lambda t=tid: self.player.video_set_spu(t))
        m.tk_popup(self.btn_sub.winfo_rootx(), self.btn_sub.winfo_rooty() - 10)

    def load_sub(self):
        f = filedialog.askopenfilename(
            parent=self, title="Subtítulos",
            filetypes=[("Subtítulos", "*.srt *.ass *.ssa *.vtt *.sub"), ("Todos", "*.*")])
        if f:
            self.player.video_set_subtitle_file(f)

    # -- pantalla completa -----------------------------------------------------
    def toggle_fullscreen(self):
        self.fs = not self.fs
        self.attributes("-fullscreen", self.fs)
        if not self.fs:
            self._show_controls(True)
            self.video.config(cursor="")

    def _show_controls(self, show):
        if show and not self.controls_visible:
            self.controls.pack(side="bottom", fill="x", before=self.video)
            self.controls_visible = True
            self.video.config(cursor="")
        elif not show and self.controls_visible:
            self.controls.pack_forget()
            self.controls_visible = False
            self.video.config(cursor="none")

    def _tick(self):
        if self.closed or not self.winfo_exists():
            return
        try:
            n, t = self.player.get_length(), self.player.get_time()
            if n > 0 and not self.dragging:
                self.scale.set(t / n * 1000.0)
            self.time_lbl.config(text=f"{fmt_time(t)} / {fmt_time(n)}")
            self.btn_play.config(text="⏸ Pausa" if self.player.is_playing() else "▶ Reproducir")
            if self.player.get_state() == self.vlc.State.Ended and not self.ended:
                self.ended = True
                if self.index < len(self.paths) - 1:
                    self.next()
            pos = self.winfo_pointerxy()
            if pos != self.last_mouse:
                self.last_mouse = pos
                self.last_move = time.time()
                self._show_controls(True)
            elif self.fs and time.time() - self.last_move > 3:
                self._show_controls(False)
        except Exception:
            pass
        self.after(300, self._tick)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.save_pos()
        self.cfg.save()
        try:
            self.player.stop()
            self.player.release()
            self.instance.release()
        except Exception:
            pass
        self.destroy()
