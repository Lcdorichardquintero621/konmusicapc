"""Rutas, carpetas de la app y búsqueda de herramientas externas (yt-dlp, ffmpeg)."""
import os
import shutil
import sys

APP = "KonMusic"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    """Carpeta donde está el programa (junto al .exe cuando está empaquetado)."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or app_dir()
    return os.path.join(base, rel)


def data_dir() -> str:
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Application Support")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(root, APP)
    os.makedirs(d, exist_ok=True)
    return d


def _user_media_dir(name: str) -> str:
    d = os.path.join(os.path.expanduser("~"), name, APP)
    os.makedirs(d, exist_ok=True)
    return d


def videos_dir() -> str:
    return _user_media_dir("Videos")


def music_dir() -> str:
    return _user_media_dir("Music")


def tmp_dir() -> str:
    d = os.path.join(data_dir(), "tmp")
    os.makedirs(d, exist_ok=True)
    return d


def cookies_file() -> str:
    return os.path.join(data_dir(), "cookies.txt")


def exe(name: str) -> str:
    return name + ".exe" if os.name == "nt" else name


def find_ffmpeg():
    for p in (resource_path(os.path.join("bin", exe("ffmpeg"))),
              os.path.join(app_dir(), "bin", exe("ffmpeg"))):
        if os.path.isfile(p):
            return p
    return shutil.which("ffmpeg")


def ytdlp_cmd():
    """Devuelve la lista de comando para ejecutar yt-dlp, o None si no está disponible.

    En el .exe se usa una copia editable en la carpeta de datos del usuario (para poder
    actualizarla con 'yt-dlp -U'); si no, el yt-dlp del sistema o el módulo de Python.
    """
    user_bin = os.path.join(data_dir(), "bin")
    target = os.path.join(user_bin, exe("yt-dlp"))
    bundled = resource_path(os.path.join("bin", exe("yt-dlp")))
    if not os.path.isfile(target) and os.path.isfile(bundled):
        os.makedirs(user_bin, exist_ok=True)
        shutil.copy2(bundled, target)
    if os.path.isfile(target):
        return [target]
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    try:
        import yt_dlp  # noqa: F401,WPS433
        return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        return None


def no_window_flags() -> int:
    """Evita que aparezca una ventana negra de consola en Windows."""
    return 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
