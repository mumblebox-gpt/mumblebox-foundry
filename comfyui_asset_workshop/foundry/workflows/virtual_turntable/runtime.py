"""Resolve independently installed, qualified photogrammetry tools."""
import json
import os
from pathlib import Path

MESHROOM = "2025.1.0"
COLMAP = "4.2.1"
OPENMVS = "2.4.0"
TEXTURE_REVISION = "14ad2571aac650bfabf54296d31aabed7a19fdde"
TOOLS = {
    "meshroom": {"meshroom_batch": "Meshroom-2025.1.0/meshroom_batch.exe"},
    "colmap-openmvs": {
        "colmap": "COLMAP-4.2.1/bin/colmap.exe",
        "openmvs": "OpenMVS-2.4.0-CUDA",
        "openmvs_texture": "OpenMVS-develop-14ad2571/vc18/x64/Release/TextureMesh.exe",
    },
}
SOURCES = {
    "meshroom": "https://github.com/alicevision/Meshroom/releases/tag/v2025.1.0",
    "colmap-openmvs": "https://github.com/cdcseacave/openMVS/releases/tag/v2.4.0",
}


def runtime_settings():
    # The standalone installs used versioned directories. Allow the host to
    # point at another drive or specify individual executable paths.
    tools = Path(os.environ.get("MUMBLEBOX_PHOTOGRAMMETRY_TOOLS", os.environ.get("SystemDrive", "C:") + "/Tools"))
    settings = {
        key: str(tools / relative) for group in TOOLS.values() for key, relative in group.items()
    }
    path = os.environ.get("MUMBLEBOX_PHOTOGRAMMETRY_CONFIG")
    if path:
        override = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(override, dict) or set(override) - set(settings):
            raise ValueError("The Virtual Turntable runtime configuration contains an unknown path key.")
        for key, value in override.items():
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError(f"Use an absolute path for {key}.")
        settings.update(override)
    return dict(settings, version=MESHROOM, alicevision="3.3.0", colmap_version=COLMAP,
                openmvs_version=OPENMVS, openmvs_texture_revision=TEXTURE_REVISION,
                openmvs_texture_cuda=False)


def missing(engine):
    settings = runtime_settings()
    paths = [Path(settings[key]) for key in TOOLS[engine] if key != "openmvs"]
    if engine == "colmap-openmvs":
        paths.extend(Path(settings["openmvs"]) / (name + ".exe") for name in
                     ("InterfaceCOLMAP", "DensifyPointCloud", "ReconstructMesh", "RefineMesh"))
    return [path.name for path in paths if not path.is_file()]
