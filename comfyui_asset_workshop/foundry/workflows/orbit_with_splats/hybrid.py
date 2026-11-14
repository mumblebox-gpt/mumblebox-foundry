"""Encode a reviewed, camera-matched hybrid from the native Foundry viewers."""
import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import uuid

from ...artifacts import owned_path

WIDTH, HEIGHT, FPS, FRAMES = 1920, 1080, 30, 600
MAX_FRAME = 4 * 1024 * 1024
ENCODERS = {}

@dataclass
class Export:
    token: str
    process: asyncio.subprocess.Process
    file: Path
    final: Path
    pair: str
    frames: int = 0
    expiry: asyncio.TimerHandle | None = None
    writing: bool = False

    def renew(self, callback):
        if self.expiry:
            self.expiry.cancel()
        self.expiry = asyncio.get_running_loop().call_later(120, callback)

    async def discard(self):
        if self.expiry:
            self.expiry.cancel()
        if self.process.returncode is None:
            self.process.kill()
        await self.process.communicate()
        self.file.unlink(missing_ok=True)

def ffmpeg():
    from imageio_ffmpeg import get_ffmpeg_exe
    return get_ffmpeg_exe()

async def begin(service, run):
    pair = run["checkpoints"].get("pair")
    if run["id"] in service.tasks or not pair:
        raise ValueError("Finish the aligned mesh and splat before exporting a hybrid video.")
    if ENCODERS:
        raise ValueError("A hybrid video is already being exported.")
    if service.native.active_ids() or service.legacy_busy():
        raise ValueError("Another Comfy or Foundry job is active. Wait for it to finish.")
    pair = str(owned_path(service.output_root, pair))
    if not Path(pair).is_file():
        raise ValueError("Finish the aligned mesh and splat before exporting a hybrid video.")
    token = uuid.uuid4().hex
    directory = owned_path(service.output_root, service.output_root / "foundry" / service.method / run["id"])
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"hybrid-{token[:12]}.mp4"
    partial = target.with_suffix(".partial")
    ENCODERS[token] = None
    try:
        executable = ffmpeg()
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = await asyncio.create_subprocess_exec(
            executable, "-nostdin", "-loglevel", "error", "-n",
            "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "pipe:0",
            "-vf", f"scale={WIDTH}:{HEIGHT}:out_color_matrix=bt709:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-movflags", "+faststart",
            "-color_primaries", "bt709", "-colorspace", "bt709", "-color_trc", "bt709",
            "-f", "mp4", str(partial), stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL, creationflags=flags)
    except (ImportError, ValueError, OSError, RuntimeError, NotImplementedError):
        ENCODERS.pop(token, None)
        raise ValueError("Foundry could not start the local MP4 encoder.") from None
    state = ENCODERS[token] = Export(token, process, partial, target, pair)
    refresh(run, state)
    return {"id": token, "width": WIDTH, "height": HEIGHT, "frames": FRAMES, "fps": FPS}

def refresh(run, state):
    state.renew(lambda: asyncio.create_task(discard(run, state.token)))

def lookup(run, token):
    state = ENCODERS.get(token)
    if not state or state.final.parent.name != run["id"] or state.pair != run["checkpoints"].get("pair"):
        raise ValueError("The hybrid export session has expired or the asset has changed.")
    return state

async def discard(run, token):
    state = ENCODERS.get(token)
    if not state or state.final.parent.name != run["id"]:
        return
    ENCODERS.pop(token)
    await state.discard()

async def append(run, token, index, data):
    state = lookup(run, token)
    if state.writing or index != state.frames or index >= FRAMES:
        raise ValueError("The hybrid video frames must arrive in order.")
    if not 4 <= len(data) <= MAX_FRAME or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("The hybrid renderer did not send a valid frame.")
    state.writing = True
    try:
        state.process.stdin.write(data)
        await asyncio.wait_for(state.process.stdin.drain(), timeout=30)
        state.frames += 1
        refresh(run, state)
    except (OSError, TimeoutError):
        await discard(run, token)
        raise ValueError("The local MP4 encoder stopped before the export finished.") from None
    finally:
        state.writing = False
    return {"frames": state.frames}

async def finish(service, run, token):
    state = lookup(run, token)
    if state.frames != FRAMES or state.writing:
        raise ValueError("The hybrid video needs all rendered frames before it can be saved.")
    state.expiry.cancel()
    state.process.stdin.close()
    try:
        await asyncio.wait_for(state.process.communicate(), timeout=60)
        if state.process.returncode or not state.file.is_file() or state.file.stat().st_size < 1024:
            raise ValueError("The local MP4 encoder could not finish the hybrid video.")
        state.file.replace(state.final)
        run["checkpoints"]["hybrid"] = str(state.final)
        service.save(run)
    finally:
        await discard(run, token)
    return service.public(run)
