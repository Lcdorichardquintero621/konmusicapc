"""Configuración persistente: carpetas, playlist, elementos quitados y posiciones de reproducción."""
import json
import os
import threading

from . import paths


class Config:
    def __init__(self, file=None):
        self.file = file or os.path.join(paths.data_dir(), "config.json")
        self.lock = threading.Lock()
        self.data = {"folders": [], "items": [], "excluded": [], "pos": {}, "settings": {}}
        self.load()

    # -- archivo ---------------------------------------------------------
    def load(self):
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k in self.data:
                if k in loaded:
                    self.data[k] = loaded[k]
        except Exception:
            pass

    def save(self):
        with self.lock:
            try:
                tmp = self.file + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, self.file)
            except Exception:
                pass

    # -- carpetas y playlist ---------------------------------------------
    @property
    def folders(self):
        return self.data["folders"]

    @property
    def items(self):
        return self.data["items"]

    def add_folder(self, path: str) -> bool:
        path = os.path.normpath(path)
        if path in self.data["folders"]:
            return False
        self.data["folders"].append(path)
        self.save()
        return True

    def remove_folder(self, path: str):
        if path in self.data["folders"]:
            self.data["folders"].remove(path)
        self.data["items"] = [i for i in self.data["items"] if i.get("folder") != path]
        self.save()

    def remove_item(self, path: str):
        self.data["items"] = [i for i in self.data["items"] if i["path"] != path]
        if path not in self.data["excluded"]:
            self.data["excluded"].append(path)
        self.save()

    def clear_excluded(self):
        self.data["excluded"] = []

    def apply_scan(self, scanned, folders_scanned, replace_all=False):
        """Mezcla el resultado del análisis en la playlist (sin los elementos quitados)."""
        excluded = set(self.data["excluded"])
        fresh = [e for e in scanned if e["path"] not in excluded]
        if replace_all:
            keep = []
        else:
            keep = [i for i in self.data["items"] if i.get("folder") not in folders_scanned]
        items = keep + fresh
        order = {f: n for n, f in enumerate(self.data["folders"])}
        items.sort(key=lambda i: (order.get(i.get("folder"), 999), i["name"].lower()))
        self.data["items"] = items
        self.save()
        return len(fresh)

    # -- posiciones y ajustes --------------------------------------------
    def get_pos(self, path: str) -> int:
        return int(self.data["pos"].get(path, 0))

    def set_pos(self, path: str, ms: int):
        if ms <= 0:
            self.data["pos"].pop(path, None)
        else:
            self.data["pos"][path] = int(ms)

    def get_setting(self, key, default=None):
        return self.data["settings"].get(key, default)

    def set_setting(self, key, value):
        self.data["settings"][key] = value
        self.save()
