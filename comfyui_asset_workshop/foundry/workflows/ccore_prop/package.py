"""Publish the exact checked prop through Foundry's existing package catalog."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from .contract import IMAGE_MODE, MODEL_KEYS, PROJECTOR_KEY, STANDARD_MODEL
from ... import VERSION
from ...artifacts import digest
from ....finishing.package_archive import publish_archive, validate_archive
from ....finishing.package_catalog import FileRecord, ValidationRecord, VariantRecord, build_catalog

PACK = Path(__file__).resolve().parents[3]


def publish(model, measurements, run, library, check):
    root = model.parent.parent
    archive = root.with_suffix(".zip")
    if not archive.exists():
        registry = json.loads((PACK / "finishing/package_resources.json").read_text(encoding="utf-8"))
        from ....recipes import MODELS

        variant_id = run["config"].get("model_variant", STANDARD_MODEL)
        checkpoint = MODELS[MODEL_KEYS[variant_id]]
        precision = variant_id.upper()
        resource = dict(registry["ccore_prop"], id=MODEL_KEYS[variant_id],
                        name=f"CCORE GLB-3D-Coder (Qwen3.5-4B, {precision})",
                        version=checkpoint["revision"],
                        source=f"https://huggingface.co/{checkpoint['repo']}/blob/{checkpoint['revision']}/{checkpoint['file']}",
                        license_url=checkpoint["license_url"],
                        license_summary=f"Official {precision} weights by CCORE, based on Qwen3.5-4B.")
        resources = [resource] + [registry[key] for key in ("ccore_three", "ccore_llama", "ccore_playwright")]
        with_image = run["config"].get("mode") == IMAGE_MODE
        if with_image:
            resources.append(registry[PROJECTOR_KEY])
        relative = "Prop/prop.glb"
        files = [FileRecord(relative, "mesh", "prop", "Self-contained GLB exported by the generated scene.", "glb", "primary"),
                 FileRecord("Metadata/manifest.json", "metadata", None, "File inventory, provenance and validation.", "json", "catalog")]
        for resource in resources:
            for name in resource["notices"]:
                if any(file.path == "Licenses/" + name for file in files):
                    continue
                target = root / "Licenses" / name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(PACK / "licenses/pipeline" / name, target)
                files.append(FileRecord("Licenses/" + name, "license", None,
                                        resource["name"] + " license.", "txt", "notice"))
        audit = ValidationRecord("Embedded GLB and visible triangles", "pass", relative, digest(model),
                                 "Foundry GLB structure, resource and scene bounds check")
        source = "one reference image and text" if with_image else "text"
        variant = VariantRecord("prop", "Prop/", f"A procedural prop generated from {source} by CCORE.",
                                intended_use="Review and import into a GLB-capable 3D editor or game engine.",
                                file_paths=[relative], measurements={"geometry": measurements},
                                validations=[audit],
                                limitations=["Engine-specific import, topology, UV layout and collision were not certified."])
        production = {"method": "ccore-prop/v1", "workflow_title": "Create a Prop from Text · CCORE",
                      "settings": {"seed": run["config"]["seed"], "max_tokens": run["config"]["max_tokens"],
                                   "model_variant": variant_id, "checkpoint_sha256": checkpoint["sha256"]}}
        if with_image:
            production.update(method="ccore-image-text/v1", workflow_title="Create a Prop from Image + Text · CCORE")
            production["settings"].update(projector_sha256=MODELS[PROJECTOR_KEY]["sha256"],
                                          prepared_reference_sha256=run["prepared_reference_sha256"])
        catalog = build_catalog(files, [variant], resources,
                                dict(name="Mumblebox 3D Asset Foundry",
                                     description="A curated toolbox of model-powered creative workflows.",
                                     github_url="https://github.com/mumblebox-gpt/mumblebox-foundry"),
                                dict(asset_name=run["config"]["name"], export_id=run["id"],
                                     created_utc=datetime.now(timezone.utc).isoformat(),
                                     workflow_version=VERSION, production=production))
        publish_archive(catalog, root, archive, check)
    else:
        validate_archive(archive)
    return archive, library.import_package(archive)["id"]
