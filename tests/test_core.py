"""Pruebas de la lógica (sin ventana): configuración, escaneo, comandos y flujo de descarga simulado."""
import os
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAKE = r'''
import os, sys, time
a = sys.argv[1:]
out = a[a.index("-o") + 1]
fmt_audio = "-x" in a
for p in (10, 55, 100):
    print("KM| %.1f%%" % p, flush=True)
if "FAILME" in a[-1]:
    print("ERROR: [youtube] abc: Please sign in", flush=True)
    sys.exit(1)
ext = "mp3" if fmt_audio else "mp4"
path = out.replace("%(title).100s", "Mi cancion").replace("%(ext)s", ext)
open(path, "wb").write(b"x" * 2048)
'''


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["HOME"] = self.tmp
        os.environ["APPDATA"] = self.tmp
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        from konmusic import paths
        self.paths = paths

    def test_media_scan_and_sizes(self):
        from konmusic import media
        d = os.path.join(self.tmp, "m", "sub")
        os.makedirs(d)
        for n in ("a.mp3", "b.MKV", "c.txt"):
            open(os.path.join(d, n), "wb").write(b"1234")
        found = media.scan_folder(os.path.join(self.tmp, "m"))
        self.assertEqual(sorted(e["name"] for e in found), ["a", "b"])
        self.assertTrue([e for e in found if e["name"] == "b"][0]["video"])
        self.assertEqual(media.human_size(500), "500 B")
        self.assertEqual(media.human_size(1536), "1.5 KB")

    def test_config_persists_and_excludes(self):
        from konmusic.config import Config
        from konmusic import media
        f1 = os.path.join(self.tmp, "f1")
        os.makedirs(f1)
        for n in ("x.mp3", "y.mp3"):
            open(os.path.join(f1, n), "wb").write(b"1")
        cfg = Config(os.path.join(self.tmp, "c.json"))
        self.assertTrue(cfg.add_folder(f1))
        self.assertFalse(cfg.add_folder(f1))
        cfg.apply_scan(media.scan_folder(f1), {cfg.folders[0]})
        self.assertEqual(len(cfg.items), 2)
        cfg.remove_item(cfg.items[0]["path"])
        self.assertEqual(len(cfg.items), 1)
        # reabrir: recuerda carpetas, playlist y lo quitado
        cfg2 = Config(os.path.join(self.tmp, "c.json"))
        self.assertEqual(cfg2.folders, cfg.folders)
        self.assertEqual(len(cfg2.items), 1)
        self.assertEqual(len(cfg2.data["excluded"]), 1)
        # volver a analizar no vuelve a meter lo quitado hasta limpiar exclusiones
        cfg2.apply_scan(media.scan_folder(f1), set(cfg2.folders), replace_all=True)
        self.assertEqual(len(cfg2.items), 1)
        cfg2.clear_excluded()
        cfg2.apply_scan(media.scan_folder(f1), set(cfg2.folders), replace_all=True)
        self.assertEqual(len(cfg2.items), 2)
        cfg2.remove_folder(cfg2.folders[0])
        self.assertEqual(cfg2.items, [])

    def test_build_cmd_and_parsers(self):
        from konmusic import downloader as d
        job = d.Job("https://youtu.be/x", False, 1080, "mp4", 192)
        cmd = d.build_cmd(["yt-dlp"], job, "/tmp/o", "/bin/ffmpeg", None, "android_vr")
        self.assertIn("bv*[height<=1080]+ba/b[height<=1080]/b", cmd)
        self.assertIn("youtube:player_client=android_vr", cmd)
        self.assertEqual(cmd[-1], "https://youtu.be/x")
        a = d.build_cmd(["yt-dlp"], d.Job("u", True, 0, "mp3", 320), "/t")
        self.assertIn("-x", a)
        self.assertIn("320K", a)
        w = d.build_cmd(["yt-dlp"], d.Job("u", True, 0, "wav", 0), "/t")
        self.assertNotIn("--audio-quality", w)
        self.assertAlmostEqual(d.parse_progress("KM| 45.3%"), 0.453)
        self.assertIsNone(d.parse_progress("otra cosa"))
        self.assertIn("sign in", d.last_error(["x", "ERROR: Please sign in", "y"]))

    def test_download_flow_with_fake_ytdlp(self):
        from konmusic import downloader as d
        fake = os.path.join(self.tmp, "fake.py")
        open(fake, "w").write(FAKE)
        self.paths.ytdlp_cmd = lambda: [sys.executable, fake]
        self.paths.find_ffmpeg = lambda: None
        events = []
        done = threading.Event()
        dm = d.DownloadManager(lambda fn: fn(), lambda: None, lambda: (events.append("done"), done.set()))
        dm.enqueue("https://example.com/video", False, 720, "mp4", 192)
        self.assertTrue(done.wait(15))
        self.assertEqual(dm.jobs[0].status, "Completado")
        self.assertTrue(os.path.isfile(os.path.join(self.paths.videos_dir(), "Mi cancion.mp4")))
        # audio y nombre repetido -> no pisa archivos
        done.clear()
        dm.enqueue("https://example.com/a", True, 0, "mp3", 192)
        self.assertTrue(done.wait(15))
        self.assertTrue(os.path.isfile(os.path.join(self.paths.music_dir(), "Mi cancion.mp3")))
        done.clear()
        dm.enqueue("https://example.com/video", False, 720, "mp4", 192)
        self.assertTrue(done.wait(15))
        self.assertTrue(os.path.isfile(os.path.join(self.paths.videos_dir(), "Mi cancion (1).mp4")))

    def test_failure_reports_error(self):
        from konmusic import downloader as d
        fake = os.path.join(self.tmp, "fake.py")
        open(fake, "w").write(FAKE)
        self.paths.ytdlp_cmd = lambda: [sys.executable, fake]
        self.paths.find_ffmpeg = lambda: None
        dm = d.DownloadManager(lambda fn: fn(), lambda: None, lambda: None)
        job = dm.enqueue("https://example.com/FAILME", False, 720, "mp4", 192)
        for _ in range(100):
            if not job.active:
                break
            time.sleep(0.1)
        self.assertTrue(job.status.startswith("Error"))
        self.assertIn("sign in", job.status)


if __name__ == "__main__":
    unittest.main()
