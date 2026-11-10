"""First-use readiness for isolated refinement and texture workers.

Called only by a requested stage (or its native node), never bootstrap/settings.
Hi3D retains ownership of its pinned download and verification service.
"""
import hashlib
import json
import time
from pathlib import Path


def ensure_hi3d(base, request, cancelled, progress, wait=lambda: time.sleep(2)):
    started = False
    verifying = False
    while True:
        if cancelled():
            # The pinned upstream API has no download-cancel endpoint. Stop the
            # asset job without killing the user's service or pretending its
            # independent download stopped.
            raise InterruptedError("Asset run cancelled. Any Hi3D model download already started continues in the local Hi3D service; no refinement will be submitted.")
        health = request(base, "/api/health")
        state = health["models"]
        if state.get("ready"):
            return
        if health.get("recovery_blocked"):
            raise ValueError("Hi3D needs recovery in its local workbench before this stage can start.")
        downloading = state.get("download", {})
        if downloading.get("state") == "downloading":
            progress({"name":"Hi3D / "+downloading.get("file", downloading.get("component","required models")),
                      "phase":"downloading",
                      "completed_chunks":downloading.get("completed_chunks"),
                      "total_chunks":downloading.get("total_chunks")})
            started = True
        elif health.get("model_checking"):
            progress({"name":"Hi3D", "phase":"verifying required models"})
        elif started:
            raise ValueError("Hi3D model download did not finish successfully. "+downloading.get("message","Check the local Hi3D service and retry."))
        elif state.get("components") and all(item.get("present") for item in state["components"].values()):
            if verifying:
                raise ValueError("Hi3D model verification failed. Existing files were preserved; check its workbench.")
            progress({"name":"Hi3D", "phase":"verifying required models"})
            request(base, "/api/models/verify", {})
            verifying = True
        else:
            if health.get("active") or health.get("operation"):
                raise ValueError("Hi3D is busy. Retry this stage when its current operation finishes.")
            progress({"name":"Hi3D", "phase":"downloading"})
            result = request(base, "/api/models/download", {})
            if not result.get("started"):
                raise ValueError("Hi3D could not start its model download. Check its workbench and retry.")
            started = True
        wait()


def ensure_files(items, root, receipt_path, download, cancelled, progress):
    """Verify pinned snapshot files, fetching only absent files with shared downloader."""
    root = Path(root).resolve()
    receipt_path = Path(receipt_path)
    try:
        receipts = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        receipts = {}
    for item in items:
        if cancelled():
            raise InterruptedError("Cancelled before model loading.")
        target = (root/item["name"]).resolve()
        if not target.is_relative_to(root) or target == root:
            raise ValueError("Model snapshot path escaped its configured folder.")
        progress({"name":item["name"],"phase":"verifying required model"})
        if not target.is_file():
            progress({"name":item["name"],"phase":"downloading"})
            download(item, root)
        info = target.stat()
        identity = [str(target),info.st_size,info.st_mtime_ns,item["sha256"]]
        if receipts.get(item["name"]) == identity:
            continue
        actual = hashlib.sha256()
        with target.open("rb") as source:
            while block := source.read(8*1024*1024):
                if cancelled():
                    raise InterruptedError("Cancelled while verifying models.")
                actual.update(block)
        if info.st_size != item["size"] or actual.hexdigest() != item["sha256"]:
            raise ValueError(item["name"]+" differs from the pinned model and was preserved.")
        receipts[item["name"]] = identity
        receipt_path.parent.mkdir(parents=True,exist_ok=True)
        temporary = receipt_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipts),encoding="utf-8")
        temporary.replace(receipt_path)


def texture_dependencies(lock, mode):
    groups = lock["worker_models"]
    base = groups["trellis_texture"]
    return base + groups["trellis_smd_texture"] if mode == "smd" else base


def ensure_texture(state_root, cancelled=lambda:False, owner=None, progress=lambda value:None, *, texture_mode="standard"):
    from .... import models
    from ....finishing.runtime import settings
    root = Path(settings()["trellis_models"])
    if texture_mode not in ("standard", "smd"):
        raise ValueError("Choose Standard or SMD texturing.")
    lock = json.loads((Path(models.__file__).parent/"models.lock.json").read_text(encoding="utf-8"))
    items = texture_dependencies(lock, texture_mode)
    if not models.DOWNLOAD_LOCK.acquire(blocking=False):
        raise ValueError("Another model download is running. Retry after it finishes.")
    try:
        models.DOWNLOAD.clear()
        models.DOWNLOAD.update(status="running",cancel=False,owner=owner)
        ensure_files(items,root,Path(state_root)/"verified-texture-models.json",
                     lambda item, destination:models.download_one(item,destination_root=destination),
                     lambda:cancelled() or models.DOWNLOAD.get("cancel",False),progress)
        models.DOWNLOAD.update(status="complete")
    except Exception as error:
        models.DOWNLOAD.update(status="paused" if isinstance(error,InterruptedError) else "failed",error=str(error))
        raise
    finally:
        models.DOWNLOAD_LOCK.release()
