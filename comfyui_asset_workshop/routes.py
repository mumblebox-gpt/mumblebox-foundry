"""Local, explicit stage actions for the visible Comfy Desktop controls."""

import asyncio
import functools
import io
import json
import math
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlencode

import psutil
import torch
from aiohttp import web
from PIL import Image, ImageOps

import comfy.model_management as memory
import execution
import folder_paths
from comfy.cli_args import args, enables_dynamic_vram
from server import PromptServer

from . import models, recipes, description_helper, memory_policy, hf_auth, image_edits, foreground, prompt_contracts
from .profiles import PROFILES, ORBIT8, ORBIT12, angle_asset, camera_prompt
from .runtime import configuration, set_root, store, request_startup_headroom
from .store import LOCK, atomic_json, contained, digest, identifier, MESH_DEFAULTS, ProjectConflict, JobConflict, ApprovalRequired
from .resource_lifecycle import ResourceLifecycle

ROUTES = PromptServer.instance.routes
PREFIX = "/asset-workshop"


def endpoint(function):
    @functools.wraps(function)
    async def wrapped(request):
        # Same-origin desktop controls. No arbitrary remote website can mutate the library.
        origin = request.headers.get("Origin")
        if request.path.startswith(PREFIX + "/v2") and request.remote not in ("127.0.0.1", "::1"):
            return web.json_response({"error": "The single-image agent API is available on this computer only."}, status=403)
        if origin and urlsplit(origin).netloc != request.host:
            return web.json_response({"error": "Use the controls in this ComfyUI instance."}, status=403)
        try:
            return await function(request)
        except (ProjectConflict, JobConflict, ApprovalRequired) as error:
            return web.json_response({"error": str(error), "type": type(error).__name__}, status=409)
        except (ValueError, KeyError, StopIteration, FileNotFoundError) as error:
            return web.json_response({"error": str(error)}, status=400)
        except Exception as error:
            return web.json_response({"error": f"{type(error).__name__}: {error}"}, status=500)
    return wrapped


def queue():
    return PromptServer.instance.prompt_queue


def resource_sample():
    ram = psutil.virtual_memory()
    device = memory.get_torch_device()
    cuda = device.type == "cuda"
    free, total = torch.cuda.mem_get_info(device) if cuda else (0, 0)
    return {"process_rss": psutil.Process().memory_info().rss,
            "ram_used": ram.total - ram.available, "ram_available": ram.available,
            "vram_used": total - free, "vram_available": free,
            "torch_allocated": torch.cuda.memory_allocated(device) if cuda else 0,
            "torch_reserved": torch.cuda.memory_reserved(device) if cuda else 0,
            "loaded_models": len(memory.current_loaded_models)}


def record_resources(owner, report):
    with LOCK:
        library = store()
        asset = library.load(owner[0])
        job = next(j for j in asset["jobs"] if j["id"] == owner[1])
        job["resources"] = report
        library.save(asset)


RESOURCE_LIFECYCLE = None
_METER_CACHE = (0, {})

def meter_sample():
    """One bounded hardware sample shared by all GUI clients for half a second."""
    global _METER_CACHE
    now=time.monotonic()
    if now-_METER_CACHE[0]<.5:return _METER_CACHE[1]
    ram=psutil.virtual_memory()
    device=memory.get_torch_device()
    free,total=torch.cuda.mem_get_info(device) if device.type=='cuda' else (0,0)
    value={'sampled_at':time.time(),'cpu_percent':psutil.cpu_percent(interval=None),
           'ram_total':ram.total,'ram_used':ram.total-ram.available,
           'vram_total':int(total),'vram_used':int(total-free)}
    _METER_CACHE=(now,value)
    return value


def resources():
    global RESOURCE_LIFECYCLE
    if RESOURCE_LIFECYCLE is None:
        RESOURCE_LIFECYCLE = ResourceLifecycle(queue(), resource_sample, record_resources)
    return RESOURCE_LIFECYCLE


def idle():
    if queue().get_tasks_remaining():
        raise ValueError("Another Comfy job is queued or running. Wait for it to finish.")
    from .foundry.workflows.image_to_3d.runs import busy as foundry_busy
    from .foundry.workflows.image_creation.runs import busy as image_busy
    from .foundry.workflows.hair_creation.runs import busy as hair_busy
    from .foundry.workflows.guided_mesh.runs import busy as guided_busy
    from .foundry.workflows.splat_solid.runs import busy as splat_busy
    if single_image_jobs_active() or foundry_busy() or image_busy() or hair_busy() or guided_busy() or splat_busy():
        raise JobConflict("A Mumblebox job is still active. Wait for it to finish or stop it before changing the library or History.")
    if description_helper.STATE.get("running"):
        raise ValueError("The description assistant is working. Wait for it or stop it before generating an image.")


def reconcile(asset):
    """Recover interrupted jobs after a reboot without touching another job."""
    if asset.get("schema_version") == 2:
        return asset
    changed = False
    running, pending = queue().get_current_queue_volatile()
    active = {item[1] for item in running + pending}
    for job in asset["jobs"]:
        prompt_id = job.get("prompt_id")
        if job["status"] == "complete" and prompt_id and "preview_files" not in job and prompt_id not in active:
            history = queue().get_history(prompt_id).get(prompt_id)
            if history:
                owned = []
                for output in history.get("outputs", {}).values():
                    for entry in output.get("images", []) + output.get("3d", []):
                        if not isinstance(entry, dict) or entry.get("type") != "temp":
                            continue
                        relative = str(Path(entry.get("subfolder", "")) / entry["filename"])
                        path = contained(folder_paths.get_temp_directory(), relative)
                        if path.is_file():
                            stat = path.stat()
                            owned.append({"relative": relative, "size": stat.st_size, "mtime": stat.st_mtime_ns})
                job["preview_files"] = owned
                changed = True
        if job["status"] not in ("queued", "running", "preparing"):
            continue
        if prompt_id in active:
            continue
        if prompt_id:
            history = queue().get_history(prompt_id).get(prompt_id)
            if history:
                status = history.get("status") or {}
                if status.get("completed") or status.get("status_str") == "error":
                    # Output nodes mark success themselves. A failed output is never reported as success.
                    job["status"] = "failed"
                    messages = status.get("messages") or []
                    errors = [m[1].get("exception_message", m[1].get("node_type", "")) for m in messages
                              if len(m) == 2 and m[0] == "execution_error"]
                    job["error"] = "; ".join(errors) or "Execution ended without its saved output. Resume this stage."
                    changed = True
                    continue
        if time.time() - job["created"] > 120:
            job.update(status="interrupted", error="Job was not completed. Saved revisions and masters remain available; run the stage again.")
            changed = True
    if changed:
        store().save(asset)
    return asset


@ROUTES.get(PREFIX + "/status")
@endpoint
async def status(request):
    from .civitai_routes import DOWNLOADS
    from .pipeline_workers.activity import snapshot as worker_snapshot, host_residency
    from .foundry.cache import busy as maintenance_busy
    workers=worker_snapshot()
    residencies=host_residency(list(memory.current_loaded_models))+workers
    workflow_activity=[]
    for name in ('image_to_3d','image_creation','hair_creation','splat_solid'):
        owner=__import__(__package__+'.foundry.workflows.'+name+'.runs',fromlist=['ACTIVE']).ACTIVE
        if owner:
            for ident in list(owner.tasks):
                run=(owner.runs if name=='image_to_3d' else owner.records).get(ident,{})
                workflow_activity.append({'workflow':name,'stage':run.get('stage'), 'dependency':run.get('dependency')})
    library_path = Path(configuration()["root"])
    while not library_path.exists():
        library_path = library_path.parent
    disk = shutil.disk_usage(library_path)
    return web.json_response({
        **meter_sample(),
        "model_residency":residencies,
        "workflow_activity":workflow_activity,
        "maintenance_active":maintenance_busy(),
        "loaded_models": len(memory.current_loaded_models),
        "helper_loaded": description_helper.PROCESS is not None and description_helper.PROCESS.poll() is None,
        "running": queue().get_tasks_remaining() > 0 or any(__import__(__package__+".foundry.workflows."+name+".runs",fromlist=["busy"]).busy() for name in ('image_to_3d','image_creation','hair_creation','guided_mesh','splat_solid')), "root": configuration()["root"],
        "download": dict(models.DOWNLOAD), "profiles": PROFILES,
        "resource_download": DOWNLOADS.status(),
        "startup_vram_reserve_gb": memory.extra_reserved_memory() / 1024**3,
        "startup_vram_headroom_gb": args.vram_headroom,
        "pending_vram_headroom_gb": configuration().get("pending_vram_headroom_gb", args.vram_headroom),
        "dynamic_vram_requested": enables_dynamic_vram(), "disk_free": disk.free,
        "description_helper": dict(description_helper.STATE),
        "resource_cleanup": resources().status(),
        "interface_version": 10, "mesh_defaults": MESH_DEFAULTS,
        "hardware": memory_policy.hardware_info(),
        "hugging_face": hf_auth.status(),
        "models_directory": str(models.MODEL_ROOT),
    },headers={"Cache-Control":"no-store"})


@ROUTES.post(PREFIX + "/hugging-face")
@endpoint
async def hugging_face_connection(request):
    body = await request.json()
    action = body.get("action")
    if action in ("connect", "disconnect") and models.DOWNLOAD.get("status") == "running":
        raise ValueError("Wait for the model download to finish before changing its connection.")
    if action == "connect":
        result = await asyncio.to_thread(hf_auth.connect, body.get("token"))
    elif action == "test":
        result = await asyncio.to_thread(hf_auth.test_connection)
    elif action == "disconnect":
        result = await asyncio.to_thread(hf_auth.disconnect)
    else:
        raise ValueError("Choose Connect, Test connection or Disconnect.")
    return web.json_response(result, headers={"Cache-Control": "no-store"})


@ROUTES.get(PREFIX + "/loras")
@endpoint
async def loras(request):
    return web.json_response({
        "folders": folder_paths.get_folder_paths("loras"),
        "files": sorted(folder_paths.get_filename_list("loras")),
    })


@ROUTES.post(PREFIX + "/open-folder")
@endpoint
async def open_folder(request):
    body = await request.json()
    kind = body.get("kind")
    if kind == "loras":
        folders = folder_paths.get_folder_paths("loras")
        if not folders:
            raise ValueError("No LoRA folder is configured in ComfyUI.")
        path = Path(folders[0])
    elif kind == "library":
        path = Path(configuration()["root"])
    elif kind == "asset":
        asset = store().load(body["asset"])
        path = store().assets / asset["id"]
    else:
        raise ValueError("Choose the library, current asset or LoRA folder.")
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return web.json_response({"opened": str(path)})


@ROUTES.post(PREFIX + "/assets/{asset}/describe")
@endpoint
async def describe_asset(request):
    idle()
    body = await request.json()
    asset = store().load(request.match_info["asset"])
    action = body.get("action")
    if action not in ("describe", "enhance"):
        raise ValueError("Choose Auto describe or Enhance description.")
    # Claim synchronously before yielding so two callers cannot start assistants.
    description_helper.claim(asset["id"])
    try:
        await resources().barrier()
        await resources().release("before description assistant")
        text = await asyncio.to_thread(description_helper.generate, asset, action)
        has_images=bool(asset.get("initial",{}).get("current") or (action=="enhance" and any(r.get("enabled",True) for r in asset["references"])))
        contract=prompt_contracts.contract(asset["profile"],action,has_images,asset.get("category","props"))
        public_contract={key:value for key,value in contract.items() if key!="instruction"}
        record=await asyncio.to_thread(store().record_description,asset,action,text,public_contract)
        return web.json_response({"text":text,"suggestion_id":record["id"],"contract":public_contract})
    finally:
        description_helper.release()
        if not queue().get_tasks_remaining():
            await resources().release("description assistant finished")


@ROUTES.post(PREFIX + "/assets/{asset}/descriptions/{suggestion}/accept")
@endpoint
async def accept_description(request):
    idle()
    body=await request.json()
    asset=store().accept_description(request.match_info["asset"],request.match_info["suggestion"],body.get("text"))
    return web.json_response(asset)


@ROUTES.get(PREFIX + "/assets")
@endpoint
async def list_assets(request):
    return web.json_response(await asyncio.to_thread(store().list_assets))


@ROUTES.post(PREFIX + "/assets")
@endpoint
async def create_asset(request):
    body = await request.json()
    library=store()
    asset=library.create(body.get("name", "Untitled asset"))
    return web.json_response(library.save(memory_policy.apply_policy(asset)))


@ROUTES.get(PREFIX + "/assets/{asset}")
@endpoint
async def get_asset(request):
    with LOCK:
        asset = reconcile(store().load(request.match_info["asset"]))
    return web.json_response(asset)


@ROUTES.patch(PREFIX + "/assets/{asset}")
@endpoint
async def update_asset(request):
    patch = await request.json()
    with LOCK:
        library=store()
        asset=library.update(request.match_info["asset"], patch)
        return web.json_response(library.save(memory_policy.apply_policy(asset)))


@ROUTES.get(PREFIX + "/assets/{asset}/memory")
@endpoint
async def asset_memory(request):
    asset=store().load(request.match_info["asset"])
    if "profile" in request.query:
        profile=request.query["profile"]
        if profile not in PROFILES: raise ValueError("Unknown image model.")
        asset["profile"]=profile
    return web.json_response(memory_policy.inspect_policy(asset))


@ROUTES.get(PREFIX + "/memory")
@endpoint
async def default_memory(request):
    profile=request.query.get("profile","qwen21")
    if profile not in PROFILES: raise ValueError("Unknown image model.")
    return web.json_response(memory_policy.inspect_policy({"profile":profile,"settings":{"memory_overrides":[]}}))


@ROUTES.get(PREFIX + "/assets/{asset}/history")
@endpoint
async def asset_history(request):
    offset=max(0,int(request.query.get("offset","0")))
    limit=min(24,max(1,int(request.query.get("limit","12"))))
    return web.json_response(await asyncio.to_thread(store().history,request.match_info["asset"],offset,limit))


@ROUTES.post(PREFIX + "/assets/{asset}/restore")
@endpoint
async def restore_generation(request):
    idle()
    body=await request.json()
    return web.json_response(store().restore_generation(request.match_info["asset"],body["job"]))


@ROUTES.delete(PREFIX + "/assets/{asset}")
@endpoint
async def delete_asset(request):
    idle()
    if models.DOWNLOAD["status"]=="running":
        raise ValueError("Wait for the current download before deleting an asset.")
    return web.json_response(store().trash_asset(request.match_info["asset"]))


@ROUTES.post(PREFIX + "/trash/{token}/restore")
@endpoint
async def undo_delete(request):
    idle()
    return web.json_response(store().undo_delete(request.match_info["token"]))


@ROUTES.post(PREFIX + "/history/clear")
@endpoint
async def clear_history(request):
    idle()
    if models.DOWNLOAD["status"] == "running":
        raise ValueError("Wait for the current download before clearing History.")
    body = await request.json()
    return web.json_response(store().clear_history(body.get("assets")))


@ROUTES.post(PREFIX + "/root")
@endpoint
async def root(request):
    idle()
    if models.DOWNLOAD["status"] == "running":
        raise ValueError("Wait for the download before changing libraries.")
    body = await request.json()
    return web.json_response(set_root(body["root"]))


@ROUTES.post(PREFIX + "/startup-headroom")
@endpoint
async def startup_headroom(request):
    body = await request.json()
    return web.json_response(request_startup_headroom(body["gb"]))


@ROUTES.get(PREFIX + "/file/{asset}")
@endpoint
async def file(request):
    path = store().path(request.match_info["asset"], request.query["path"])
    if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".glb", ".stl", ".json"):
        raise ValueError("This file type is not exposed by the asset viewer.")
    if not path.is_file():
        raise FileNotFoundError("The saved asset file is missing.")
    return web.FileResponse(path)


@ROUTES.post(PREFIX + "/assets/{asset}/preview")
@endpoint
async def preview_asset(request):
    body = await request.json()
    library = store()
    asset = library.load(request.match_info["asset"])
    collection, output_id = ("drafts", body["draft"]) if "draft" in body else ("exports", body["export"])
    if asset.get("schema_version") == 2:
        collection = "artifacts"
    output = next(item for item in asset[collection] if item["id"] == output_id)
    if asset.get("schema_version") == 2 and output.get("kind") not in ("mesh","geometry"):
        raise ValueError("Choose an exported mesh for the 3D preview.")
    path = library.path(asset["id"], output.get("preview_file",output["file"]))
    expected = output.get("preview_sha256",output.get("sha256"))
    if expected and digest(path)!=expected:raise ValueError("Preview file changed on disk")
    output_root = Path(folder_paths.get_output_directory()).resolve()
    if path.is_relative_to(output_root):
        relative, kind = path.relative_to(output_root), "output"
    else:
        # Native Comfy viewer loads only registered input/temp/output files.
        # Cache one known GLB when the user's library lives outside those roots.
        temp_root = Path(folder_paths.get_temp_directory()).resolve()
        directory = contained(temp_root, f"mumblebox-preview/{asset['id']}")
        directory.mkdir(parents=True, exist_ok=True)
        target = contained(directory, identifier(output["id"]) + ".glb")
        marker = directory / "owner.json"
        previous = json.loads(marker.read_text()) if marker.is_file() else {}
        if not target.is_file() or target.stat().st_size != path.stat().st_size:
            shutil.copyfile(path, target)
        if previous.get("owner") == "mumblebox-preview" and previous.get("file") != target.name:
            old = contained(directory, previous["file"])
            if old.suffix == ".glb":
                old.unlink(missing_ok=True)
        atomic_json(marker, {"owner": "mumblebox-preview", "file": target.name})
        relative, kind = target.relative_to(temp_root), "temp"
    return web.json_response({"url": "/view?" + urlencode({
        "filename": relative.name, "subfolder": relative.parent.as_posix(), "type": kind,
    })})


@ROUTES.post(PREFIX + "/assets/{asset}/upload")
@endpoint
async def upload(request):
    asset_id = identifier(request.match_info["asset"])
    reader = await request.multipart()
    data, slot = bytearray(), "references"
    async for part in reader:
        if part.name == "image":
            while chunk := await part.read_chunk(1024 * 1024):
                data.extend(chunk)
                if len(data) > 64 * 1024 * 1024:
                    raise ValueError("An individual input image must be under 64 MB.")
        elif part.name == "slot":
            slot = await part.text()
    if not data:
        raise ValueError("Choose an image file.")
    library = store()
    revision_id = uuid.uuid4().hex[:16]
    identifier(slot)
    with Image.open(io.BytesIO(data)) as original:
        if original.width * original.height > 40_000_000:
            raise ValueError("Resize this reference below 40 megapixels before importing.")
        image = ImageOps.exif_transpose(original).convert("RGBA")
        relative = f"references/{revision_id}.png" if slot == "references" else f"images/{slot}/{revision_id}.png"
        target = library.path(asset_id, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, format="PNG")
    record = {"id": revision_id, "file": relative, "sha256": digest(target), "created": time.time()}
    with LOCK:
        asset = library.load(asset_id)
        if slot == "references":
            asset["references"].append({**record, "role": "design ingredient", "instructions": "", "enabled": True})
            asset["design"]["stale"] = True
            for view in asset["views"]:
                view["stale"] = True
            library.save(asset)
        else:
            library.slot(asset, slot)
            library.add_revision(asset_id, slot, {**record, "recipe": {"source": "user upload"}})
    return web.json_response(record)


@ROUTES.post(PREFIX + "/assets/{asset}/approve")
@endpoint
async def approve(request):
    body = await request.json()
    result = await asyncio.to_thread(store().approve, request.match_info["asset"], body["slot"], body["revision"])
    return web.json_response(result)


@ROUTES.post(PREFIX + "/assets/{asset}/approve-pair")
@endpoint
async def approve_pair(request):
    idle()
    result = await asyncio.to_thread(store().approve_pair, request.match_info["asset"])
    return web.json_response(result)


@ROUTES.post(PREFIX + "/assets/{asset}/edits")
@endpoint
async def create_image_edit(request):
    idle()
    fields, mask = {}, bytearray()
    reader = await request.multipart()
    async for part in reader:
        if part.name == "mask":
            while chunk := await part.read_chunk(1024 * 1024):
                mask.extend(chunk)
                if len(mask) > 16 * 1024 * 1024:
                    raise ValueError("The selection file must be smaller than 16 MB.")
        elif part.name in ("slot", "revision", "prompt", "feather", "replace_detail"):
            value = await part.text()
            if len(value) > 16000:
                raise ValueError("Edit instructions are too long.")
            fields[part.name] = value
    if not mask:
        raise ValueError("Select an area before generating an edit.")
    replace_detail = fields.get("replace_detail", "false")
    if replace_detail not in ("true", "false"):
        raise ValueError("Replace selected details must be true or false.")
    result = await asyncio.to_thread(
        image_edits.create, store(), request.match_info["asset"], fields["slot"],
        fields["revision"], fields["prompt"], bytes(mask), fields.get("feather", 0),
        replace_detail == "true")
    return web.json_response(result)


@ROUTES.post(PREFIX + "/assets/{asset}/edits/accept")
@endpoint
async def accept_image_edit(request):
    idle()
    body = await request.json()
    result = await asyncio.to_thread(image_edits.accept, store(), request.match_info["asset"],
                                     body["slot"], body["revision"])
    return web.json_response(result)


@ROUTES.post(PREFIX + "/assets/{asset}/foreground")
@endpoint
async def foreground_preview(request):
    idle()
    fields, payload = {}, bytearray()
    reader = await request.multipart()
    async for part in reader:
        if part.name == "mask":
            while chunk := await part.read_chunk(1024 * 1024):
                payload.extend(chunk)
                if len(payload) > 16 * 1024 * 1024:
                    raise ValueError("The mask must be smaller than 16 MB.")
        elif part.name in ("slot", "revision", "feather"):
            fields[part.name] = await part.text()
            if len(fields[part.name]) > 128:
                raise ValueError("Invalid foreground settings.")
    if not payload:
        raise ValueError("Select the object to keep before previewing the cutout.")
    def make_preview():
        with Image.open(io.BytesIO(payload)) as mask:
            if mask.width*mask.height > 40_000_000:
                raise ValueError("The mask must be below 40 megapixels.")
            return foreground.create(store(), request.match_info["asset"], fields["slot"],
                                     fields["revision"], mask, origin="manual",
                                     feather=int(fields.get("feather", 0)))
    return web.json_response(await asyncio.to_thread(make_preview))


@ROUTES.post(PREFIX + "/assets/{asset}/foreground/accept")
@endpoint
async def accept_foreground(request):
    idle()
    body = await request.json()
    result = await asyncio.to_thread(foreground.accept, store(), request.match_info["asset"],
                                     body["slot"], body["candidate"])
    return web.json_response(result)


@ROUTES.post(PREFIX + "/assets/{asset}/approve-draft")
@endpoint
async def approve_draft(request):
    idle()
    body = await request.json()
    with LOCK:
        library = store()
        asset = library.load(request.match_info["asset"])
        draft = next(item for item in asset["drafts"] if item["id"] == body["draft"])
        if draft.get("stale") or draft["dependencies"] != recipes.draft_inputs(asset):
            raise ValueError("The source images or masks changed. Build a fresh draft before using its shape.")
        if digest(library.path(asset["id"], draft["file"])) != draft["sha256"]:
            raise ValueError("The saved draft changed on disk. Build it again.")
        for other in asset["drafts"]:
            other["approved"] = other["id"] == draft["id"]
        asset["selected_draft"] = draft["id"]
        library.save(asset)
    return web.json_response(asset)


@ROUTES.post(PREFIX + "/assets/{asset}/approve-master")
@endpoint
async def approve_master(request):
    body = await request.json()
    with LOCK:
        library = store()
        asset = library.load(request.match_info["asset"])
        master = next(m for m in asset["masters"] if m["id"] == body["master"])
        if not any(e["kind"] == "master" and e["master"] == master["id"] for e in asset["exports"]):
            raise ValueError("Build and review the textured master first.")
        for other in asset["masters"]:
            other["approved"] = other["id"] == master["id"]
        library.save(asset)
    return web.json_response(asset)


@ROUTES.post(PREFIX + "/assets/{asset}/camera-preset")
@endpoint
async def camera_preset(request):
    with LOCK:
        library = store()
        asset = library.load(request.match_info["asset"])
        profile = asset["profile"]
        if not PROFILES[profile].get("camera"):
            raise ValueError("This variant has no configured camera LoRA. Approximate text prompts remain available.")
        for view in asset["views"]:
            azimuth, elevation = view["azimuth"], view["elevation"]
            if profile == "qwen21":
                azimuth = min(ORBIT12, key=lambda angle: abs((angle - azimuth + 180) % 360 - 180))
                # Upper rear adds coverage when the trained model lacks an underside pose.
                elevation = min((0, 30, 60, 90), key=lambda angle: abs(angle - elevation)) if elevation >= 0 else 60
                if view["elevation"] < 0:
                    view["name"] = "Upper rear"
            else:
                azimuth = min(ORBIT8, key=lambda angle: abs((angle - azimuth + 180) % 360 - 180))
                elevation = min((-30, 0, 30, 60), key=lambda angle: abs(angle - elevation))
            if azimuth != view["azimuth"] or elevation != view["elevation"]:
                view["stale"] = True
            view.update(azimuth=azimuth, elevation=elevation, camera_source="generated_estimate")
        library.save(asset)
    return web.json_response(asset)


def review_asset(asset):
    library = store()
    messages, fingerprints, dimensions, poses = [], {}, set(), set()
    views = [v for v in asset["views"] if v["enabled"]]
    messages.append(f"{len(views)} views enabled; {sum(bool(v['approved']) for v in views)} accepted.")
    for view in views:
        if not view["approved"]:
            messages.append(f"{view['name']}: needs acceptance.")
            continue
        revision = library.revision(asset, view["id"], approved=True)
        path = library.path(asset["id"], revision["file"])
        with Image.open(path) as image:
            dimensions.add(image.size)
            # A small grayscale descriptor catches near-identical cards, not 3D inconsistency.
            descriptor = tuple(ImageOps.grayscale(image).resize((16, 16)).getdata())
        for other, previous in fingerprints.items():
            if sum(abs(a - b) for a, b in zip(descriptor, previous)) / 256 < 1.5:
                messages.append(f"{view['name']} is very similar to {other}; inspect whether the angle actually changed.")
        fingerprints[view["name"]] = descriptor
        pose = (view["azimuth"], view["elevation"])
        if pose in poses:
            messages.append(f"{view['name']}: duplicate requested camera position.")
        poses.add(pose)
        if asset["settings"].get("camera_lora"):
            try:
                camera_prompt(asset["profile"], view)
            except ValueError as error:
                messages.append(f"{view['name']}: {error}")
        prepared = library.path(asset["id"], f"prepared/{view['id']}/{revision['id']}-pad1.1.png.json")
        if prepared.exists() and json.loads(prepared.read_text()).get("clipped_silhouette"):
            messages.append(f"{view['name']}: object touches the original image border; check for clipped parts.")
    if len(dimensions) > 1:
        messages.append("Canvas sizes differ. Preparation keeps aspect ratio and adds a centered square frame.")
    if not any(el > 0 for _, el in poses):
        messages.append("No accepted upper coverage.")
    if not any(el < 0 for _, el in poses):
        messages.append("No accepted underside coverage. Qwen 2.1's trained camera route does not supply it.")
    messages.append("These checks cannot prove geometric consistency. Inspect silhouettes, counts and proportions before accepting the view set.")
    return {"messages": messages}


@ROUTES.get(PREFIX + "/assets/{asset}/review")
@endpoint
async def review(request):
    return web.json_response(await asyncio.to_thread(review_asset, store().load(request.match_info["asset"])))


@ROUTES.get(PREFIX + "/assets/{asset}/models")
@endpoint
async def model_status(request):
    asset = store().load(request.match_info["asset"])
    return web.json_response(models.status(asset, request.query.get("stage", "image"), request.query.get("camera") == "1",
                                           request.query.get("slot", "design"), request.query.get("action", "generate")))


@ROUTES.post(PREFIX + "/assets/{asset}/download")
@endpoint
async def download(request):
    body = await request.json()
    if body.get("accept_licenses") is not True:
        raise ValueError("Review and accept the displayed model licenses before downloading.")
    asset = store().load(request.match_info["asset"])
    return web.json_response(models.start_download(asset, body.get("stage", "image"), body.get("camera", False),
                                                   body.get("slot", "design"), body.get("action", "generate"),
                                                   retry=body.get("retry") is True))


@ROUTES.post(PREFIX + "/download/pause")
@endpoint
async def pause_download(request):
    models.DOWNLOAD["cancel"] = True
    return web.json_response({"status": "pause requested"})


@ROUTES.post(PREFIX + "/assets/{asset}/prepare")
@endpoint
async def prepare(request):
    idle()
    body = await request.json()
    asset = store().load(request.match_info["asset"])
    stage, slot, action = body["stage"], body.get("slot", "design"), body.get("action", "generate")
    if stage not in ("image", "foreground", "draft", "guide", "prepare", "mesh", "master", "game") or action not in ("generate", "correct", "edit"):
        raise ValueError("Unknown stage action.")
    if stage == "image" and slot not in ("design", "initial", "view_05"):
        if slot == "view_01":
            raise ValueError("Create or replace the front in Step 1, then review the front/back pair.")
        if not recipes.pair_approved(asset):
            raise ValueError("Review and approve the front and back before generating or editing the remaining angles.")
    edit = None
    if action == "edit":
        if stage != "image":
            raise ValueError("Image edits belong to the image stage.")
        edit = image_edits.load(store(), asset, body["edit"], slot)
    if stage == "mesh":
        requested = asset["settings"].get("mesh_requested_seed", -1)
        asset = store().update(asset["id"], {"settings":{"mesh_seed":secrets.randbits(32) if requested == -1 else requested}})
    selected = angle_asset(asset, stage, slot, action)
    if stage == "image":
        recipes.guidance_inputs(selected, slot, action)
    # Reset native execution caches before checking reserves or starting the helper.
    # Unloading only weights leaves cached NAF features/mesh tensors alive.
    await resources().barrier()
    await resources().release("before next stage")
    memory_policy.preflight(selected,stage)
    angle_prompt = None
    if stage == "image" and action == "generate":
        if slot == "design":
            directions = {"design": {"name": "Front", "azimuth": 0, "elevation": 0}}
        else:
            index = next(i for i, view in enumerate(asset["views"]) if view["id"] == slot)
            views = asset["views"][index // 10 * 10:index // 10 * 10 + 10]
            directions = {view["id"]: {"name": view["name"], "azimuth": view["azimuth"],
                          "elevation": view["elevation"], "visibility": recipes.view_instructions(view)}
                          for view in views}
        description_helper.claim(asset["id"])
        try:
            prompts = await asyncio.to_thread(description_helper.angle_instructions, selected, directions,
                                              "initial" if slot == "design" else "design")
            angle_prompt = prompts[slot]
        finally:
            description_helper.release()
        idle()
    settings = asset["settings"]
    directory = Path(configuration()["root"])
    while not directory.exists():
        directory = directory.parent
    estimated_gb = 1 if stage == "image" else 8 if stage == "mesh" else 4
    disk_free_gb = shutil.disk_usage(directory).free / 1024**3
    if disk_free_gb < estimated_gb:
        raise ValueError(f"Only {disk_free_gb:.1f} GB disk space is free; this stage reserves an estimated {estimated_gb} GB of working space.")
    required = recipes.required_models(asset, stage, slot=slot, action=action)
    await asyncio.to_thread(models.verify, required)
    idle()
    # The helper has its own subprocess finally block; check headroom again after it exits.
    memory_policy.preflight(selected, stage)
    library = store()
    cache_bytes = 0
    if library.cache.exists():
        for directory in library.cache.iterdir():
            if directory.is_dir() and (directory / "owner.json").is_file():
                cache_bytes += sum(p.stat().st_size for p in directory.rglob("*") if p.is_file() and not p.is_symlink())
    if cache_bytes > settings["cache_limit_gb"] * 1024**3:
        raise ValueError("The job-owned temporary cache budget is full. Clean completed job temporary files before continuing.")
    job = library.create_job(asset["id"], stage)
    atomic_json(library.path(asset["id"], f"jobs/{job['id']}.json"),
                {"asset": asset, "stage": stage, "slot": slot, "action": action, "edit": edit})
    try:
        graph, details, bindings = await asyncio.to_thread(recipes.build, selected, job, stage, slot, action,
                                                         angle_prompt=angle_prompt, edit=edit)
        valid = await execution.validate_prompt(job["id"], graph.nodes, None)
        if not valid[0]:
            raise ValueError("Native graph validation failed: " + json.dumps({"error": valid[1], "nodes": valid[3]}))
        folder = contained(library.cache, job["id"])
        atomic_json(folder / "prompt.json", graph.nodes)
        atomic_json(folder / "recipe.json", details)
        return web.json_response({"prompt": graph.nodes, "job": job, "label": f"{stage}: {slot}",
                                  "summary": f"{stage.capitalize()} graph ready. {len(graph.nodes)} visible nodes.",
                                  "bindings": bindings})
    except Exception as error:
        with LOCK:
            current = library.load(asset["id"])
            next(j for j in current["jobs"] if j["id"] == job["id"]).update(status="failed", error=str(error))
            library.save(current)
        raise


@ROUTES.post(PREFIX + "/assets/{asset}/resume-info")
@endpoint
async def resume_info(request):
    library = store()
    asset_id = request.match_info["asset"]
    body = await request.json()
    job_id = identifier(body["job"])
    saved = json.loads(library.path(asset_id, f"jobs/{job_id}.json").read_text())
    # Restore recipe inputs without rolling back results created after the failed job.
    current = library.load(asset_id)
    recipe = saved["asset"]
    current.update({k: recipe[k] for k in ("profile", "prompt", "loras", "settings", "references")})
    # Preserve revision history but restore exactly which image and camera each input used.
    for key in ("current", "approved", "stale"):
        if key in recipe["design"]:
            current["design"][key] = recipe["design"][key]
    existing = {v["id"]: v for v in current["views"]}
    restored = []
    for old in recipe["views"]:
        view = existing.get(old["id"], old).copy()
        view.update({k: value for k, value in old.items() if k != "revisions"})
        restored.append(view)
    current["views"] = restored
    with LOCK:
        library.save(current)
    saved["asset"] = current
    return web.json_response(saved)


@ROUTES.post(PREFIX + "/assets/{asset}/queued")
@endpoint
async def queued(request):
    body = await request.json()
    with LOCK:
        library = store()
        asset = library.load(request.match_info["asset"])
        job = next(j for j in asset["jobs"] if j["id"] == identifier(body["job"]))
        prompt_id = str(uuid.UUID(body["prompt_id"]))
        job["prompt_id"] = prompt_id
        if job["status"] != "complete":
            job["status"] = "queued"
        library.save(asset)
    return web.json_response({"ok": True})


@ROUTES.post(PREFIX + "/assets/{asset}/cancel")
@endpoint
async def cancel(request):
    description_helper.cancel(request.match_info["asset"])
    with LOCK:
        library = store()
        asset = library.load(request.match_info["asset"])
        for job in asset["jobs"]:
            if job["status"] not in ("queued", "running", "preparing"):
                continue
            prompt_id = job.get("prompt_id")
            if prompt_id:
                interrupted = queue().interrupt_if_running(prompt_id)
                deleted = queue().delete_queue_item(lambda item: item[1] == prompt_id)
                if not interrupted and not deleted:
                    continue
                resources().cancel(prompt_id)
            job["status"] = "cancelled"
        library.save(asset)
    return web.json_response({"ok": True})


@ROUTES.post(PREFIX + "/release")
@endpoint
async def release(request):
    idle()
    # A manual retry may recover a previous failed release. Do not gate it on barrier().
    report = await resources().release("manual release")
    return web.json_response({"ok": True, "resources": report})


@ROUTES.post(PREFIX + "/assets/{asset}/cleanup")
@endpoint
async def cleanup(request):
    idle()
    library = store()
    with LOCK:
        asset = reconcile(library.load(request.match_info["asset"]))
        removable = [j for j in asset["jobs"] if j["status"] in ("complete", "failed", "cancelled", "interrupted")]
    removed = 0
    for job in removable:
        path = contained(library.cache, identifier(job["id"]))
        if path.exists():
            await asyncio.to_thread(library.cleanup_job, job["id"])
            removed += 1
    previews = cleanup_previews(asset, keep_latest=True)
    return web.json_response({"removed": removed, "previews": previews})


def cleanup_previews(asset, keep_latest=True):
    complete = [job for job in asset["jobs"] if job["status"] == "complete"]
    keep = complete[-1]["id"] if complete and keep_latest else None
    removed = 0
    for job in complete:
        if job["id"] == keep:
            continue
        for record in job.get("preview_files", []):
            path = contained(folder_paths.get_temp_directory(), record["relative"])
            if path.is_file():
                stat = path.stat()
                if stat.st_size == record["size"] and stat.st_mtime_ns == record["mtime"]:
                    path.unlink()
                    removed += 1
    return removed


@ROUTES.post(PREFIX + "/assets/{asset}/cleanup-previews")
@endpoint
async def clean_old_previews(request):
    with LOCK:
        asset = reconcile(store().load(request.match_info["asset"]))
        result = cleanup_previews(asset, keep_latest=True)
    return web.json_response({"removed": result})


def track_workshop_prompt(payload):
    """Also tracks a stage queued with Comfy's ordinary Run button."""
    prompt = payload.get("prompt", {})
    owners = set()
    for node in prompt.values():
        if node.get("class_type") in ("AW_SaveImage", "AW_SaveMaster", "AW_SaveDraft", "AW_SaveGuide", "AW_Export", "AW_FinishPreparation"):
            inputs = node.get("inputs", {})
            if isinstance(inputs.get("asset_id"), str) and isinstance(inputs.get("job_id"), str):
                owners.add((inputs["asset_id"], inputs["job_id"]))
    if len(owners) != 1:
        return payload
    asset_id, job_id = owners.pop()
    with LOCK:
        library = store()
        asset = library.load(asset_id)
        if asset.get("schema_version") == 2:
            return payload
        job = next(j for j in asset["jobs"] if j["id"] == job_id)
        payload.setdefault("prompt_id", str(uuid.uuid4()))
        job["prompt_id"] = payload["prompt_id"]
        if job["status"] != "complete":
            job["status"] = "queued"
        library.save(asset)
    # Runs independently of the browser and survives page reloads. The native worker
    # owns actual model unloading/cache reset; this observer only requests and checks it.
    PromptServer.instance.loop.call_soon_threadsafe(resources().track, payload["prompt_id"], (asset_id, job_id))
    return payload


if hasattr(PromptServer.instance, "add_on_prompt_handler"):
    PromptServer.instance.add_on_prompt_handler(track_workshop_prompt)


from .single_image_routes import register as register_single_image_routes
from .single_image_routes import has_active_jobs as single_image_jobs_active
register_single_image_routes(ROUTES, endpoint, resources, queue)

from .civitai_routes import register as register_civitai_routes
register_civitai_routes(ROUTES)
