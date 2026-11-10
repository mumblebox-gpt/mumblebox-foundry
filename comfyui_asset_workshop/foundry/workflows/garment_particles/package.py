"""Catalog the author pattern, point preview and prepared polygon files."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

from ... import VERSION
from ....finishing.package_archive import publish_archive
from ....finishing.package_catalog import FileRecord, VariantRecord, build_catalog
from .contract import AUTHOR, WEIGHTS

AUTHOR_REVISION = "2a058b9aa896e931311b4ad8bb960516f98ef368"
WEIGHTS_REVISION = "2c463e6cc48cb3263d1e0e1e052a3ec0fc760db6"
ORIGINALS = {
    "garment_pattern.png": ("preview", "Sewing sheet with panel labels and seam markings."),
    "garment_pattern.svg": ("pattern", "Vector sewing sheet."),
    "garment_3d_pattern.png": ("preview", "The authors’ 3D panel placement sheet."),
    "garment_specification.json": ("pattern", "Editable GarmentCode pattern and stitches."),
    "drape-particles.glb": ("preview", "Rotatable 3D point drape."),
    "drape-particles.ply": ("geometry", "Colored 3D garment points."),
    "particles.npz": ("data", "Original model points and edge predictions."),
    "receipt.json": ("metadata", "Generation settings, timing and GPU allocation."),
}
MESH_FILES = {
    "sewn-garment.glb": ("mesh", "UV-mapped sewn panels in meters."),
    "sewn-garment.obj": ("mesh", "Original GarmentCodeRC polygon mesh in centimeters."),
    "sewn-garment.mtl": ("material", "Material definitions for the OBJ."),
    "pattern-atlas.png": ("texture", "Pattern UV atlas."),
    "fabric-atlas.png": ("texture", "Fabric atlas for the OBJ."),
    "mesh-report.json": ("metadata", "Triangle count, UVs and mesh measurements."),
}
DRAPE_FILES = {
    "draped-garment.glb": ("mesh", "UV-mapped garment settled on the rest-pose character with Blender Cloth."),
    "draped-fit.glb": ("preview", "Settled garment, translucent body and clipping marks."),
    "starting-fit.glb": ("preview", "Starting garment placement and pre-simulation clipping."),
    "drape-report.json": ("metadata", "Solver settings, measured movement and penetration before and after simulation."),
}
RIG_FILES = {
    "wearable.glb": ("mesh", "Skinned wearable and its armature."),
    "wearable.fbx": ("mesh", "Skinned wearable for FBX-compatible editors."),
    "fit-report.json": ("metadata", "Rest fit, skin weights and sampled pose checks."),
}


def publish(run, source, mesh, rig, library, check, *, drape=None):
    export_id = uuid4().hex
    root = source.parent / "packages" / export_id
    root.mkdir(parents=True)
    files = [FileRecord("Metadata/manifest.json", "metadata", None, "File inventory and provenance.", "json", "catalog")]
    variants = []
    groups = [
        ("pattern", "Pattern", source, ORIGINALS, "Editable sewing pattern and model-predicted drape reference.",
         "A design reference for garment construction and tailoring.",
         ["The drape is a point cloud. The sewing pattern is inferred from the design."]),
    ]
    if mesh:
        groups.append(("sewn", "SewnMesh", mesh, MESH_FILES, "UV-mapped polygon panels.",
                       "A Blender starting mesh for tailoring, simulation and rigging.",
                       ["The mesh uses the authors’ initial panel placement and can sit loosely on a character."]))
    if drape:
        groups.append(("draped", "Draped", drape, DRAPE_FILES, "Cloth simulation on the target rest-pose body.",
                       "Optional cloth preview for checking placement and clipping.",
                       ["The report covers one rest pose. Fabric can hang loosely even with zero detected clipping."]))
    if rig:
        groups.append(("wearable", "Wearable", rig, RIG_FILES, "Skinned wearable with sampled fit checks.",
                       "Experimental weight transfer for further fit and rigging work.",
                       ["The report covers sampled poses. Tailoring and weight cleanup may be needed."]))
    for key, folder, origin, entries, title, use, limits in groups:
        (root / folder).mkdir()
        paths = []
        for name, (role, description) in entries.items():
            check()
            candidate = origin / name
            if not candidate.is_file():
                raise ValueError(f"The garment package is missing {name}. Rebuild the corresponding stage.")
            relative = f"{folder}/{name}"
            shutil.copyfile(candidate, root / relative)
            files.append(FileRecord(relative, role, key, description, candidate.suffix[1:], "primary"))
            paths.append(relative)
        variants.append(VariantRecord(key, folder + "/", title, intended_use=use, file_paths=paths, limitations=limits))
    registry = [dict(id="garment_particles", name="Garment Particles", version=AUTHOR_REVISION,
                     source=AUTHOR, license_url=AUTHOR + "/blob/" + AUTHOR_REVISION + "/LICENSE",
                     license_summary="Garment Particles by Kiyohiro Nakayama and collaborators. Original generator, guided editing, sewing-pattern reconstruction and public checkpoints.",
                     notices=[])]
    production = dict(method="garment-particles/v1", workflow_title="Create Clothing with Garment Particles",
                      settings={key: run["config"][key] for key in ("mode", "seed", "points", "steps")})
    production["settings"].update(weights=WEIGHTS + "/tree/" + WEIGHTS_REVISION)
    if run.get("mesh"):
        production["settings"]["triangle_budget"] = run["mesh"]["triangle_budget"]
    if run.get("edit"):
        production["settings"]["author_edit"] = run["edit"]
        production["settings"]["parent_revision"] = run["parent"]
    if run.get("drape"):
        production["settings"]["cloth"] = {key: run["drape"][key] for key in ("solver", "blender", "fabric", "frames")}
    warnings = []
    if (run.get("rig") or {}).get("needs_review") or (run.get("drape") or {}).get("needs_review"):
        warnings.append("The target fit needs review. Open the fit report and check the garment on your character before shipping.")
    catalog = build_catalog(files, variants, registry,
                            dict(name="Mumblebox 3D Asset Foundry",
                                 description="A curated toolbox of local asset workflows.",
                                 github_url="https://github.com/mumblebox-gpt/mumblebox-foundry"),
                            dict(asset_name=run["config"]["name"], export_id=export_id,
                                 created_utc=datetime.now(timezone.utc).isoformat(),
                                 workflow_version=VERSION, production=production, warnings=warnings))
    archive = publish_archive(catalog, root, root.with_suffix(".zip"), check)
    return archive, library.import_package(archive)["id"]

