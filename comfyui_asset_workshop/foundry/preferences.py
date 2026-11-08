"""Non-sensitive interface preferences; credentials belong to the existing OS vault."""
import json
import threading
from pathlib import Path

class Preferences:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def read(self):
        with self.lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError):
                data = {}
            return {"theme": data.get("theme") if data.get("theme") in ("light", "dark") else None,
                    "language": "en", "profile": "default",
                    "font_size": data.get("font_size","default") if data.get("font_size","default") in ("default","larger","large","extra-large","175","200") else "default",
                    "busy_motion": data.get("busy_motion", "system") if data.get("busy_motion", "system") in ("system", "full", "paused") else "system",
                    "auto_check_updates": data.get("auto_check_updates", True) is not False}

    def update(self, patch):
        if not isinstance(patch, dict) or set(patch) - {"theme", "language", "profile", "auto_check_updates", "busy_motion", "font_size"}:
            raise ValueError("Only supported interface preferences can be saved here.")
        if patch.get("font_size","default") not in ("default","larger","large","extra-large","175","200"):
            raise ValueError("Choose Default or one of the supported text percentages.")
        if "auto_check_updates" in patch and not isinstance(patch["auto_check_updates"], bool):
            raise ValueError("Automatic update checks must be on or off.")
        if "theme" in patch and patch["theme"] not in ("light", "dark"):
            raise ValueError("Choose the light or dark theme.")
        if patch.get("busy_motion", "system") not in ("system", "full", "paused"):
            raise ValueError("Choose system, full or paused busy animations.")
        if patch.get("profile", "default") != "default":
            raise ValueError("Only the Default memory profile is configured.")
        if patch.get("language", "en") != "en":
            raise ValueError("Translations are not available yet.")
        with self.lock:
            data = {**self.read(), **patch}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(data), encoding="utf-8")
            temp.replace(self.path)
            return data
