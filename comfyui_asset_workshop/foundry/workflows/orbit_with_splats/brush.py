"""Resolve and prepare the pinned Brush executable used by Orbit with Splats."""
import os
import platform
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from ...artifacts import digest

BRUSH_VERSION = "0.3.0"
BRUSH_RELEASE = "https://github.com/ArthurBrussee/brush/releases/tag/v" + BRUSH_VERSION
BRUSH_SHA256 = "37e46cbf808b9983dd15a5f9a25328dbe43e7e06d53c4f59fbeaeb10e3a5b34a"
ARCHIVE_URL = BRUSH_RELEASE.replace("/tag/", "/download/") + "/brush-app-x86_64-pc-windows-msvc.zip"
ARCHIVE_SHA256 = "b68e3e9cf052d51bf3ee30776fa5a364de7f2ba13b58443128ff797bb7bcfcd6"
ARCHIVE_SIZE = 158791348
PREPARING = "Preparing Brush"
UNAVAILABLE = "Foundry could not prepare Brush. Check your internet connection and free disk space, then retry."
BAD_OVERRIDE = "The Brush override is missing or does not match the verified build. Check MUMBLEBOX_BRUSH or remove it to use automatic setup."
INSTALL_LOCK = Lock()


def can_install():
    return sys.platform == "win32" and platform.machine().lower() in {"amd64", "x86_64"}


def brush_path():
    import folder_paths

    override = os.environ.get("MUMBLEBOX_BRUSH")
    if override:
        return Path(override)
    return Path(folder_paths.get_user_directory()) / "mumblebox-foundry" / "tools" / f"brush-v{BRUSH_VERSION}" / "brush_app.exe"


def ensure_brush(cancelled=lambda: False):
    """Verify a ready copy or publish a verified download into the managed tools folder."""
    def check():
        if cancelled():
            raise InterruptedError("Brush preparation was cancelled.")

    while not INSTALL_LOCK.acquire(timeout=0.2):
        check()
    try:
        check()
        target = brush_path()
        if target.is_file() and digest(target) == BRUSH_SHA256:
            return target
        if os.environ.get("MUMBLEBOX_BRUSH"):
            raise ValueError(BAD_OVERRIDE)
        if not can_install():
            raise ValueError("Automatic Brush setup requires 64-bit Windows.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".brush-", dir=target.parent) as staging:
            stage = Path(staging)
            archive_path = stage / "brush.zip"
            request = Request(ARCHIVE_URL, headers={"User-Agent": "Mumblebox-Foundry"})
            with urlopen(request, timeout=30) as response, archive_path.open("wb") as output:
                total = 0
                while block := response.read(1024 * 1024):
                    check()
                    total += len(block)
                    if total > ARCHIVE_SIZE:
                        raise ValueError("Brush archive exceeded its verified size.")
                    output.write(block)
            check()
            if total != ARCHIVE_SIZE or digest(archive_path) != ARCHIVE_SHA256:
                raise ValueError("Brush archive checksum did not match.")
            executable = stage / "brush_app.exe"
            with ZipFile(archive_path) as archive:
                for name in (executable.name, "LICENSE"):
                    with archive.open(name) as source, (stage / name).open("wb") as output:
                        shutil.copyfileobj(source, output)
            if digest(executable) != BRUSH_SHA256:
                raise ValueError("Brush executable checksum did not match.")
            check()
            (stage / "LICENSE").replace(target.parent / "LICENSE")
            executable.replace(target)
        return target
    finally:
        INSTALL_LOCK.release()


def prepare_brush(cancelled=lambda: False):
    try:
        return ensure_brush(cancelled)
    except InterruptedError:
        raise
    except (URLError, OSError, BadZipFile, KeyError, ValueError) as error:
        if str(error) == BAD_OVERRIDE:
            raise
        raise ValueError(UNAVAILABLE) from error
