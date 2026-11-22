"""Tipos de archivo, escaneo de carpetas y formato de tamaños."""
import os

VIDEO_EXTS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "3gp", "ts", "wmv", "m4v", "mpg", "mpeg"}
AUDIO_EXTS = {"mp3", "m4a", "opus", "ogg", "wav", "flac", "aac", "wma"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".").lower()


def is_video(path: str) -> bool:
    return ext_of(path) in VIDEO_EXTS


def entry_for(path: str, folder: str = ""):
    """Crea la ficha de un archivo multimedia o None si no lo es / no existe."""
    ext = ext_of(path)
    if ext not in MEDIA_EXTS:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    return {
        "path": path,
        "name": os.path.splitext(os.path.basename(path))[0],
        "ext": ext,
        "size": st.st_size,
        "video": ext in VIDEO_EXTS,
        "mtime": st.st_mtime,
        "folder": folder,
    }


def scan_folder(folder: str):
    """Busca videos y música dentro de la carpeta, incluidas las subcarpetas."""
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            e = entry_for(os.path.join(root, f), folder)
            if e:
                out.append(e)
    return out


def human_size(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if x < 1024 or unit == "GB":
            return f"{x:.0f} {unit}" if unit == "B" else f"{x:.1f} {unit}"
        x /= 1024
    return f"{x:.1f} GB"


def folder_label(path: str) -> str:
    base = os.path.basename(os.path.normpath(path))
    return base or path
