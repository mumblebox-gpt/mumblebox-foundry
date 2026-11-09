"""Foundry routes for the CCORE prop wizard."""
import json
from aiohttp import web

from .contract import EXAMPLE, MODEL_KEYS, TOKEN_LIMITS, default_model_variant
from .enhancement import enhancement_input

PREFIX = "/mumblebox-foundry/v1/ccore"


def register(routes, factory, endpoint):
    @routes.get(PREFIX + "/capabilities")
    @endpoint
    async def capabilities(request):
        from ..image_to_3d.readiness import viewer_module

        return {"viewer_module": viewer_module(), "example": EXAMPLE, "token_limits": TOKEN_LIMITS,
                "model_variants": list(MODEL_KEYS), "default_model_variant": default_model_variant()}

    @routes.post(PREFIX + "/enhance")
    @endpoint
    async def enhance(request):
        ident, prompt = enhancement_input(await read_object(request))
        return await factory().enhance(ident, prompt)

    @routes.post(PREFIX + "/enhance/{id}/cancel")
    @endpoint
    async def cancel_enhancement(request):
        return factory().cancel_enhancement(request.match_info["id"])

    @routes.post(PREFIX + "/runs")
    @endpoint
    async def start(request):
        return factory().start(await read_object(request))

    @routes.get(PREFIX + "/runs/{id}")
    @endpoint
    async def status(request):
        service = factory()
        return service.public(service.get(request.match_info["id"]))

    @routes.post(PREFIX + "/runs/{id}/cancel")
    @endpoint
    async def cancel(request):
        return factory().cancel(request.match_info["id"])

    @routes.get(PREFIX + "/runs/{id}/file")
    @endpoint
    async def file(request):
        kind = request.query.get("kind", "model")
        path = factory().file(request.match_info["id"], kind)
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if request.query.get("download") == "1":
            filename = "prop.glb" if kind == "model" else "ccore-prop.zip"
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        headers["Content-Type"] = "model/gltf-binary" if kind == "model" else "application/zip"
        return web.FileResponse(path, headers=headers)




async def read_object(request):
    if request.content_type != "application/json":
        raise ValueError("Send one CCORE prop request as JSON.")
    raw = bytearray()
    async for block in request.content.iter_chunked(8192):
        raw.extend(block)
        if len(raw) > 32768:
            raise ValueError("The CCORE request exceeds 32 KiB.")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Send one CCORE prop request.")
    return data
