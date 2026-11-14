"""Portable pair archive. Standard mesh variants retain their existing catalog."""
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ...artifacts import owned_path
from .definition import CREDITS, LICENSE_MESSAGE

def build_pair(output_root, checkpoints):
    manifest = owned_path(output_root, checkpoints["pair"])
    directory = manifest.parent
    pair = json.loads(manifest.read_text(encoding="utf-8"))
    archive = directory / "orbit-with-splats.zip"
    if archive.is_file():
        return archive
    partial = archive.with_suffix(".partial")
    files = {
        "textured-mesh.glb": "Textured, editable polygon mesh with embedded textures.",
        "gaussian-splat.ply": "Trained Gaussian splat with view-dependent color.",
        "alignment.json": "Solved camera fit, selected source frames and grounding transform.",
        "pair.json": "Pair format, training preset, Gaussian count and Brush version.",
    }
    readme = ["# Orbit with Splats", "",
              "The mesh and splat share one right-handed Y-up coordinate system. Their fine surface detail can differ.",
              "", "## Files", ""]
    readme.extend(f"- `{name}` — {description}" for name, description in files.items())
    readme.extend(["", f"Brush trained {pair['gaussians']:,} Gaussians from {pair['training_views']} views.",
                   "", "## Credits and terms", "",
                   LICENSE_MESSAGE, "",
                   "The linked sources provide the applicable terms for the tools and models."])
    readme.extend(f"- [{author}]({url})" for author, url in CREDITS.items())
    try:
        with ZipFile(partial, "w", ZIP_DEFLATED, compresslevel=1) as zipfile:
            zipfile.writestr("README.md", "\n".join(readme) + "\n")
            for name in files:
                zipfile.write(owned_path(output_root, directory / name), name)
        with ZipFile(partial) as zipfile:
            if zipfile.testzip():
                raise ValueError("The aligned pair archive could not be verified.")
        partial.replace(archive)
    finally:
        partial.unlink(missing_ok=True)
    return archive
