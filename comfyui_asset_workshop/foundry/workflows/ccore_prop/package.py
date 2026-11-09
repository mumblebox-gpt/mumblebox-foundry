"""Publish the exact checked prop through Foundry's existing package catalog."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

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
        resources = [registry[key] for key in ("ccore_prop", "ccore_three", "ccore_llama", "ccore_playwright")]
        relative = "Prop/prop.glb"
        files = [FileRecord(relative, "mesh", "prop", "Self-contained GLB exported by the generated scene.", "glb", "primary"),
                 FileRecord("Metadata/manifest.json", "metadata", None, "File inventory, provenance and validation.", "json", "catalog")]
        for resource in resources:
            for name in resource["notices"]:
                target = root / "Licenses" / name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(PACK / "licenses/pipeline" / name, target)
                files.append(FileRecord("Licenses/" + name, "license", None,
                                        resource["name"] + " license.", "txt", "notice"))
        audit = ValidationRecord("Embedded GLB and visible triangles", "pass", relative, digest(model),
                                 "Foundry GLB structure, resource and scene bounds check")
        variant = VariantRecord("prop", "Prop/", "A procedural prop generated from text by CCORE.",
                                intended_use="Review and import into a GLB-capable 3D editor or game engine.",
                                file_paths=[relative], measurements={"geometry": measurements},
                                validations=[audit],
                                limitations=["Engine-specific import, topology, UV layout and collision were not certified."])
        production = {"method": "ccore-prop/v1", "workflow_title": "Create a Prop from Text · CCORE",
                      "settings": {key: run["config"][key] for key in ("seed", "max_tokens")}}
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
