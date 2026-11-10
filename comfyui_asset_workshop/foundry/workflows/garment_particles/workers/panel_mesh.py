"""Mesh the authors' sewn panel pattern with its original UV layout."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np
import trimesh

from worker import configure_upstream


def mesh_pattern(pattern, output, author_root, budget):
    configure_upstream(author_root / "external" / "GarmentCodeRC")
    from pygarment.meshgen.boxmeshgen import BoxMesh

    spacing = 1.6
    for _ in range(4):
        mesh = BoxMesh(pattern, res=spacing)
        mesh.load()
        triangles = len(mesh.faces)
        if not mesh.vertices or not triangles:
            raise ValueError("No polygon mesh could be sewn from this pattern.")
        if triangles <= budget:
            break
        spacing *= max(1.12, (triangles / budget) ** .5 * 1.08)
    else:
        raise ValueError("This pattern needs more triangles to preserve its panels and seams. Increase the triangle budget.")

    mesh.paths = SimpleNamespace(g_box_mesh=output / "sewn-garment.obj", g_texture=output / "pattern-atlas.png",
                                 g_texture_fabric=output / "fabric-atlas.png", g_mtl=output / "sewn-garment.mtl",
                                 g_texture_replace=None, g_texture_fabric_replace=None)
    mesh.save_box_mesh_obj(in_uv_config={"dpi": 75})
    with TemporaryDirectory(prefix="foundry-attachments-") as temporary:
        mesh.paths.g_vert_labels = Path(temporary) / "labels.yaml"
        mesh.save_vertex_labels()
    attachments = {label: sorted({int(index) for index in indices})
                   for label, indices in mesh.vertex_labels.items()}
    (output / "pattern-attachments.json").write_text(json.dumps(attachments), encoding="utf-8")
    scene = trimesh.load_scene(mesh.paths.g_box_mesh, process=False)
    for part in scene.geometry.values():
        uv = getattr(part.visual, "uv", None)
        if not np.isfinite(part.vertices).all() or uv is None or not np.isfinite(uv).all():
            raise ValueError("The sewn mesh has invalid vertices or missing UVs.")
    # GarmentCode stores pattern coordinates in centimeters. glTF uses meters.
    scene.apply_scale(.01)
    scene.export(output / "sewn-garment.glb")
    result = {"triangles": sum(len(part.faces) for part in scene.geometry.values()),
              "vertices": sum(len(part.vertices) for part in scene.geometry.values()),
              "panels": len(mesh.panels), "seams": len(mesh.stitches), "triangle_budget": budget,
              "panel_spacing_cm": spacing, "dimensions_m": scene.extents.tolist(),
              "format": "glTF 2.0", "units": "meters", "geometry": "sewn polygon panels"}
    if not 0 < result["triangles"] <= budget:
        raise ValueError("The exported mesh exceeded the selected triangle budget.")
    (output / "mesh-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--author-root", type=Path, required=True)
    parser.add_argument("--budget", type=int, required=True)
    args = parser.parse_args()
    mesh_pattern(args.pattern.resolve(), args.output.resolve(), args.author_root.resolve(), args.budget)

