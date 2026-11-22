"""Ventana principal de KonMusic: Biblioteca, Descargar y Listas."""
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from . import downloader, media, paths
from .config import Config
from .theme import (BG, CARD, FONT, FONT_B, FONT_BIG, GREEN, MUTED, SOFT, TEXT,
                    GradientBar, ScrollFrame, button, choice)
from .thumbs import Thumbs

PAGE = 60
RESOLUTIONS = [(144, "144p"), (240, "240p"), (360, "360p"), (480, "480p"), (720, "720p"),
               (1080, "1080p"), (1440, "2K"), (2160, "4K UHD")]
AUDIO_FORMATS = ["mp3", "m4a", "opus", "ogg", "wav", "flac"]
LOSSY = ("mp3", "m4a", "opus", "ogg")


def open_in_system(path):
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class JobsView(tk.Frame):
    """Lista de descargas con barra de progreso; se actualiza sin reconstruirse."""

    def __init__(self, parent, app, active_only=False):
        super().__init__(parent, bg=BG)
        self.app = app
        self.active_only = active_only
        self.cards = {}

    def refresh(self):
        jobs = [j for j in self.app.dm.jobs if j.active or not self.active_only]
        ids = {j.id for j in jobs}
        for jid in list(self.cards):
            if jid not in ids:
                self.cards.pop(jid)["frame"].destroy()
        for j in jobs:
            if j.id not in self.cards:
                self.cards[j.id] = self._make_card(j)
            c = self.cards[j.id]
            c["status"].config(text=j.status if not j.active or j.progress <= 0
                               else f"{j.status} {int(j.progress * 100)}%")
            c["bar"]["value"] = j.progress * 100
            if j.active and not c["shown"]:
                c["bar"].pack(fill="x", padx=12, pady=(0, 4))
                c["cancel"].pack(side="right", padx=6)
                c["shown"] = True
            elif not j.active and c["shown"]:
                c["bar"].pack_forget()
                c["cancel"].pack_forget()
                c["shown"] = False
        self.app._update_scroll_hint(self)

    def _make_card(self, j):
        f = tk.Frame(self, bg=SOFT)
        children = self.pack_slaves()
        if children:
            f.pack(fill="x", pady=4, before=children[0])
        else:
            f.pack(fill="x", pady=4)
        head = tk.Frame(f, bg=SOFT)
        head.pack(fill="x", padx=12, pady=(8, 2))
        txt = tk.Frame(head, bg=SOFT)
        txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text=j.label, bg=SOFT, fg=TEXT, font=FONT_BIG, anchor="w").pack(fill="x")
        url = j.url if len(j.url) < 70 else j.url[:67] + "..."
        tk.Label(txt, text=url, bg=SOFT, fg=MUTED, font=FONT, anchor="w").pack(fill="x")
        cancel = button(head, "Cancelar", lambda jid=j.id: self.app.dm.cancel(jid), "danger")
        status = tk.Label(f, text="", bg=SOFT, fg=TEXT, font=FONT, anchor="w", wraplength=700, justify="left")
        status.pack(fill="x", padx=12, pady=(0, 6), side="bottom")
        bar = ttk.Progressbar(f, style="Leaf.Horizontal.TProgressbar", maximum=100)
        return {"frame": f, "status": status, "bar": bar, "cancel": cancel, "shown": False}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KonMusic")
        self.geometry("1020x760")
        self.minsize(880, 640)
        self.configure(bg=BG)
        self._set_icon()
        self.cfg = Config()
        self.ui_q = queue.Queue()
        self.thumbs = Thumbs(self.post)
        self.dm = downloader.DownloadManager(self.post, self.on_jobs_changed, self.on_download_done)
        self.player = None
        self.selected_folder = None
        self.scanning = False
        self.lib_limit = PAGE
        self.pl_limit = PAGE
        self._jobs_flush_pending = False
        self._refs = []

        self._style()
        logo = None
        try:
            logo = ImageTk.PhotoImage(Image.open(paths.resource_path("assets/logo.png")).resize((52, 52), Image.LANCZOS))
            self._refs.append(logo)
        except Exception:
            pass
        GradientBar(self, "KonMusic", logo).pack(fill="x")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_lib = tk.Frame(self.tabs, bg=BG)
        self.tab_dl = tk.Frame(self.tabs, bg=BG)
        self.tab_pl = tk.Frame(self.tabs, bg=BG)
        self.tabs.add(self.tab_lib, text="  Biblioteca  ")
        self.tabs.add(self.tab_dl, text="  Descargar  ")
        self.tabs.add(self.tab_pl, text="  🎶 Listas  ")
        self._build_library()
        self._build_download()
        self._build_playlist()

        self.refresh_library()
        self.refresh_playlist()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._pump)
        threading.Thread(target=self._load_engine_info, daemon=True).start()

    # -- infraestructura -------------------------------------------------------
    def _set_icon(self):
        try:
            if os.name == "nt":
                self.iconbitmap(paths.resource_path("assets/icon.ico"))
            else:
                img = ImageTk.PhotoImage(Image.open(paths.resource_path("assets/logo.png")))
                self._icon = img
                self.iconphoto(True, img)
        except Exception:
            pass

    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(22, 10), font=FONT_BIG, background=SOFT, foreground=TEXT, borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", GREEN)], foreground=[("selected", "white")])
        s.configure("Leaf.Horizontal.TProgressbar", troughcolor="#C5E1A5", background=GREEN,
                    bordercolor=SOFT, lightcolor=GREEN, darkcolor=GREEN)

    def post(self, fn):
        """Programa fn en el hilo de la interfaz (seguro desde otros hilos)."""
        self.ui_q.put(fn)

    def _pump(self):
        try:
            while True:
                fn = self.ui_q.get_nowait()
                try:
                    fn()
                except tk.TclError:
                    pass
                except Exception as e:  # no tumbar la ventana por un error puntual
                    print("Error:", e, file=sys.stderr)
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _update_scroll_hint(self, _w):
        pass

    def on_close(self):
        try:
            if self.player is not None and self.player.winfo_exists():
                self.player.close()
        except Exception:
            pass
        self.cfg.save()
        self.destroy()

    # -- filas con miniatura ---------------------------------------------------
    def _row(self, parent, e, on_play, actions):
        f = tk.Frame(parent, bg=CARD, highlightbackground=SOFT, highlightthickness=1)
        f.pack(fill="x", padx=10, pady=4)
        box = tk.Frame(f, width=120, height=68, bg=SOFT)
        box.pack(side="left", padx=8, pady=8)
        box.pack_propagate(False)
        th = tk.Label(box, text="▶" if e["video"] else "♪", bg=SOFT, fg=GREEN, font=("Segoe UI", 20, "bold"))
        th.pack(fill="both", expand=True)
        info = tk.Frame(f, bg=CARD)
        info.pack(side="left", fill="x", expand=True, padx=4)
        tk.Label(info, text=e["name"], bg=CARD, fg=TEXT, font=FONT_B, anchor="w", justify="left",
                 wraplength=430).pack(fill="x")
        tk.Label(info, text=f'{e["ext"].upper()} · {media.human_size(e["size"])}', bg=CARD, fg=MUTED,
                 font=FONT, anchor="w").pack(fill="x")
        btns = tk.Frame(f, bg=CARD)
        btns.pack(side="right", padx=8)
        for text, cmd, kind in actions:
            button(btns, text, cmd, kind).pack(side="left", padx=3)
        for w in (f, th, info):
            w.bind("<Double-Button-1>", lambda ev: on_play())

        def set_thumb(jpg):
            try:
                img = ImageOps.fit(Image.open(jpg), (120, 68), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                th.configure(image=photo, text="")
                th.image = photo
            except Exception:
                pass
        self.thumbs.request(e, set_thumb)
        return f

    # -- BIBLIOTECA ------------------------------------------------------------
    def _build_library(self):
        top = tk.Frame(self.tab_lib, bg=BG)
        top.pack(fill="x", padx=10, pady=(12, 4))
        self.q_var = tk.StringVar()
        self.q_var.trace_add("write", lambda *a: self._lib_reset())
        tk.Entry(top, textvariable=self.q_var, font=FONT_BIG, relief="flat", bg="white", fg=TEXT,
                 highlightthickness=1, highlightbackground=SOFT, highlightcolor=GREEN
                 ).pack(side="left", fill="x", expand=True, ipady=6)
        self.lib_filter = tk.StringVar(value="all")
        for text, val in (("Todo", "all"), ("Videos", "video"), ("Música", "audio")):
            choice(top, text, self.lib_filter, val, self._lib_reset).pack(side="left", padx=(6, 0))
        button(top, "Abrir archivo...", self.open_file, "soft").pack(side="left", padx=(12, 0))
        self.lib_info = tk.Label(self.tab_lib, text="", bg=BG, fg=MUTED, font=FONT, anchor="w")
        self.lib_info.pack(fill="x", padx=12)
        self.lib_jobs = JobsView(self.tab_lib, self, active_only=True)
        self.lib_jobs.pack(fill="x", padx=10)
        self.lib_list = ScrollFrame(self.tab_lib)
        self.lib_list.pack(fill="both", expand=True)

    def _lib_reset(self):
        self.lib_limit = PAGE
        self.refresh_library()

    def library_entries(self):
        out = []
        for d in (paths.videos_dir(), paths.music_dir()):
            out += media.scan_folder(d)
        out.sort(key=lambda e: e["mtime"], reverse=True)
        return out

    def refresh_library(self):
        allv = self.library_entries()
        total = sum(e["size"] for e in allv)
        self.lib_info.config(text=f"{len(allv)} archivos · {media.human_size(total)} "
                                  f"(Videos/KonMusic y Music/KonMusic)")
        q = self.q_var.get().lower().strip()
        flt = self.lib_filter.get()
        shown = [e for e in allv
                 if (flt == "all" or (flt == "video") == e["video"]) and q in e["name"].lower()]
        self.lib_list.clear()
        inner = self.lib_list.inner
        if not shown:
            tk.Label(inner, text="Aún no hay archivos. Ve a Descargar para añadir el primero.",
                     bg=BG, fg=MUTED, font=FONT).pack(pady=20)
        plist = [e["path"] for e in shown]
        for i, e in enumerate(shown[:self.lib_limit]):
            self._row(inner, e, lambda i=i: self.open_player(plist, i), [
                ("▶ Reproducir", lambda i=i: self.open_player(plist, i), "primary"),
                ("Carpeta", lambda p=e["path"]: open_in_system(os.path.dirname(p)), "soft"),
                ("Eliminar", lambda e=e: self.delete_file(e), "danger"),
            ])
        if len(shown) > self.lib_limit:
            button(inner, f"Mostrar más ({len(shown) - self.lib_limit} restantes)",
                   self._lib_more, "soft").pack(pady=10)

    def _lib_more(self):
        self.lib_limit += PAGE
        self.refresh_library()

    def delete_file(self, e):
        if messagebox.askyesno("Eliminar", f'¿Eliminar "{e["name"]}" del equipo?\nEsta acción no se puede deshacer.'):
            try:
                os.remove(e["path"])
            except OSError as ex:
                messagebox.showerror("Eliminar", f"No se pudo eliminar: {ex}")
            self.refresh_library()
            self.refresh_playlist()

    def open_file(self):
        files = filedialog.askopenfilenames(
            title="Abrir videos o música",
            filetypes=[("Multimedia", " ".join("*." + x for x in sorted(media.MEDIA_EXTS))), ("Todos", "*.*")])
        if files:
            self.open_player(list(files), 0)

    def open_player(self, plist, index):
        if not plist:
            return
        from . import player
        if not player.vlc_available():
            messagebox.showinfo(
                "KonMusic",
                "No se encontró el motor de reproducción (VLC).\n\n"
                "Instala VLC (versión de 64 bits) desde videolan.org y vuelve a abrir KonMusic.\n"
                "Por ahora se abrirá el archivo con tu reproductor del sistema.")
            open_in_system(plist[index])
            return
        try:
            if self.player is not None and self.player.winfo_exists():
                self.player.close()
        except Exception:
            pass
        self.player = player.PlayerWindow(self, self.cfg, plist, index)

    # -- DESCARGAR -------------------------------------------------------------
    def _build_download(self):
        t = self.tab_dl
        box = tk.Frame(t, bg=BG)
        box.pack(fill="x", padx=14, pady=(14, 4))
        tk.Label(box, text="Enlace del video o música (puedes pegar varios):", bg=BG, fg=TEXT,
                 font=FONT_B, anchor="w").pack(fill="x")
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", pady=4)
        self.url_var = tk.StringVar()
        tk.Entry(row, textvariable=self.url_var, font=FONT_BIG, relief="flat", bg="white", fg=TEXT,
                 highlightthickness=1, highlightbackground=SOFT, highlightcolor=GREEN
                 ).pack(side="left", fill="x", expand=True, ipady=7)
        button(row, "Pegar", self.paste_url, "soft").pack(side="left", padx=(8, 0))

        self.mode_var = tk.StringVar(value=self.cfg.get_setting("mode", "video"))
        mrow = tk.Frame(box, bg=BG)
        mrow.pack(fill="x", pady=(8, 4))
        choice(mrow, "🎬 Video", self.mode_var, "video", self._mode_changed).pack(side="left", padx=(0, 6))
        choice(mrow, "🎵 Audio", self.mode_var, "audio", self._mode_changed).pack(side="left")

        self.res_var = tk.IntVar(value=int(self.cfg.get_setting("height", 720)))
        self.fmt_var = tk.StringVar(value=self.cfg.get_setting("fmt", "mp3"))
        self.kbps_var = tk.IntVar(value=int(self.cfg.get_setting("kbps", 192)))

        self.opt_video = tk.Frame(box, bg=BG)
        tk.Label(self.opt_video, text="Resolución", bg=BG, fg=TEXT, font=FONT_B).pack(anchor="w")
        rr = tk.Frame(self.opt_video, bg=BG)
        rr.pack(anchor="w", pady=4)
        for val, text in RESOLUTIONS:
            choice(rr, text, self.res_var, val).pack(side="left", padx=(0, 6))

        self.opt_audio = tk.Frame(box, bg=BG)
        tk.Label(self.opt_audio, text="Formato de audio", bg=BG, fg=TEXT, font=FONT_B).pack(anchor="w")
        fr = tk.Frame(self.opt_audio, bg=BG)
        fr.pack(anchor="w", pady=4)
        for f in AUDIO_FORMATS:
            choice(fr, f.upper(), self.fmt_var, f, self._fmt_changed).pack(side="left", padx=(0, 6))
        self.kbps_row = tk.Frame(self.opt_audio, bg=BG)
        tk.Label(self.kbps_row, text="Calidad", bg=BG, fg=TEXT, font=FONT_B).pack(anchor="w")
        kr = tk.Frame(self.kbps_row, bg=BG)
        kr.pack(anchor="w", pady=4)
        for k in (128, 192, 320):
            choice(kr, f"{k} kbps", self.kbps_var, k).pack(side="left", padx=(0, 6))

        button(box, "Descargar", self.start_download, "primary", font=("Segoe UI", 14, "bold"),
               pady=12).pack(fill="x", pady=(12, 6))
        tk.Label(box, text="Úsala solo con contenido tuyo, libre o con permiso del autor.",
                 bg=BG, fg=MUTED, font=FONT, anchor="w").pack(fill="x")

        tools = tk.Frame(box, bg=BG)
        tools.pack(fill="x", pady=(10, 2))
        self.cookies_btn = button(tools, "", self.import_cookies, "soft")
        self.cookies_btn.pack(side="left")
        button(tools, "Actualizar motor ahora", self.update_engine, "soft").pack(side="left", padx=8)
        self.engine_lbl = tk.Label(tools, text="Motor: comprobando...", bg=BG, fg=MUTED, font=FONT)
        self.engine_lbl.pack(side="left", padx=6)
        self._cookies_text()

        tk.Label(box, text="Cola de descargas", bg=BG, fg=TEXT, font=FONT_BIG, anchor="w").pack(fill="x", pady=(12, 2))
        sf = ScrollFrame(t)
        sf.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        self.dl_jobs = JobsView(sf.inner, self, active_only=False)
        self.dl_jobs.pack(fill="x")
        self._mode_changed()

    def _mode_changed(self):
        self.cfg.set_setting("mode", self.mode_var.get())
        if self.mode_var.get() == "video":
            self.opt_audio.pack_forget()
            self.opt_video.pack(fill="x")
        else:
            self.opt_video.pack_forget()
            self.opt_audio.pack(fill="x")
            self._fmt_changed()

    def _fmt_changed(self):
        if self.fmt_var.get() in LOSSY:
            self.kbps_row.pack(anchor="w")
        else:
            self.kbps_row.pack_forget()

    def paste_url(self):
        try:
            self.url_var.set(self.clipboard_get().strip())
        except tk.TclError:
            pass

    def start_download(self):
        urls = re.findall(r"https?://\S+", self.url_var.get())
        if not urls:
            messagebox.showinfo("KonMusic", "Pega un enlace válido (empieza con http o https).")
            return
        if not paths.ytdlp_cmd():
            messagebox.showerror("KonMusic", "No se encontró el motor de descargas (yt-dlp).")
            return
        if not paths.find_ffmpeg():
            messagebox.showwarning("KonMusic", "No se encontró ffmpeg: algunos videos y los formatos de audio podrían fallar.")
        audio = self.mode_var.get() == "audio"
        for k, v in (("height", self.res_var.get()), ("fmt", self.fmt_var.get()), ("kbps", self.kbps_var.get())):
            self.cfg.data["settings"][k] = v
        self.cfg.save()
        for u in urls:
            self.dm.enqueue(u, audio, self.res_var.get(), self.fmt_var.get(), self.kbps_var.get())
        self.url_var.set("")

    def on_jobs_changed(self):
        """Agrupa las actualizaciones de progreso para no sobrecargar la ventana."""
        if self._jobs_flush_pending:
            return
        self._jobs_flush_pending = True

        def flush():
            self._jobs_flush_pending = False
            self.dl_jobs.refresh()
            self.lib_jobs.refresh()
        self.after(150, flush)

    def on_download_done(self):
        self.refresh_library()

    def _cookies_text(self):
        have = os.path.isfile(paths.cookies_file())
        self.cookies_btn.config(text="Cookies cargadas ✓ (cambiar)" if have else "Importar cookies.txt")

    def import_cookies(self):
        f = filedialog.askopenfilename(title="Archivo cookies.txt",
                                       filetypes=[("cookies.txt", "*.txt"), ("Todos", "*.*")])
        if f:
            try:
                shutil.copy(f, paths.cookies_file())
            except OSError as e:
                messagebox.showerror("KonMusic", f"No se pudo importar: {e}")
            self._cookies_text()

    def _load_engine_info(self):
        v = downloader.engine_version()
        ff = "ffmpeg ✓" if paths.find_ffmpeg() else "ffmpeg no encontrado"
        text = f"Motor yt-dlp {v} · {ff}" if v else f"yt-dlp no encontrado · {ff}"
        self.post(lambda: self.engine_lbl.config(text=text))

    def update_engine(self):
        self.engine_lbl.config(text="Actualizando motor...")

        def work():
            msg = downloader.update_engine()
            v = downloader.engine_version()
            self.post(lambda: self.engine_lbl.config(text=f"{msg} · yt-dlp {v or '?'}"))
        threading.Thread(target=work, daemon=True).start()

    # -- LISTAS (carpetas → playlist) --------------------------------------------
    def _build_playlist(self):
        t = self.tab_pl
        top = tk.Frame(t, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 4))
        button(top, "➕ Agregar carpeta y analizar", self.add_folder, "primary",
               font=("Segoe UI", 11, "bold"), pady=9).pack(side="left")
        self.rescan_btn = button(top, "🔄 Volver a analizar todas", self.rescan, "soft", pady=9)
        self.rescan_btn.pack(side="left", padx=8)
        self.pl_status = tk.Label(top, text="", bg=BG, fg=MUTED, font=FONT)
        self.pl_status.pack(side="left", padx=8)
        self.pl_bar = ttk.Progressbar(t, style="Leaf.Horizontal.TProgressbar", mode="indeterminate")

        body = tk.Frame(t, bg=BG)
        self.pl_body = body
        body.pack(fill="both", expand=True, padx=8, pady=4)
        left = tk.Frame(body, bg=BG, width=330)
        left.pack(side="left", fill="y", padx=(4, 8))
        left.pack_propagate(False)
        self.folders_title = tk.Label(left, text="", bg=BG, fg=TEXT, font=FONT_BIG, anchor="w")
        self.folders_title.pack(fill="x", pady=(2, 4))
        self.folders_hint = tk.Label(left, text="", bg=BG, fg=MUTED, font=FONT, anchor="w",
                                     justify="left", wraplength=310)
        self.folders_hint.pack(fill="x")
        self.folders_list = ScrollFrame(left)
        self.folders_list.pack(fill="both", expand=True)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        head = tk.Frame(right, bg=BG)
        head.pack(fill="x", pady=(2, 4))
        self.pl_title = tk.Label(head, text="", bg=BG, fg=TEXT, font=FONT_BIG, anchor="w")
        self.pl_title.pack(side="left", fill="x", expand=True)
        self.pl_play = button(head, "▶ Reproducir", self.play_shown, "primary")
        self.pl_play.pack(side="right")
        self.pl_list = ScrollFrame(right)
        self.pl_list.pack(fill="both", expand=True)

    def shown_items(self):
        items = [i for i in self.cfg.items if os.path.exists(i["path"])]
        if self.selected_folder is not None:
            items = [i for i in items if i.get("folder") == self.selected_folder]
        return items

    def refresh_playlist(self):
        folders = self.cfg.folders
        if self.selected_folder not in folders:
            self.selected_folder = None
        self.folders_title.config(text=f"Carpetas ({len(folders)})")
        if not folders:
            hint = "Agrega una o más carpetas con tu música o videos y se analizarán."
        elif len(folders) > 1:
            hint = ("Haz clic en una carpeta para ver y reproducir solo esa." if self.selected_folder is None
                    else "Mostrando solo la carpeta seleccionada. Haz clic otra vez para ver todas.")
        else:
            hint = ""
        self.folders_hint.config(text=hint)

        self.folders_list.clear()
        counts = {}
        for i in self.cfg.items:
            counts[i.get("folder")] = counts.get(i.get("folder"), 0) + 1
        for f in folders:
            sel = f == self.selected_folder
            bg = SOFT if sel else CARD
            card = tk.Frame(self.folders_list.inner, bg=bg, highlightbackground=SOFT, highlightthickness=1)
            card.pack(fill="x", padx=2, pady=4)
            tk.Label(card, text=("📂 " if sel else "📁 ") + media.folder_label(f), bg=bg, fg=TEXT,
                     font=FONT_B, anchor="w", wraplength=290, justify="left").pack(fill="x", padx=10, pady=(8, 0))
            tk.Label(card, text=f, bg=bg, fg=MUTED, font=("Segoe UI", 8), anchor="w", wraplength=290,
                     justify="left").pack(fill="x", padx=10)
            tk.Label(card, text=f"{counts.get(f, 0)} archivos", bg=bg, fg=MUTED, font=FONT, anchor="w"
                     ).pack(fill="x", padx=10)
            br = tk.Frame(card, bg=bg)
            br.pack(fill="x", padx=8, pady=8)
            button(br, "▶ Reproducir", lambda f=f: self.play_folder(f), "primary").pack(side="left")
            button(br, "Quitar", lambda f=f: self.remove_folder(f), "danger").pack(side="left", padx=6)
            for w in (card,) + tuple(card.winfo_children()):
                if not isinstance(w, tk.Button) and w is not br:
                    w.bind("<Button-1>", lambda e, f=f: self.select_folder(f))

        shown = self.shown_items()
        if self.selected_folder is None:
            self.pl_title.config(text=f"Playlist ({len(shown)})")
        else:
            self.pl_title.config(text=f"Solo {media.folder_label(self.selected_folder)} ({len(shown)})")
        if shown:
            self.pl_play.pack(side="right")
        else:
            self.pl_play.pack_forget()
        self.pl_list.clear()
        inner = self.pl_list.inner
        if not shown:
            tk.Label(inner, text="La playlist está vacía.", bg=BG, fg=MUTED, font=FONT).pack(pady=20)
        plist = [i["path"] for i in shown]
        for n, e in enumerate(shown[:self.pl_limit]):
            self._row(inner, e, lambda n=n: self.open_player(plist, n), [
                ("▶", lambda n=n: self.open_player(plist, n), "primary"),
                ("Quitar de la lista", lambda e=e: self.remove_item(e), "soft"),
            ])
        if len(shown) > self.pl_limit:
            button(inner, f"Mostrar más ({len(shown) - self.pl_limit} restantes)",
                   self._pl_more, "soft").pack(pady=10)

    def _pl_more(self):
        self.pl_limit += PAGE
        self.refresh_playlist()

    def select_folder(self, f):
        self.selected_folder = None if self.selected_folder == f else f
        self.pl_limit = PAGE
        self.refresh_playlist()

    def play_folder(self, f):
        items = [i for i in self.cfg.items if i.get("folder") == f and os.path.exists(i["path"])]
        self.open_player([i["path"] for i in items], 0)

    def play_shown(self):
        self.open_player([i["path"] for i in self.shown_items()], 0)

    def remove_folder(self, f):
        if messagebox.askyesno("Quitar carpeta",
                               "Se quitará de la lista junto con sus archivos.\nNo se borra nada del equipo."):
            self.cfg.remove_folder(f)
            self.refresh_playlist()

    def remove_item(self, e):
        self.cfg.remove_item(e["path"])
        self.refresh_playlist()

    def add_folder(self):
        d = filedialog.askdirectory(title="Elige una carpeta con música o videos", mustexist=True)
        if not d:
            return
        d = os.path.normpath(d)
        if self.cfg.add_folder(d):
            self.refresh_playlist()
            self.start_scan([d], replace_all=False)
        else:
            self.pl_status.config(text="Esa carpeta ya está en la lista")

    def rescan(self):
        self.cfg.clear_excluded()
        self.start_scan(list(self.cfg.folders), replace_all=True)

    def start_scan(self, folders, replace_all):
        if self.scanning or not folders:
            return
        self.scanning = True
        self.pl_status.config(text="Analizando...")
        self.pl_bar.pack(fill="x", padx=14, pady=2, before=self.pl_body)
        self.pl_bar.start(12)
        self.rescan_btn.config(state="disabled")

        def work():
            found = []
            for f in folders:
                found += media.scan_folder(f)

            def done():
                n = self.cfg.apply_scan(found, set(folders), replace_all)
                self.scanning = False
                self.pl_bar.stop()
                self.pl_bar.pack_forget()
                self.rescan_btn.config(state="normal")
                self.pl_status.config(text=f"{n} archivos encontrados")
                self.pl_limit = PAGE
                self.refresh_playlist()
            self.post(done)
        threading.Thread(target=work, daemon=True).start()
