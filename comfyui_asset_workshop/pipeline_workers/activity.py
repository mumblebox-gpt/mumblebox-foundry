"""Host-owned live worker registry. No directory scans, network calls or model imports."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import threading
import time
from weakref import WeakKeyDictionary

_lock = threading.Lock()
_workers = {}
_native_names = WeakKeyDictionary()
_STATES = {"loaded", "offloaded", "unknown", "empty"}
_WEIGHT_SUFFIXES = {".safetensors", ".sft", ".ckpt", ".gguf", ".pt", ".pth", ".bin", ".onnx"}


def checkpoint_name(path):
    """Only the checkpoint basename belongs in the public status response."""
    return str(path).replace("\\", "/").rsplit("/", 1)[-1][:160]


def _label(value, default):
    return " ".join(value.split())[:160] if isinstance(value, str) and value.strip() else default


def _row(name, state, device=None, *, runtime):
    return {"name": _label(name, "Model"), "state": state if state in _STATES else "unknown",
            "device": _label(device, None), "runtime": runtime}


def update_models(key, models):
    rows = [_row(model["name"], model["state"], model.get("device"), runtime="worker")
            for model in models if model["state"] != "empty"]
    with _lock:
        _workers[key] = rows


def update(key, name, state="unknown", *, device=None):
    update_models(key, [{"name": name, "state": state, "device": device}])


def remove(key):
    with _lock:
        _workers.pop(key, None)


def snapshot():
    with _lock:
        return copy.deepcopy([row for rows in _workers.values() for row in rows])


def identify(patcher, *names):
    """Attach names to an owned native model without keeping its weights alive."""
    module = getattr(patcher, "model", None)
    if module is not None:
        with _lock:
            try:
                _native_names[module] = tuple(names)
            except TypeError:
                pass


def _native_labels(patcher):
    module = getattr(patcher, "model", None)
    if module is not None:
        with _lock:
            try:
                aliases = _native_names.get(module)
            except TypeError:
                aliases = None
        if aliases:
            return aliases
    metadata = getattr(patcher, "cached_patcher_init", None)
    if isinstance(metadata, tuple) and len(metadata) > 1 and isinstance(metadata[1], (list, tuple)) and metadata[1]:
        first = metadata[1][0]
        sources = first if isinstance(first, (list, tuple)) else [first]
        names = [checkpoint_name(path) for path in sources if isinstance(path, (str, Path))
                 and Path(checkpoint_name(path)).suffix.lower() in _WEIGHT_SUFFIXES]
        if names:
            return names
    actual = getattr(module, "diffusion_model", module)
    if actual is None:
        return ["ComfyUI model"]
    kind = type(actual).__name__
    display = {"MoGeModelV1": "MoGe", "MoGeModelV2": "MoGe 2", "MoGeModelV3": "MoGe 3",
               "CLIPVisionModelProjection": "CLIP Vision"}
    return [display.get(kind, kind)]


def owned_pid(reported, root):
    if reported==root:return True
    if not isinstance(reported,int) or reported<=0:return False
    # Windows venv python.exe can be a redirector. Its real interpreter remains
    # in the owned job tree; accept that child, never an arbitrary reported PID.
    import psutil
    try:return root in [p.pid for p in psutil.Process(reported).parents()[:16]]
    except (psutil.NoSuchProcess,psutil.AccessDenied):return False

@contextmanager
def tracked(key, name):
    update(key, name)
    try: yield
    finally: remove(key)

def read_worker(key, name, path, pid):
    """Only accept this live child's recent, bounded status; stale is unknown."""
    try:
        path=Path(path)
        if path.stat().st_size>8192: raise ValueError('Oversized worker status')
        value=json.loads(path.read_text(encoding='utf-8'))
        if not owned_pid(value.get('pid'),pid) or not 0<=time.time()-value['time']<5: raise ValueError('Stale worker status')
        models = value.get("models")
        if models is None:
            update(key, name, value.get("state", "unknown"), device=value.get("device"))
        elif isinstance(models, list) and len(models) <= 32:
            if models or value.get("state") == "empty":
                update_models(key, models)
            else:
                update(key, name)
        else:
            raise ValueError("Invalid worker model list")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        update(key, name)


def host_residency(loaded):
    """Read Comfy's live residency and native identities without loading anything."""
    rows = []
    for item in loaded:
        patcher = item.model
        if patcher is None:
            continue
        names = _native_labels(patcher)
        try:
            size = patcher.loaded_size()
            if size > 0:
                device = str(patcher.current_loaded_device() if hasattr(patcher, "current_loaded_device") else patcher.load_device)
                state, label = "loaded", "GPU" if device.startswith("cuda") else device.upper()
            else:
                state, label = "offloaded", "CPU offload"
        except (AttributeError, TypeError, RuntimeError):
            state, label = "unknown", None
        rows.extend(_row(name, state, label, runtime="comfy") for name in names)
    return rows


def model_snapshot(loaded):
    rows = host_residency(loaded) + snapshot()
    return list({(row["name"], row["state"], row["device"]): row for row in rows}.values())
