"""Miniaturas: un fotograma del video o la carátula incrustada del audio (vía ffmpeg), con caché."""
import hashlib
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

from . import paths


class Thumbs:
    def __init__(self, post):
        self.post = post
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.dir = os.path.join(paths.data_dir(), "thumbs")
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.Lock()
        self.ffmpeg = paths.find_ffmpeg()

    def _cache_path(self, path):
        try:
            m = os.path.getmtime(path)
        except OSError:
            m = 0
        h = hashlib.md5(f"{path}|{m}".encode("utf-8", "ignore")).hexdigest()
        return os.path.join(self.dir, h + ".jpg")

    def _make(self, path, video):
        out = self._cache_path(path)
        if os.path.isfile(out):
            return out
        if os.path.isfile(out + ".none"):
            return None
        if not self.ffmpeg:
            return None
        attempts = []
        if video:
            attempts.append(["-ss", "1", "-i", path])
            attempts.append(["-i", path])
        else:
            attempts.append(["-i", path, "-an"])
        for pre in attempts:
            cmd = [self.ffmpeg, "-y", "-loglevel", "error"] + pre + \
                  ["-frames:v", "1", "-vf", "scale=240:-2", out]
            try:
                subprocess.run(cmd, capture_output=True, timeout=20,
                               creationflags=paths.no_window_flags())
            except Exception:
                continue
            if os.path.isfile(out) and os.path.getsize(out) > 0:
                return out
        try:
            open(out + ".none", "w").close()
        except OSError:
            pass
        return None

    def request(self, entry, callback):
        """Pide la miniatura en segundo plano; callback(ruta_jpg) se ejecuta en el hilo de la interfaz."""
        def work():
            res = self._make(entry["path"], entry["video"])
            if res:
                self.post(lambda: callback(res))
        self.pool.submit(work)
