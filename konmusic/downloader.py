"""Descargas con yt-dlp (como proceso externo): cola, progreso, reintentos y guardado final."""
import os
import queue
import re
import shutil
import subprocess
import threading
import uuid

from . import paths
from .media import MEDIA_EXTS, VIDEO_EXTS, ext_of

CLIENTS_YT = [None, "android_vr", "tv", "mweb", "web_safari"]
NO_RETRY = ("Unsupported URL", "Private video", "Video unavailable", "not a valid URL")
PCT = re.compile(r"KM\|\s*([\d.]+)%")


class Job:
    def __init__(self, url, audio, height, fmt, kbps):
        self.id = uuid.uuid4().hex
        self.url = url
        self.audio = audio
        self.height = height
        self.fmt = fmt
        self.kbps = kbps
        self.label = f"Audio {fmt.upper()}" if audio else f"Video {height}p"
        self.progress = 0.0
        self.status = "En cola"

    @property
    def active(self):
        return self.status in ("En cola", "Descargando", "Guardando...")


def build_cmd(base, job, outdir, ffmpeg=None, cookies=None, client=None):
    """Arma la línea de comando de yt-dlp para un trabajo."""
    cmd = list(base) + [
        "--no-playlist", "--newline", "--no-colors", "--no-warnings",
        "-o", os.path.join(outdir, "%(title).100s.%(ext)s"),
        "--progress-template", "download:KM|%(progress._percent_str)s",
    ]
    if ffmpeg:
        cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
    if cookies and os.path.isfile(cookies):
        cmd += ["--cookies", cookies]
    if client:
        cmd += ["--extractor-args", f"youtube:player_client={client}"]
    if job.audio:
        cmd += ["-x", "--audio-format", job.fmt]
        if job.fmt in ("mp3", "m4a", "opus", "vorbis"):
            cmd += ["--audio-quality", f"{job.kbps}K"]
    else:
        h = job.height
        cmd += ["-f", f"bv*[height<={h}]+ba/b[height<={h}]/b",
                "--merge-output-format", "mp4/mkv"]
    cmd.append(job.url)
    return cmd


def parse_progress(line):
    m = PCT.search(line)
    return float(m.group(1)) / 100.0 if m else None


def last_error(lines):
    errs = [l for l in lines if "ERROR" in l]
    pick = errs[-1] if errs else (lines[-1] if lines else "falló")
    return pick.strip()[:200]


def unique_path(folder, name):
    base, ext = os.path.splitext(name)
    p = os.path.join(folder, name)
    n = 1
    while os.path.exists(p):
        p = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return p


class DownloadManager:
    def __init__(self, post, on_change, on_done):
        """post(fn): ejecuta fn en el hilo de la interfaz. on_change/on_done se llaman allí."""
        self.post = post
        self.on_change = on_change
        self.on_done = on_done
        self.jobs = []
        self.q = queue.Queue()
        self.cancelled = set()
        self.procs = {}
        threading.Thread(target=self._worker, daemon=True).start()

    # -- API -------------------------------------------------------------
    def enqueue(self, url, audio, height, fmt, kbps):
        job = Job(url, audio, height, "vorbis" if fmt == "ogg" else fmt, kbps)
        self.jobs.append(job)
        self.q.put(job)
        self.post(self.on_change)
        return job

    def cancel(self, job_id):
        self.cancelled.add(job_id)
        p = self.procs.get(job_id)
        if p:
            try:
                p.terminate()
            except Exception:
                pass
        for j in self.jobs:
            if j.id == job_id and j.status == "En cola":
                j.status = "Cancelado"
        self.post(self.on_change)

    def clear_finished(self):
        self.jobs = [j for j in self.jobs if j.active]
        self.post(self.on_change)

    # -- trabajo ---------------------------------------------------------
    def _set(self, job, **kw):
        for k, v in kw.items():
            setattr(job, k, v)
        self.post(self.on_change)

    def _worker(self):
        while True:
            job = self.q.get()
            if job.id in self.cancelled:
                continue
            try:
                self._run(job)
            except Exception as e:  # nunca dejar morir el hilo
                self._set(job, status=f"Error: {str(e)[:150]}")

    def _run(self, job):
        base = paths.ytdlp_cmd()
        if not base:
            self._set(job, status="Error: no se encontró yt-dlp")
            return
        ffmpeg = paths.find_ffmpeg()
        clients = CLIENTS_YT if ("youtu" in job.url) else [None]
        self._set(job, status="Descargando", progress=0.0)
        err = "falló"
        for client in clients:
            if job.id in self.cancelled:
                break
            tmp = os.path.join(paths.tmp_dir(), job.id)
            shutil.rmtree(tmp, ignore_errors=True)
            os.makedirs(tmp, exist_ok=True)
            cmd = build_cmd(base, job, tmp, ffmpeg, paths.cookies_file(), client)
            ok, err = self._exec(job, cmd)
            if ok:
                self._set(job, progress=1.0, status="Guardando...")
                self._export(job, tmp)
                shutil.rmtree(tmp, ignore_errors=True)
                self._set(job, status="Completado")
                self.post(self.on_done)
                return
            shutil.rmtree(tmp, ignore_errors=True)
            if any(s.lower() in err.lower() for s in NO_RETRY):
                break
        if job.id in self.cancelled:
            self._set(job, status="Cancelado")
        else:
            self._set(job, status=f"Error: {err}")

    def _exec(self, job, cmd):
        lines = []
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", creationflags=paths.no_window_flags())
        except Exception as e:
            return False, str(e)[:200]
        self.procs[job.id] = proc
        try:
            for line in proc.stdout:
                p = parse_progress(line)
                if p is not None:
                    self._set(job, progress=min(max(p, 0.0), 1.0))
                else:
                    lines.append(line.rstrip())
                    lines = lines[-40:]
                if job.id in self.cancelled:
                    proc.terminate()
                    break
            proc.wait()
        finally:
            self.procs.pop(job.id, None)
        if job.id in self.cancelled:
            return False, "Cancelado"
        return proc.returncode == 0, last_error(lines)

    def _export(self, job, tmp):
        """Mueve lo descargado a Videos/KonMusic o Music/KonMusic."""
        for f in os.listdir(tmp):
            src = os.path.join(tmp, f)
            ext = ext_of(f)
            if not os.path.isfile(src) or ext not in MEDIA_EXTS:
                continue
            dest_dir = paths.videos_dir() if ext in VIDEO_EXTS else paths.music_dir()
            shutil.move(src, unique_path(dest_dir, f))


# -- motor yt-dlp ------------------------------------------------------------
def engine_version():
    base = paths.ytdlp_cmd()
    if not base:
        return None
    try:
        r = subprocess.run(base + ["--version"], capture_output=True, text=True, timeout=30,
                           creationflags=paths.no_window_flags())
        return r.stdout.strip() or None
    except Exception:
        return None


def update_engine():
    """Actualiza yt-dlp. Devuelve un texto con el resultado."""
    base = paths.ytdlp_cmd()
    if not base:
        return "No se encontró yt-dlp"
    import sys
    try:
        if base[:2] == [sys.executable, "-m"]:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                               capture_output=True, text=True, timeout=300,
                               creationflags=paths.no_window_flags())
            return "Actualizado" if r.returncode == 0 else "No se pudo actualizar con pip"
        for args in (["--update-to", "nightly"], ["-U"]):
            r = subprocess.run(base + args, capture_output=True, text=True, timeout=300,
                               creationflags=paths.no_window_flags())
            if r.returncode == 0:
                return "Motor actualizado"
        return "No se pudo actualizar (¿sin internet?)"
    except Exception as e:
        return f"No se pudo actualizar: {str(e)[:80]}"
