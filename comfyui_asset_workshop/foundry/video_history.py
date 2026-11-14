"""Discover standalone workflow videos from Foundry-owned run directories."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .artifacts import owned_path

VIDEO_SUFFIXES = frozenset({".mp4", ".webm", ".mov", ".mkv"})
RUN_ID = re.compile(r"[a-f0-9]{32}")
SOURCES = (
    ("orbit-with-splats", "foundry/orbit-with-splats", "orbit_*", "Orbit with Splats"),
    ("orbit-with-splats", "foundry/orbit-with-splats", "hybrid-*.mp4", "Orbit with Splats"),
    ("orbit-to-mesh", "foundry/orbit-to-mesh", "orbit_*", "Orbit to Mesh"),
    ("virtual-turntable", "foundry/virtual-turntable", "orbit_*", "Virtual Turntable"),
    ("splat-runs", "foundry-splat", "orbit/asset_*", "Splat & Solid"),
    ("hair-runs", "foundry-hair", "variant-*/export_*/motion_*", "HairDeck"),
)


def video_file(path):
    return Path(path).suffix.lower() in VIDEO_SUFFIXES


def available_entries(root, entries):
    return [entry for entry in entries if not video_file(entry["filename"]) or
            (root / entry["subfolder"] / entry["filename"]).is_file()]


def sync(library):
    if library.busy():
        return {"busy": True, "failed": 0}
    # Only inspect the output layouts owned by these workflow writers. Keep
    # every rendition, even if a later run receipt points at a newer video.
    failed = 0
    for state, output, pattern, workflow in SOURCES:
        folder = library.output_root / output
        for run_dir in folder.iterdir() if folder.is_dir() else ():
            if not RUN_ID.fullmatch(run_dir.name):
                continue
            receipt = library.root / state / (run_dir.name + ".json")
            if not receipt.is_file():
                continue
            try:
                owned_path(library.output_root, run_dir)
                paths = [path for path in run_dir.glob(pattern) if video_file(path) and path.is_file()]
                if not paths:
                    continue
                run = json.loads(receipt.read_text(encoding="utf-8"))
                name = run.get("name") or run.get("config", {}).get("name") or workflow
                for path in paths:
                    stat = path.stat()
                    if stat.st_size:
                        created = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                        library.import_video(path, name, workflow, created)
            except (OSError, ValueError, TypeError, AttributeError):
                failed += 1
    return {"busy": False, "failed": failed}
