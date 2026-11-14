"""HTTP routes shared by Virtual Turntable's wizard and MCP."""
import json
from aiohttp import web

from ...artifacts import owned_path
from .definition import capabilities
from .graph import compile_stage, template, FINISHING
from .runs import STEPS

PREFIX = "/mumblebox-foundry/v1/virtual-turntable"


async def body(request):
    data = await request.content.read(192001)
    if len(data) > 192000:
        raise ValueError("Virtual Turntable settings exceed 192 KB.")
    value = json.loads(data or b"{}")
    if not isinstance(value, dict):
        raise ValueError("Supply one Virtual Turntable operation.")
    return value


def register(routes, factory, endpoint, *, prefix=PREFIX, get_capabilities=capabilities,
             get_template=template, compile_prompt=compile_stage, stages=(*STEPS, *FINISHING),
             event="mumblebox-foundry-turntable", extra_artifacts=()):
    artifacts = ("orbit", "raw", "frames", "clean", "texture", "refined", "balanced", "compact", "print", "quads", *extra_artifacts)
    @routes.get(prefix + "/capabilities")
    @endpoint
    async def cap(request):
        return get_capabilities()

    @routes.get(prefix + "/template")
    @endpoint
    async def default_template(request):
        return get_template()

    @routes.post(prefix + "/runs")
    @endpoint
    async def create(request):
        return factory().create(await body(request))

    @routes.get(prefix + "/runs/{id}")
    @endpoint
    async def get(request):
        service = factory()
        return service.public(service.get(request.match_info["id"]))

    @routes.patch(prefix + "/runs/{id}")
    @endpoint
    async def update(request):
        return factory().update(request.match_info["id"], await body(request))

    @routes.get(prefix + "/runs/{id}/graph")
    @endpoint
    async def graph(request):
        run = factory().get(request.match_info["id"])
        stage = request.query.get("stage")
        if stage is None:
            return get_template(run)
        if stage not in stages:
            raise ValueError("Choose a Virtual Turntable stage.")
        return compile_prompt(stage, run, factory().output_root)

    @routes.post(prefix + "/runs/{id}/start")
    @endpoint
    async def start(request):
        data = await body(request)
        run = factory().start(request.match_info["id"], data.get("operation"), data.get("client_id", ""), data.get("request_id"))
        if data.get("client_id") == "foundry-agent":
            from server import PromptServer
            PromptServer.instance.send_sync(event, {"id": run["id"]})
        return run

    @routes.post(prefix + "/runs/{id}/cancel")
    @endpoint
    async def cancel(request):
        await body(request)
        return factory().cancel(request.match_info["id"])

    @routes.post(prefix + "/runs/{id}/show")
    @endpoint
    async def show(request):
        await body(request)
        run = factory().get(request.match_info["id"])
        from server import PromptServer
        PromptServer.instance.send_sync(event, {"id": run["id"]})
        return {"id": run["id"], "display_requested": True}

    @routes.get(prefix + "/runs/{id}/artifacts/{role}")
    @endpoint
    async def artifact(request):
        service = factory()
        run = service.get(request.match_info["id"])
        role = request.match_info["role"]
        if role not in artifacts:
            raise ValueError("Choose a published Virtual Turntable artifact.")
        path = owned_path(service.output_root, run["checkpoints"].get(role, ""))
        if not path.is_file():
            raise ValueError("That artifact is not available yet.")
        return web.FileResponse(path, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @routes.get(prefix + "/runs/{id}/package")
    @endpoint
    async def package(request):
        service = factory()
        run = service.get(request.match_info["id"])
        if not run.get("package"):
            raise ValueError("Finish the asset package first.")
        path = owned_path(service.output_root, run["package"]["archive_path"])
        return web.FileResponse(path, headers={"Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="' + path.name + '"'})
