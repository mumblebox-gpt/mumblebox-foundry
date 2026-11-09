"""Explicit first-use downloads, pinned hashes, resumable files, no model execution."""

import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit
from pathlib import Path

import folder_paths
from . import hf_auth
from .recipes import MODELS, required_models
from .runtime import configuration
from .store import atomic_json, contained, digest

DOWNLOAD = {"status": "idle", "bytes": 0}
DOWNLOAD_LOCK = threading.Lock()
MODEL_ROOT = Path(folder_paths.base_path).resolve() / "models"

# This extension's downloads stay in this installation, even if Comfy also
# searches model folders registered by another application.
for category in {m["category"] for m in MODELS.values()}:
    folder_paths.add_model_folder_path(category, str(MODEL_ROOT / category), is_default=True)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        redirected = super().redirect_request(request, fp, code, msg, headers, new_url)
        if redirected and urlsplit(new_url).hostname != urlsplit(request.full_url).hostname:
            redirected.remove_header("Authorization")
        return redirected


def installed(key):
    model = MODELS[key]
    for folder in folder_paths.get_folder_paths(model["category"]):
        candidate = (Path(folder) / model["name"]).resolve()
        if candidate.is_relative_to(MODEL_ROOT) and candidate.is_file():
            return candidate
    return None


def status(asset, stage="image", camera=False, slot="design", action="generate"):
    keys = required_models(asset, stage, camera, slot, action)
    missing, available = [], []
    for key in keys:
        model = MODELS[key]
        path = installed(key)
        if path and path.stat().st_size == model["size"]:
            available.append({"id": key, **model})
        else:
            missing.append({"id": key, **model, "repo_url": "https://huggingface.co/" + quote(model["repo"], safe="/")})
    return {"missing": missing, "available": available}


def verify(keys):
    receipts_path = Path(configuration()["root"]) / "model-verification.json"
    receipts = json.loads(receipts_path.read_text()) if receipts_path.exists() else {}
    for key in keys:
        model = MODELS[key]
        path = installed(key)
        if path is None:
            raise ValueError(f"Download the selected model first: {model['name']}")
        stat = path.stat()
        identity = [str(path.resolve()), stat.st_size, stat.st_mtime_ns, model["sha256"]]
        if receipts.get(key) == identity:
            continue
        if stat.st_size != model["size"] or digest(path) != model["sha256"]:
            raise ValueError(f"{model['name']} differs from the pinned recipe. It has not been overwritten. Select the correct file before continuing.")
        receipts[key] = identity
        atomic_json(receipts_path, receipts)


def download_one(model, *, destination_root=None, anonymous=False, check=None):
    source = {"model": model["name"], "repo_url": "https://huggingface.co/" + quote(model["repo"], safe="/"),
              "license_url": model.get("license_url")}
    DOWNLOAD.update(source=source, recovery=None)
    if destination_root is None:
        folders = [Path(p).resolve() for p in folder_paths.get_folder_paths(model["category"])]
        root = next((p for p in folders if p.is_relative_to(MODEL_ROOT)),
                    MODEL_ROOT / model["category"]).resolve()
        if not root.is_relative_to(MODEL_ROOT):
            raise ValueError("This model folder points outside this Comfy installation. Choose a local model folder before downloading.")
    else:
        # Only the explicitly configured isolated texture snapshot root is
        # permitted. HTTP callers cannot supply arbitrary download destinations.
        from .pipeline_capabilities import validate_runtime
        config = validate_runtime(configuration().get("pipeline_runtime", {}))
        allowed = config.get("trellis_models")
        root = Path(destination_root).resolve()
        if not allowed or root != Path(allowed).resolve():
            raise ValueError("Worker downloads must use the configured texture model folder.")
    root.mkdir(parents=True, exist_ok=True)
    target = contained(root, model["name"])
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size == model["size"] and digest(target) == model["sha256"]:
            if model['category'] == 'loras':
                from .civitai_downloads import register_included_lora_info
                register_included_lora_info(MODEL_ROOT, [model['name']])
            return
        raise ValueError(f"{target.name} already exists with different content; it will not be replaced.")
    # This subfolder belongs only to Asset Workshop downloads.
    cache = root / ".asset-workshop-downloads"
    cache.mkdir(parents=True, exist_ok=True)
    part = contained(cache, model["sha256"] + ".part")
    required = model["size"] - (part.stat().st_size if part.exists() else 0)
    if shutil.disk_usage(root).free < required + 1024**3:
        raise ValueError(f"Not enough free disk space for {model['name']}.")
    url = f"https://huggingface.co/{model['repo']}/resolve/{model['revision']}/{model['file']}"
    headers = {"User-Agent": "ComfyUI-Asset-Workshop/0.1"}
    token = None if anonymous else hf_auth.token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    offset = part.stat().st_size if part.exists() else 0
    DOWNLOAD.update(name=model["name"], bytes=offset, total=model["size"], phase="connecting")
    if offset > model["size"]:
        raise ValueError("The owned partial download is larger than its pinned source; remove that partial file before retrying.")
    if offset < model["size"]:
        if offset:
            headers["Range"] = f"bytes={offset}-"
        opener = urllib.request.build_opener(SafeRedirect())
        try:
            response = opener.open(urllib.request.Request(url, headers=headers), timeout=60)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                DOWNLOAD["recovery"] = {**source, "kind": "access", "http_status": error.code}
                raise ValueError(f"Hugging Face denied access to {model['name']} (HTTP {error.code}). "
                                 f"Model access page: {source['repo_url']} . Request or accept access there, then connect "
                                 "a read token for the same account and retry. If access is pending, wait for approval. "
                                 "A token does not accept the model's terms for you.") from None
            raise
        with response:
            resumed = offset > 0 and response.status == 206
            if resumed and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                raise ValueError("Server returned the wrong resume range.")
            if not resumed:
                offset = 0
            with part.open("ab" if resumed else "wb") as output:
                DOWNLOAD.update(bytes=offset, phase="download")
                while block := response.read(4 * 1024 * 1024):
                    if check is not None:
                        check()
                    if DOWNLOAD.get("cancel"):
                        raise InterruptedError("Download paused; the partial file is retained for resume.")
                    output.write(block)
                    offset += len(block)
                    DOWNLOAD["bytes"] = offset
                    if offset > model["size"]:
                        raise ValueError("Download exceeded its pinned size.")
                output.flush()
                os.fsync(output.fileno())
    DOWNLOAD["phase"] = "verifying SHA-256"
    if part.stat().st_size != model["size"] or digest(part) != model["sha256"]:
        # Only the downloader's own partial file is discarded; installed models are untouched.
        part.unlink(missing_ok=True)
        raise ValueError(f"Integrity check failed for {model['name']}. The incomplete file was not installed.")
    if target.exists():
        raise ValueError("The destination appeared during download; refusing to replace it.")
    # Windows rename fails if target already exists; same volume as destination.
    os.rename(part, target)
    if model['category'] == 'loras':
        from .civitai_downloads import register_included_lora_info
        register_included_lora_info(MODEL_ROOT, [model['name']])
    DOWNLOAD["phase"] = "download"


def start_download(asset, stage="image", camera=False, slot="design", action="generate", retry=False):
    if not DOWNLOAD_LOCK.acquire(blocking=False):
        raise ValueError("A model download is already running.")
    try:
        if retry:
            request = DOWNLOAD.get("request", {})
            if (DOWNLOAD.get("status") not in ("failed", "paused") or request.get("kind") != "models"
                    or request.get("asset_id") != asset["id"]):
                raise ValueError("Return to the job whose model download stopped before retrying it.")
            items = [{"id": key, **MODELS[key]} for key in request["model_ids"]]
        else:
            items = status(asset, stage, camera, slot, action)["missing"]
            request = {"kind": "models", "asset_id": asset["id"], "stage": stage,
                       "camera": camera, "slot": slot, "action": action,
                       "model_ids": [model["id"] for model in items]}
        DOWNLOAD.clear()
        DOWNLOAD.update(status="running", bytes=0, cancel=False, phase="connecting", request=request,
                        batch_total=sum(model["size"] for model in items), completed_bytes=0,
                        file_count=len(items), file_index=0)
    except Exception:
        DOWNLOAD_LOCK.release()
        raise

    def worker():
        try:
            for index, model in enumerate(items, 1):
                if DOWNLOAD.get("cancel"):
                    raise InterruptedError("Download paused; downloaded files are retained for resume.")
                DOWNLOAD.update(file_index=index, name=model["name"], bytes=0, total=model["size"], phase="connecting")
                download_one(model)
                DOWNLOAD.update(completed_bytes=DOWNLOAD["completed_bytes"]+model["size"], bytes=0, total=0)
            DOWNLOAD.update(status="complete", completed=time.time())
        except urllib.error.HTTPError as error:
            DOWNLOAD.update(status="failed", error=f"Could not download {DOWNLOAD.get('name', 'model')}: HTTP {error.code}. "
                            "The file or download service could not be reached. Check your connection and retry; "
                            "if it persists, check the model page for availability.")
        except Exception as error:
            DOWNLOAD.update(status="paused" if isinstance(error, InterruptedError) else "failed", error=str(error))
        finally:
            DOWNLOAD_LOCK.release()

    threading.Thread(target=worker, name="asset-workshop-model-download", daemon=True).start()
    return dict(DOWNLOAD)
