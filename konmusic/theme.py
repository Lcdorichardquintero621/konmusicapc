"""Colores verde hoja y widgets reutilizables (barra con degradado, lista con scroll, botones)."""
import tkinter as tk

GREEN_DARK = "#1B5E20"
GREEN = "#2E7D32"
GREEN_MID = "#5E9E34"
LEAF = "#8BC34A"
BG = "#F1F8E9"
SOFT = "#DCEDC8"
CARD = "#FFFFFF"
TEXT = "#1B2E1C"
MUTED = "#6B7B6C"
RED = "#B3261E"

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_BIG = ("Segoe UI", 12, "bold")


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def lerp(c1, c2, t):
    a, b = _hex(c1), _hex(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def button(parent, text, command, kind="primary", **kw):
    """kind: primary (verde), soft (verde claro), danger (rojo), dark (para el reproductor)."""
    styles = {
        "primary": (GREEN, "white", GREEN_MID),
        "soft": (SOFT, GREEN_DARK, "#CDE5B0"),
        "danger": ("#FBE9E7", RED, "#F6D3CE"),
        "dark": (GREEN_MID, "white", LEAF),
    }
    bg, fg, active = styles[kind]
    opts = dict(text=text, command=command, bg=bg, fg=fg, activebackground=active,
                activeforeground=fg, relief="flat", bd=0, cursor="hand2",
                font=FONT_B, padx=14, pady=7)
    opts.update(kw)
    return tk.Button(parent, **opts)


def choice(parent, text, variable, value, command=None, dark=False):
    """Botón tipo 'chip' que se marca al elegirlo (en lugar de un radio)."""
    if dark:
        off, on, fg_off, fg_on = GREEN_MID, "white", "white", GREEN_DARK
    else:
        off, on, fg_off, fg_on = SOFT, GREEN, GREEN_DARK, "white"
    return tk.Radiobutton(
        parent, text=text, variable=variable, value=value, command=command,
        indicatoron=False, bg=off, fg=fg_off, selectcolor=on, activebackground=on,
        activeforeground=fg_on, relief="flat", bd=0, padx=12, pady=6, font=FONT_B, cursor="hand2")


class GradientBar(tk.Canvas):
    """Barra superior con degradado de verde hoja a verde tierno, logo y título."""

    def __init__(self, parent, title, logo=None, height=68):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=GREEN)
        self.h = height
        self.logo = logo
        self.title_txt = title
        self.bind("<Configure>", self._draw)

    def _draw(self, _e=None):
        w = self.winfo_width()
        self.delete("all")
        step = 4
        for x in range(0, w + step, step):
            t = min(x / max(w, 1), 1.0)
            if t < 0.5:
                col = lerp(GREEN, GREEN_MID, t * 2)
            else:
                col = lerp(GREEN_MID, LEAF, (t - 0.5) * 2)
            self.create_rectangle(x, 0, x + step, self.h, fill=col, outline=col)
        x0 = 14
        if self.logo is not None:
            self.create_image(x0, self.h // 2, image=self.logo, anchor="w")
            x0 += self.logo.width() + 12
        self.create_text(x0, self.h // 2, text=self.title_txt, anchor="w", fill="white",
                         font=("Segoe UI", 22, "bold"))


class ScrollFrame(tk.Frame):
    """Contenedor con barra de desplazamiento vertical (rueda del ratón incluida)."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", self._bind_wheel)
            w.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _e=None):
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))

    def _unbind_wheel(self, _e=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)
