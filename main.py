"""KonMusic para PC: descarga video y audio, biblioteca, listas por carpeta y reproductor."""
import sys


def _dpi_aware():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def main():
    _dpi_aware()
    from konmusic.ui import App
    App().mainloop()


if __name__ == "__main__":
    main()
