"""Bounded HTTP interface for the garment wizard."""
import asyncio
import json
from uuid import uuid4

from aiohttp import web

from . import character, edits, runtime
from .nodes import directory
from .contract import AUTHOR, EXAMPLE, GENERATION_PRESETS, WEIGHTS

PREFIX = "/mumblebox-foundry/v1/garment"


async def body(request, limit=16384):
    raw = bytearray()
    async for block in request.content.iter_chunked(8192):
        raw.extend(block)
        if len(raw) > limit:
            raise ValueError("The garment request is too large.")
    value = json.loads(raw or b"{}")
    if not isinstance(value, dict):
        raise ValueError("Send one garment operation.")
    return value


def register(routes, factory, endpoint):
    @routes.get(PREFIX + "/capabilities")
    @endpoint
    async def capabilities(request):
        from ..image_to_3d.readiness import viewer_module
        return {"modes": runtime.availability(), "viewer_module": viewer_module(),
                "example": EXAMPLE, "source": AUTHOR, "weights": WEIGHTS,
                "generation_presets": GENERATION_PRESETS,
                "edit_operations": edits.OPERATIONS,
                "edit_fields": {
                    "pattern": ["guide", "objective", "strength", "rate", "iterations", "steps"],
                    "silhouette": ["guide", "objective", "azimuth", "elevation", "center", "strength", "rate", "iterations", "steps"],
                    "shape": ["guide", "strength", "rate", "iterations", "steps"],
                    "completion": ["guide", "strength", "rate", "iterations", "steps"],
                    "mix": ["guide", "strength", "rate", "iterations", "steps"],
                    "blend": ["second_seed", "blend", "second_points"],
                },
                "drape_controls": {"character": "uploaded character ID", "transform": character.DEFAULT_FIT,
                                   "fabric": character.FABRICS, "frames": [48, 16, 120]}}

    def notify(ident):
        from server import PromptServer
        PromptServer.instance.send_sync("mumblebox-foundry-garment", {"id": ident})

    @routes.post(PREFIX + "/runs")
    @endpoint
    async def start(request):
        data = await body(request)
        result = factory().start(data)
        if data.get("client_id") == "foundry-agent":
            notify(result["id"])
        return result

    @routes.post(PREFIX + "/runs/{id}/show")
    @endpoint
    async def show(request):
        ident = factory().get(request.match_info["id"])["id"]
        notify(ident)
        return {"id": ident, "display_requested": True}

    @routes.get(PREFIX + "/runs/{id}/graph")
    @endpoint
    async def graph(request):
        from .nodes import GENERATE, STAGE_NODE

        run = factory().get(request.match_info["id"])
        return run.get("native_graph") or {
            STAGE_NODE: {"class_type": GENERATE, "inputs": {**run["config"], "job": run["id"]}},
        }

    @routes.get(PREFIX + "/runs/{id}")
    @endpoint
    async def status(request):
        service = factory()
        return service.public(service.get(request.match_info["id"]))

    @routes.get(PREFIX + "/runs/{id}/guide")
    @endpoint
    async def guide(request):
        return await asyncio.to_thread(factory().guide, request.match_info["id"])

    @routes.get(PREFIX + "/runs/{id}/mix-sources")
    @endpoint
    async def mix_sources(request):
        return await asyncio.to_thread(factory().mix_sources, request.match_info["id"])

    @routes.post(PREFIX + "/runs/{id}/edit")
    @endpoint
    async def edit(request):
        return factory().edit(request.match_info["id"], await body(request, 384 * 1024))

    @routes.post(PREFIX + "/runs/{id}/{action:sew|drape|fit|package|cancel}")
    @endpoint
    async def stage(request):
        service = factory()
        ident, action = request.match_info["id"], request.match_info["action"]
        data = await body(request)
        if action in ("sew", "drape", "fit"):
            return getattr(service, action)(ident, data)
        return getattr(service, action)(ident)

    @routes.post(PREFIX + "/runs/{id}/character")
    @endpoint
    async def upload_character(request):
        service = factory()
        run = service.get(request.match_info["id"])
        if not run["mesh"] or request.content_type != "application/octet-stream":
            raise ValueError("Build the sewn mesh, then upload one rigged character GLB.")
        if request.content_length is None or request.content_length > character.MAX_CHARACTER:
            raise ValueError("Choose one rigged GLB smaller than 150 MB.")
        ident = uuid4().hex
        file = character.path(directory(service.output, run["id"]), ident)
        file.parent.mkdir(exist_ok=True)
        partial = file.with_suffix(".partial")
        try:
            count = 0
            with partial.open("xb") as stream:
                async for block in request.content.iter_chunked(1024 * 1024):
                    count += len(block)
                    if count > character.MAX_CHARACTER:
                        raise ValueError("The character file exceeds 150 MB.")
                    stream.write(block)
            character.validate(partial)
            partial.replace(file)
        finally:
            partial.unlink(missing_ok=True)
        return {"character": ident}

    @routes.get(PREFIX + "/runs/{id}/file/{name}")
    @endpoint
    async def file(request):
        path = factory().file(request.match_info["id"], request.match_info["name"])
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
        if path.suffix == ".glb":
            headers["Content-Type"] = "model/gltf-binary"
        if request.query.get("download") == "1" or path.suffix == ".svg":
            headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
        return web.FileResponse(path, headers=headers)

