"""Small worker-side model-residency sampler; uses existing model objects only."""
import atexit
from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading
import time

def residency(pipeline):
    candidates=list(pipeline.models.values())+[getattr(pipeline,'image_cond_model',None)]
    devices=[]
    unknown=False
    for model in candidates:
        if model is None: continue
        try:
            module=model if hasattr(model,'parameters') else getattr(model,'model',None)
            parameter=next(module.parameters(),None) if module is not None else None
            if parameter is None: unknown=True
            else: devices.append(str(parameter.device).split(':')[0])
        except (AttributeError,RuntimeError): unknown=True
    if 'cuda' in devices: return {'state':'loaded','device':'CUDA + CPU offload' if 'cpu' in devices else 'CUDA'}
    if unknown or 'meta' in devices: return {'state':'unknown','device':'unknown'}
    if devices: return {'state':'offloaded','device':'CPU'}
    # Lazy model construction may temporarily leave the pipeline slots empty.
    # An active worker without observable parameters is unknown, not unloaded.
    return {'state':'unknown','device':'unknown'}

def _monitor(request_path, read):
    path = Path(request_path).with_name("model-residency.json")
    stopped = threading.Event()

    def sample():
        while not stopped.is_set():
            try:
                value = {**read(), "pid": os.getpid(), "time": time.time()}
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(value), encoding="utf-8")
                temporary.replace(path)
            except (OSError, RuntimeError):
                pass
            stopped.wait(.5)

    threading.Thread(target=sample, name="foundry-model-residency", daemon=True).start()
    atexit.register(stopped.set)
    return stopped


def monitor(pipeline, request_path, slot_names=None):
    slot_names = slot_names or {}
    def read():
        slots = list(pipeline.models.items())
        slots.append(("image_encoder", getattr(pipeline, "image_cond_model", None)))
        models = []
        for key, model in slots:
            if model is None:
                continue
            try:
                module = model if hasattr(model, "parameters") else getattr(model, "model", None)
                parameter = next(module.parameters(), None) if module is not None else None
                device = parameter.device.type if parameter is not None else None
            except (AttributeError, RuntimeError):
                device = None
            state = "loaded" if device == "cuda" else "offloaded" if device == "cpu" else "unknown"
            label = slot_names.get(key, "TRELLIS.2 · " + key.replace("_", " ").capitalize())
            models.append({"name": label, "state": state,
                           "device": "GPU" if state == "loaded" else "CPU offload" if state == "offloaded" else None})
        return {**residency(pipeline), "models": models}
    return _monitor(request_path, read)


@contextmanager
def monitor_stages(request_path):
    """Publish real stage loads and clears using the same worker heartbeat."""
    models = []

    def set_models(names):
        nonlocal models
        models = [{"name": name, "state": "loaded", "device": "GPU"} for name in names]

    def read():
        current = models
        return {"state": "loaded" if current else "empty", "models": current}

    stopped = _monitor(request_path, read)
    try:
        yield set_models
    finally:
        stopped.set()
