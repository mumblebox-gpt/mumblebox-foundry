"""Resolve selected native model dependencies through the existing download owner."""
import json
from pathlib import Path
from ...artifacts import digest

MODELS = {"single_geometry":("pixal_single","shape_vae","dino","moge2","birefnet"), "splat":("idol","idol_dino","idol_decoder","idol_image_vae","birefnet"), "guided":("pixal_single","moge2","qwen21_union"),
          "turnaround":("qwen21","qwen21_clip","qwen21_vae","birefnet"),
          "geometry":("pixal_multiview","shape_vae","dino"),
          "refinement":("birefnet",), "texture":("birefnet",)}

def required_stages(operation, selection):
    """Prepare the remaining selected workflow before any new generation.

    Manual review boundaries do not postpone downstream model acquisition.
    Changed export choices are checked again when the user continues.
    """
    stages = ["turnaround", "geometry", "refinement"]
    if any(variant != "print" for variant in selection["variants"]):
        stages.append("texture")
    first = {"turnaround": 0, "rocket": 0, "mesh": 1, "finish": 3}[operation]
    return stages[first:]

def ensure(stage, state_root, cancelled=lambda:False, owner=None, progress=lambda value:None, turnaround_model="qwen21",geometry_model="pixal3d"):
    import folder_paths
    from .... import models
    path=Path(state_root)/"verified-models.json"
    try:receipts=json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,ValueError):receipts={}
    from .turnaround import dependency_keys
    required = dependency_keys(turnaround_model) if stage == "turnaround" else MODELS.get(stage,())
    if stage=='single_geometry' and geometry_model=='trellis2':required=tuple('trellis_single' if k=='pixal_single' else k for k in required)
    for key in required:
        if cancelled():raise InterruptedError("Cancelled before model loading.")
        model=models.MODELS[key]
        progress({"name":model["name"],"phase":"verifying required model"})
        local=folder_paths.get_full_path(model["category"],model["name"])
        if not local:
            if not models.DOWNLOAD_LOCK.acquire(blocking=False):
                raise ValueError("Another model download is running. Retry after it finishes.")
            try:
                models.DOWNLOAD.update(status="running",cancel=False,owner=owner)
                progress({"name":model["name"],"phase":"downloading"})
                models.download_one(model)
                models.DOWNLOAD.update(status="complete")
            except Exception as error:
                models.DOWNLOAD.update(status="failed",error=str(error))
                raise
            finally:models.DOWNLOAD_LOCK.release()
            local=folder_paths.get_full_path(model["category"],model["name"])
        if not local:raise ValueError("The selected model was not found: "+model["name"])
        file=Path(local);stat=file.stat()
        identity=[str(file.resolve()),stat.st_size,stat.st_mtime_ns,model["sha256"]]
        if receipts.get(key)==identity:continue
        if stat.st_size!=model["size"] or digest(file)!=model["sha256"]:
            raise ValueError(model["name"]+" differs from the pinned model. It was preserved; select the matching model before retrying.")
        receipts[key]=identity
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipts),encoding="utf-8")
        temporary.replace(path)
    if stage == "refinement":
        from ....finishing.runtime import settings
        from ....pipeline_workers.refine_client import request
        from .worker_models import ensure_hi3d
        ensure_hi3d(settings().get("hi3d_url","http://127.0.0.1:8378"),request,cancelled,progress)
    elif stage == "texture":
        from .worker_models import ensure_texture
        ensure_texture(state_root,cancelled,owner,progress)

def viewer_module():
    # Comfy 0.42 moved the native viewer from the old global factory into a
    # frontend module. Resolve its published export from the installed bundle;
    # never hardcode an asset hash or fetch third-party viewer libraries.
    import re
    from server import PromptServer
    root=Path(PromptServer.instance.web_root)/"assets"
    for path in sorted(root.glob("createLoad3d-*.js"))+sorted(root.glob("load3dService-*.js")):
        source=path.read_text(encoding="utf-8")
        match=re.search(r"export\{[^}]*\bcreateLoad3d as ([A-Za-z_$][\w$]*)",source)
        if match:return {"url":"/assets/"+path.name,"export":match.group(1),"host":path.name.startswith("createLoad3d-")}
    return None


def download_progress(owner):
    from .... import models
    if models.DOWNLOAD.get("owner")!=owner:return {}
    return {key:models.DOWNLOAD[key] for key in ("name","bytes","total","phase") if key in models.DOWNLOAD}

def cancel_download(owner):
    from .... import models
    if models.DOWNLOAD.get("owner")==owner:models.DOWNLOAD["cancel"]=True
