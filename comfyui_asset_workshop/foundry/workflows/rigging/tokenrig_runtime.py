"""Prepare and run the optional, pinned Windows TokenRig environment."""
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from time import monotonic
from urllib.request import Request, urlopen
from zipfile import ZipFile

import folder_paths

from .... import models
from ....pipeline_workers.worker_process import OwnedWorker
from .document import read_prediction

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "tokenrig-runtime.json"
REQUIREMENTS = HERE / "requirements-tokenrig.txt"
WORKER = HERE / "tokenrig_worker.py"
SPEC = json.loads(MANIFEST.read_text(encoding="utf-8"))
KEYS = ("rig_tokenrig", "rig_tokenrig_vae", "rig_tokenrig_qwen_config", "rig_tokenrig_qwen_generation")
VERSION = hashlib.sha256(MANIFEST.read_bytes()+REQUIREMENTS.read_bytes()+WORKER.read_bytes()).hexdigest()[:16]


def runtime_root():
    return Path(folder_paths.base_path).resolve() / "tools" / "foundry-tokenrig" / VERSION


def interpreter(root):
    return root / "env" / "Scripts" / "python.exe"


def supported():
    return sys.platform == "win32" and os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64").upper() == "AMD64"


def readiness():
    root = runtime_root()
    ready = (root/"ready").is_file() and interpreter(root).is_file()
    missing_bytes = sum(models.MODELS[key]["size"] for key in KEYS if models.installed(key) is None)
    return {"supported_platform": supported(), "setup_ready": ready and not missing_bytes,
            "known_download_bytes": missing_bytes + (0 if ready else SPEC["uv"]["size"]+SPEC["source"]["size"]),
            "software_setup_required": not ready, "platform": "Windows x64, NVIDIA CUDA with native bfloat16"}


def download(spec, destination, check):
    if destination.exists() and destination.stat().st_size == spec["size"]:
        with destination.open("rb") as stream:
            if hashlib.file_digest(stream,"sha256").hexdigest() == spec["sha256"]:
                return
    temporary = destination.with_suffix(".partial")
    request = Request(spec["url"],headers={"User-Agent":"Mumblebox-Foundry"})
    digest = hashlib.sha256()
    size = 0
    with urlopen(request,timeout=45) as response, temporary.open("wb") as stream:
        while block := response.read(1024*1024):
            check()
            size += len(block)
            if size > spec["size"]:
                raise ValueError("The Local AI software download exceeded its pinned size.")
            digest.update(block)
            stream.write(block)
    if size != spec["size"] or digest.hexdigest() != spec["sha256"]:
        raise ValueError("The Local AI software download failed checksum verification.")
    temporary.replace(destination)


def extract_source(archive, destination):
    with ZipFile(archive) as bundle:
        for item in bundle.infolist():
            parts = PurePosixPath(item.filename).parts[1:]
            if item.is_dir() or not parts or parts[0] not in {"src","configs","LICENSE"}:
                continue
            target = destination.joinpath(*parts).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("The Local AI source archive contains an unsafe path.")
            target.parent.mkdir(parents=True,exist_ok=True)
            with bundle.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source,output)


def run_command(args, log, check, seconds, env):
    deadline = monotonic()+seconds
    with log.open("wb") as output:
        worker = OwnedWorker([str(arg) for arg in args],output,env=env)
        try:
            while True:
                check()
                try:
                    code = worker.process.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    if monotonic() >= deadline:
                        raise ValueError("Local AI took too long. Retry the operation or use Guided Template.") from None
        finally:
            if worker.process.poll() is None:
                with suppress(OSError):
                    worker.stop()
            worker.close()
    if code:
        with log.open("rb") as stream:
            stream.seek(max(0,log.stat().st_size-5000))
            lines = stream.read().decode("utf-8",errors="replace").splitlines()
        detail = next((line.removeprefix("ValueError: ") for line in reversed(lines)
                       if line.startswith("ValueError: ")),None)
        if detail:
            raise ValueError(detail)
        raise ValueError(f"Local AI setup or prediction failed. See {log.name} in Foundry’s Local AI tools folder.")


def environment(root):
    env = os.environ.copy()
    for key in ("UV_PYTHON_PREFERENCE", "UV_PYTHON", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(key,None)
    env.update(UV_CACHE_DIR=str(root.parent/"uv-cache"), UV_PYTHON_INSTALL_DIR=str(root.parent/"python"),
               PYTHONNOUSERSITE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    return env


def prepare(root, check, progress):
    if not supported():
        raise ValueError("Local AI fitting is available on Windows x64 with a compatible NVIDIA GPU.")
    root.mkdir(parents=True,exist_ok=True)
    code = root / "source"
    env = environment(root)
    python = interpreter(root)
    if not ((root/"ready").is_file() and python.is_file() and (code/"src/model/tokenrig.py").is_file()):
        progress("software")
        source_zip = root/"tokenrig-source.zip"
        uv_zip = root/"uv.zip"
        download(SPEC["source"],source_zip,check)
        download(SPEC["uv"],uv_zip,check)
        extract_source(source_zip,code)
        with ZipFile(uv_zip) as bundle, (root/"uv.exe").open("wb") as output:
            member = next(name for name in bundle.namelist() if PurePosixPath(name).name=="uv.exe")
            with bundle.open(member) as source:
                shutil.copyfileobj(source,output)
        uv = root/"uv.exe"
        log = root/"setup.log"
        if not python.is_file():
            run_command([uv,"venv","--managed-python","--python",SPEC["python"],python.parent.parent],log,check,480,env)
        run_command([uv,"pip","install","--python",python,"--index-url",SPEC["torch_index"],
                     "torch=="+SPEC["torch"]],log,check,900,env)
        run_command([uv,"pip","install","--python",python,"-r",REQUIREMENTS],log,check,900,env)
        run_command([python,"-I","-B",WORKER,code],log,check,120,env)
        (root/"ready").write_text(VERSION,encoding="ascii")
    progress("models")
    if not models.DOWNLOAD_LOCK.acquire(blocking=False):
        raise ValueError("Another Foundry download is running. Try again when it finishes.")
    try:
        missing = [models.MODELS[key] for key in KEYS if models.installed(key) is None]
        if missing:
            models.DOWNLOAD.clear()
            models.DOWNLOAD.update(status="running",cancel=False,owner="local-ai-rigging",completed_bytes=0,
                                   file_count=len(missing),batch_total=sum(model["size"] for model in missing))
            try:
                for index, model in enumerate(missing,1):
                    check()
                    models.DOWNLOAD.update(file_index=index,name=model["name"],bytes=0,total=model["size"])
                    models.download_one(model,anonymous=True,check=check)
                    models.DOWNLOAD["completed_bytes"] += model["size"]
            except BaseException:
                models.DOWNLOAD.update(status="cancelled" if models.DOWNLOAD.get("cancel") else "failed")
                raise
            models.DOWNLOAD.update(status="complete")
        models.verify(KEYS)
    finally:
        models.DOWNLOAD_LOCK.release()
    for key in KEYS[1:]:
        original = models.installed(key)
        target = code / models.MODELS[key]["name"]
        if target.is_file() and os.path.samefile(original,target):
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary = target.with_suffix(".partial")
        temporary.unlink(missing_ok=True)
        try:
            os.link(original,temporary)
        except OSError:
            shutil.copyfile(original,temporary)
        temporary.replace(target)
    return python, code, env


def fit(source, source_sha256, settings, destination, check, progress, bones=None):
    root = runtime_root()
    python, code, env = prepare(root,check,progress)
    progress("predicting")
    destination.mkdir(parents=True, exist_ok=True)
    request = destination / "request.json"
    payload = {"source": str(source), "source_sha256": source_sha256, "settings": settings,
               "checkpoint": str(models.installed(KEYS[0]))}
    if bones is not None:
        payload["bones"] = bones
    request.write_text(json.dumps(payload), encoding="utf-8")
    run_command([python, "-I", "-B", WORKER, code, request], destination/"prediction.log", check, 240, env)
    predicted, receipt = read_prediction(destination, source_sha256)
    if bones is not None:
        info = json.loads((destination/"prediction.json").read_bytes()).get("conditioning", {})
        ids = [bone["id"] for bone in bones]
        if not info.get("verified") or sorted(info.get("bone_ids", [])) != sorted(ids):
            raise ValueError("The learned binder did not preserve this skeleton. Choose Blender binding.")
        receipt["conditioning"] = info
    return predicted, {**receipt, "model": "TokenRig", "revision": models.MODELS[KEYS[0]]["revision"],
                   "adapter_revision": SPEC["source"]["revision"], "prediction_id": destination.name}
