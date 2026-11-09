"""Use Foundry's pinned model downloader and its managed llama.cpp runtime."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib import request

from . import gpu, vision
from .contract import MAX_HTML, MODEL_KEYS, PROJECTOR_KEY, STANDARD_MODEL, SYSTEM, inspect_glb, scene_html

STATE = {}
CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RENDERER = Path(__file__).with_name("renderer.py")


@contextmanager
def child(command, log_path, cwd=None):
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, creationflags=CREATE_FLAGS)
        try:
            yield process
        finally:
            if process.poll() is None:
                stop_owned_process(process)


def stop_owned_process(process):
    # The Windows Python shim and Playwright driver have children. Reap the
    # exact owned tree so cancellation cannot leave a renderer consuming memory.
    import psutil

    try:
        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        descendants = []
    for child_process in reversed(descendants):
        try:
            child_process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def log_tail(path):
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 1800))
        return stream.read().decode("utf-8", errors="replace").strip()


def prepare(model_variant, check, *, with_image=False):
    from .... import description_helper, models

    if not models.DOWNLOAD_LOCK.acquire(blocking=False):
        raise ValueError("Another model is downloading. Wait for it to finish and try again.")
    try:
        model_key = MODEL_KEYS[model_variant]
        keys = [model_key, PROJECTOR_KEY] if with_image else [model_key]
        models.DOWNLOAD.clear()
        models.DOWNLOAD.update(status="running", owner=STATE["job"], cancel=False, bytes=0, total=0)
        executable = description_helper.runtime(check, use_configured=False)
        missing = [models.MODELS[key] for key in keys if models.installed(key) is None]
        total = sum(model["size"] for model in missing)
        completed = 0
        models.DOWNLOAD.update(file_count=len(missing), batch_total=total, completed_bytes=completed)
        for index, model in enumerate(missing, 1):
            check()
            models.DOWNLOAD.update(file_index=index, name=model["name"], bytes=0, total=model["size"])
            models.download_one(model, anonymous=True, check=check)
            completed += model["size"]
            models.DOWNLOAD.update(completed_bytes=completed)
        check()
        models.verify(keys)
        local = models.installed(model_key)
        projector = models.installed(PROJECTOR_KEY) if with_image else None
        standard = None
        standard_key = MODEL_KEYS[STANDARD_MODEL]
        if model_key != standard_key and models.installed(standard_key) is not None:
            try:
                models.verify([standard_key])
                standard = models.installed(standard_key)
            except (OSError, ValueError):
                # An unavailable or invalid fallback must never be advertised.
                pass
        models.DOWNLOAD.update(status="complete", completed_bytes=completed)
        return executable, local, standard, projector
    except BaseException:
        models.DOWNLOAD.update(status="paused" if models.DOWNLOAD.get("cancel") else "failed")
        raise
    finally:
        models.DOWNLOAD_LOCK.release()


def infer(executable, checkpoint, settings, work, check, device, gpu_id, standard_checkpoint,
          *, projector=None, image=None):
    STATE["phase"] = "Checking GPU memory"
    gpu.preflight(executable, checkpoint, settings["max_tokens"], device, gpu_id, check,
                  model_variant=settings["model_variant"], standard_checkpoint=standard_checkpoint, vision=image is not None)
    log = work / "llama.log"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    key = secrets.token_urlsafe(32)
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    opener = request.build_opener(request.ProxyHandler({}))
    command = [
        str(executable), *gpu.cuda_args(checkpoint, settings["max_tokens"], device, vision=image is not None),
        "--host", "127.0.0.1", "--port", str(port), "--api-key", key,
        "--jinja", "--fit", "off", "--log-verbosity", "4", "--reasoning", "on", "--no-webui",
    ]
    if projector is not None:
        command.extend(vision.arguments(projector, device))
    from ....pipeline_workers import activity

    STATE["phase"] = "Loading CCORE"
    with activity.tracked("ccore", "CCORE"), child(command, log, executable.parent) as process:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            check()
            if process.poll() is not None:
                raise ValueError("The local CCORE runtime could not start. " + log_tail(log))
            try:
                with opener.open(request.Request(base + "/health", headers=headers), timeout=2):
                    break
            except OSError:
                time.sleep(.35)
        else:
            raise ValueError("CCORE took too long to load. Free memory and try again.")

        gpu.verify_placement(log.read_text(encoding="utf-8", errors="replace"), device, vision=image is not None)
        activity.update("ccore", "CCORE", "loaded")
        STATE["phase"] = "Designing your prop"
        body = {
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": vision.content(settings["prompt"], image)
                          if image is not None else settings["prompt"]}],
            "seed": settings["seed"], "temperature": .8, "top_p": .95,
            "top_k": 40, "min_p": 0.0, "repeat_penalty": 1.0, "max_tokens": settings["max_tokens"], "stream": True,
            "chat_template_kwargs": {"enable_thinking": True},
        }
        payload = request.Request(base + "/v1/chat/completions",
                                  data=json.dumps(body).encode("utf-8"), headers=headers)
        chunks, size, finish = [], 0, None
        deadline = time.monotonic() + 1800
        with opener.open(payload, timeout=90) as response:
            while line := response.readline(512 * 1024):
                check()
                if time.monotonic() > deadline:
                    raise ValueError("CCORE reached the time limit. Try a simpler prop.")
                if not line.startswith(b"data:"):
                    continue
                record = line[5:].strip()
                if record == b"[DONE]":
                    break
                packet = json.loads(record)
                if packet.get("error"):
                    raise ValueError("CCORE could not finish the response. Try another seed.")
                for choice in packet.get("choices", []):
                    value = choice.get("delta", {}).get("content") or ""
                    if value:
                        size += len(value.encode("utf-8"))
                        if size > MAX_HTML:
                            raise ValueError("The generated scene is too large.")
                        chunks.append(value)
                    finish = choice.get("finish_reason") or finish
        check()
        return scene_html("".join(chunks), finish)


def run_renderer(arguments, log, timeout, check):
    deadline = time.monotonic() + timeout
    with child([sys.executable, str(RENDERER), *arguments], log) as process:
        while process.poll() is None:
            check()
            if time.monotonic() > deadline:
                raise ValueError("The isolated CCORE browser took too long to finish.")
            time.sleep(.15)
        if process.returncode:
            raise ValueError(log_tail(log) or "The isolated CCORE browser could not start.")
    check()


def render_isolated(source, output, check):
    run_renderer([str(source), str(output)], source.with_suffix(".log"), 55, check)
    if not output.is_file():
        raise ValueError("The isolated renderer could not export this prop.")
    return inspect_glb(output)


def generate(settings, work, check, *, image=None):
    device, gpu_id = gpu.comfy_device()
    STATE["phase"] = "Preparing the local renderer"
    try:
        run_renderer(["--probe"], work / "renderer-probe.log", 25, check)
    except ValueError as error:
        raise ValueError("The CCORE browser renderer is unavailable. Run Foundry’s software installer. " + str(error)) from error
    STATE["phase"] = "Preparing the CCORE model"
    executable, checkpoint, standard, projector = prepare(settings["model_variant"], check, with_image=image is not None)
    if not checkpoint:
        raise ValueError("The verified CCORE checkpoint is missing.")
    if image is not None and not projector:
        raise ValueError("The verified CCORE vision projector is missing.")
    html = infer(executable, checkpoint, settings, work, check, device, gpu_id, standard,
                 projector=projector, image=image)
    STATE["phase"] = "Exporting and checking the GLB"
    source = work / "scene.html"
    source.write_text(html, encoding="utf-8")
    output = work / "prop.glb"
    return output, render_isolated(source, output, check)
