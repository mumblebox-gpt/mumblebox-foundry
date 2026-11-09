"""Exact ownership of exported files. No recursive deletion or arbitrary path access."""
import hashlib
import os
from pathlib import Path, PurePosixPath

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()

def relative_name(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Invalid package filename.")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ("", ".", "..") or part.rstrip(" .") != part for part in value.split("/")):
        raise ValueError("Package filenames must remain inside their directory.")
    if any(ord(c) < 32 for c in value):
        raise ValueError("Invalid package filename.")
    return p

def owned_path(root, path):
    root = Path(root).resolve()
    path = Path(path).absolute()
    # Reject aliases through symlinks/junctions, not just paths that escape the root.
    try:
        for current in (path, *path.parents):
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                raise ValueError("Linked output paths cannot be managed by the library.")
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or resolved == root:
            raise ValueError("This file is outside the managed output directory.")
        return resolved
    except (OSError, ValueError):
        raise ValueError("This file is outside the managed output directory or uses a linked path.") from None

def fingerprint(path):
    p = Path(path)
    if not p.is_file(): return None
    stat = p.stat()
    return {"size": stat.st_size, "mtime": stat.st_mtime_ns}

def remove_exact(paths):
    """All checks happen before this function. Partial OS failures are reported, never hidden."""
    removed, failures = [], []
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
            removed.append(str(path))
        except OSError:
            failures.append(str(path))
    return removed, failures

def open_folder(path, label="output folder"):
    path = Path(path)
    if not path.is_dir(): raise ValueError(f"The {label} is no longer available.")
    if os.name != "nt":
        raise ValueError(f"Opening the server’s {label} is currently available on Windows.")
    os.startfile(str(path))
