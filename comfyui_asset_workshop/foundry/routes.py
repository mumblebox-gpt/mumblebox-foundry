"""Thin HTTP boundary for Foundry-only data; existing download and vault owners stay unchanged."""
import asyncio
import hashlib
import itertools
import json
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from . import VERSION
from .artifacts import owned_path, open_folder
from .catalog import catalog
from .library import Library
from .preferences import Preferences
from .receipts import sync

PREFIX = "/mumblebox-foundry/v1"

def register(routes, library, preferences, wizard_factory=None, resources=None, updates=None, image_factory=None, image_notify=None, hair_factory=None, hair_notify=None, guided_factory=None):
    def endpoint(function):
        async def wrapped(request):
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                return web.json_response({"error": "Use the Foundry interface for this operation."}, status=403)
            try:
                result = await function(request)
                if isinstance(result, web.StreamResponse): return result
                return web.json_response(result, headers={"Cache-Control": "no-store"})
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                return web.json_response({"error": str(error) if isinstance(error, ValueError) else "The request was incomplete."}, status=400)
            except OSError:
                return web.json_response({"error": "The saved files could not be accessed. Check their location and try again."}, status=409)
            except Exception:
                return web.json_response({"error": "The Foundry operation could not finish. Your workflow has not been changed."}, status=500)
        return wrapped

    if guided_factory:
        from .workflows.guided_mesh.routes import register as guided_routes
        guided_routes(routes,guided_factory,endpoint)
    if image_factory:
        from .workflows.image_creation.routes import register as image_routes
        image_routes(routes,image_factory,endpoint,image_notify or (lambda ident:None))
    if hair_factory:
        from .workflows.hair_creation.routes import register as hair_routes
        hair_routes(routes,hair_factory,endpoint,hair_notify or (lambda ident:None))

    async def body(request):
        raw = await request.content.read(16385)
        if len(raw) > 16384: raise ValueError("The request is too large.")
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict): raise ValueError("Send one Foundry operation.")
        return data

    def candidates():
        folder = library.output_root / "3d" / "Finishing"
        return {hashlib.sha256(str(p).encode()).hexdigest()[:24]: p
                for p in itertools.islice(folder.glob("*.zip"), 128)}

    if resources is not None:
        @routes.get(PREFIX + "/resources")
        @endpoint
        async def resource_list(request):
            return await asyncio.to_thread(resources.list)

        @routes.post(PREFIX + "/resources/delete-preview")
        @endpoint
        async def resource_preview(request):
            return await asyncio.to_thread(resources.preview,(await body(request)).get("id"))

        @routes.post(PREFIX + "/resources/delete")
        @endpoint
        async def resource_remove(request):
            return await asyncio.to_thread(resources.remove,(await body(request)).get("token"))

    @routes.get("/mumblebox-foundry/")
    @endpoint
    async def app_entry(request):
        page = Path(__file__).resolve().parents[1] / "web" / "foundry" / "app.html"
        return web.Response(text=page.read_text(encoding="utf-8-sig"), content_type="text/html",
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "same-origin"})

    @routes.get(PREFIX + "/workflow")
    @endpoint
    async def packaged_workflow(request):
        path = Path(__file__).resolve().parents[1] / "workflows" / "Mumblebox 3D Asset Foundry.json"
        return json.loads(path.read_text(encoding="utf-8-sig"))
    @routes.get(PREFIX + "/bootstrap")
    @endpoint
    async def bootstrap(request):
        data=catalog();data["workflow"]["wizard"]=bool(wizard_factory)
        return {"version": VERSION, "preferences": preferences.read(), **data,
                "wizard_available": bool(wizard_factory),
                "import_candidates": [{"id": i, "name": p.name} for i, p in candidates().items()]}

    if updates is not None:
        @routes.get(PREFIX + "/updates/status")
        @endpoint
        async def update_status(request):
            return updates.status()

        @routes.post(PREFIX + "/updates/check")
        @endpoint
        async def update_check(request):
            data = await body(request)
            manual = data.get("manual", False)
            if set(data) - {"manual"} or not isinstance(manual, bool):
                raise ValueError("Choose an automatic or manual update check.")
            return await asyncio.to_thread(updates.check, manual)

    @routes.patch(PREFIX + "/preferences")
    @endpoint
    async def save_preferences(request):
        return preferences.update(await body(request))

    @routes.post(PREFIX + "/library/sync")
    @endpoint
    async def synchronize(request):
        await body(request)
        return await asyncio.to_thread(sync, library)

    @routes.get(PREFIX + "/library")
    @endpoint
    async def listing(request):
        return await asyncio.to_thread(library.list, request.query.get("kind", "mesh"),
                                       request.query.get("cursor", ""), int(request.query.get("limit", 24)))

    @routes.post(PREFIX + "/library/import-package")
    @endpoint
    async def import_package(request):
        data = await body(request)
        path = candidates().get(data.get("candidate_id"))
        if not path: raise ValueError("Choose a saved asset package from the listed output folder.")
        return await asyncio.to_thread(library.import_package, path)

    @routes.post(PREFIX + "/library/removal-preview")
    @endpoint
    async def review_removal(request):
        data = await body(request)
        return await asyncio.to_thread(library.preview_removal, data.get("kind"), data.get("ids"), data.get("delete_files", False))

    @routes.post(PREFIX + "/library/remove")
    @endpoint
    async def remove(request):
        data = await body(request)
        return await asyncio.to_thread(library.remove, data.get("token"))

    @routes.get(PREFIX + "/library/{id}")
    @endpoint
    async def detail(request):
        return library.public(library.record(request.match_info["id"]), detail=True)

    @routes.get(PREFIX + "/library/{id}/files/{file_id}")
    @endpoint
    async def download(request):
        path = library.file(request.match_info["id"], request.match_info["file_id"])
        image = path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if not image:
            from urllib.parse import quote
            headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(path.name)
        return web.FileResponse(path, headers=headers)

    @routes.post(PREFIX + "/library/{id}/open-folder")
    @endpoint
    async def reveal(request):
        await body(request)
        if request.remote not in ("127.0.0.1", "::1"):
            raise ValueError("Open Output Folder is available from the host PC. Use Download ZIP from another device.")
        record = library.record(request.match_info["id"])
        folder = owned_path(library.output_root, record["folder"])
        await asyncio.to_thread(open_folder, folder)
        return {"ok": True, "location": "Folder opened on the ComfyUI host PC."}


    if wizard_factory:
        @routes.get(PREFIX + "/wizard/capabilities")
        @endpoint
        async def wizard_capabilities(request):
            from .workflows.image_to_3d.definition import DEFAULTS,DEFAULT_SELECTION,CATEGORIES,VERSION
            from .workflows.image_to_3d.graph import template
            from .workflows.image_to_3d.turnaround import public_models
            service=wizard_factory()
            from .workflows.image_to_3d.readiness import viewer_module
            return {"viewer_module":viewer_module(),"defaults":DEFAULTS,"selection":DEFAULT_SELECTION,"categories":CATEGORIES,"version":VERSION,
                "max_references":10,"turnaround_models":public_models(),"default_turnaround_model":"qwen21",
                "profiles":[{"id":"default","name":"Default","available":True},
                    {"id":"low","name":"Low memory","available":False},{"id":"high","name":"High memory","available":False}],
                "exports":[{"id":k,"directory":v[0],"formats":v[1],"description":v[2]}
                    for k,v in service.variants.items() if k!="quad_detail"],
                "license_note":"Each model has its own license. The selected image model does not determine the licenses of Pixal3D, Hi3D, texturing or export tools. The package records the resources actually used."}

        @routes.get(PREFIX + "/wizard/runs/{id}/turnaround-graph")
        @endpoint
        async def wizard_turnaround_graph(request):
            from .workflows.image_to_3d.turnaround import compile_turnaround
            return compile_turnaround(wizard_factory().get(request.match_info["id"]))

        @routes.post(PREFIX + "/wizard/runs")
        @endpoint
        async def wizard_create(request):
            return await asyncio.to_thread(wizard_factory().create,await body(request))

        @routes.get(PREFIX + "/wizard/runs/{id}")
        @endpoint
        async def wizard_get(request):
            service=wizard_factory()
            return service.public(service.get(request.match_info["id"]))

        @routes.patch(PREFIX + "/wizard/runs/{id}")
        @endpoint
        async def wizard_update(request):
            return await asyncio.to_thread(wizard_factory().update,request.match_info["id"],await body(request))

        @routes.post(PREFIX + "/wizard/runs/{id}/start")
        @endpoint
        async def wizard_start(request):
            data=await body(request)
            client=data.get("client_id","")
            if not isinstance(client,str) or len(client)>100:raise ValueError("Invalid browser session.")
            result=wizard_factory().start(request.match_info["id"],data.get("operation"),client,data.get("request_id"))
            if client=="foundry-agent":
                from server import PromptServer
                PromptServer.instance.send_sync("mumblebox-foundry-run",{"id":result["id"]})
            return result

        @routes.post(PREFIX + "/wizard/runs/{id}/cancel")
        @endpoint
        async def wizard_cancel(request):
            await body(request)
            return wizard_factory().cancel(request.match_info["id"])

        @routes.post(PREFIX + "/wizard/runs/{id}/show")
        @endpoint
        async def wizard_show(request):
            await body(request)
            run=wizard_factory().get(request.match_info["id"])
            from server import PromptServer
            PromptServer.instance.send_sync("mumblebox-foundry-run",{"id":run["id"]})
            return {"id":run["id"],"display_requested":True,
                    "note":"The open Foundry interface receives this request; no window is raised or opened."}

        @routes.get(PREFIX + "/wizard/runs/{id}/graph")
        @endpoint
        async def wizard_graph(request):
            from .workflows.image_to_3d.graph import compile_stage
            run=wizard_factory().get(request.match_info["id"])
            return compile_stage(run["stage"],run)

        @routes.get(PREFIX + "/wizard/runs/{id}/package")
        @endpoint
        async def wizard_package(request):
            service=wizard_factory()
            run=service.get(request.match_info["id"])
            package=run.get("package")
            if not package:raise ValueError("No completed package is available yet.")
            path=owned_path(service.output_root,package["archive_path"])
            return web.FileResponse(path,headers={"Content-Disposition":'attachment; filename="'+path.name+'"',"Cache-Control":"no-store"})

        @routes.post(PREFIX + "/wizard/runs/{id}/open-folder")
        @endpoint
        async def wizard_folder(request):
            await body(request)
            if request.remote not in ("127.0.0.1","::1"):raise ValueError("Use Download ZIP from another device.")
            service=wizard_factory()
            run=service.get(request.match_info["id"])
            if not run.get("package"):raise ValueError("Finish the package first.")
            path=owned_path(service.output_root,run["package"]["archive_path"])
            await asyncio.to_thread(open_folder,path.parent)
            return {"ok":True}


def install():
    import folder_paths
    from server import PromptServer
    state = Path(folder_paths.get_user_directory()) / "mumblebox-foundry"
    library = Library(state, folder_paths.get_output_directory(),
                      busy=lambda: PromptServer.instance.prompt_queue.get_tasks_remaining() > 0)

    def wizard_factory():
        from .workflows.image_to_3d import runs
        if runs.ACTIVE is None:
            from ..single_image_routes import NativeQueue,has_active_jobs
            from ..routes import resources
            from ..finishing.package_catalog import VARIANTS,parse_selection
            runs.ACTIVE=runs.WizardRuns(state/"wizard-runs",folder_paths.get_input_directory(),
                folder_paths.get_output_directory(),NativeQueue(PromptServer.instance.prompt_queue),
                resources,lambda:has_active_jobs() or image_busy() or hair_busy() or guided_busy(),parse_selection,VARIANTS)
            runs.ACTIVE.library=library
            from .workflows.image_creation.lineage import resolve_handoff
            runs.ACTIVE.image_source_resolver=lambda source,refs:resolve_handoff(state/'image-creation',source,refs)
        return runs.ACTIVE
    from .workflows.image_to_3d.runs import busy
    from .workflows.image_creation.runs import busy as image_busy
    from .workflows.hair_creation.runs import busy as hair_busy
    from .workflows.guided_mesh.runs import busy as guided_busy
    def image_factory():
        from .workflows.image_creation import runs
        if runs.ACTIVE is None:
            from .workflows.image_creation.library import ImageLibrary
            from ..single_image_routes import NativeQueue,has_active_jobs
            from ..routes import resources
            runs.ACTIVE=runs.ImageRuns(ImageLibrary(state/'image-creation',folder_paths.get_output_directory()),
                folder_paths.get_input_directory(),NativeQueue(PromptServer.instance.prompt_queue),
                resources,lambda:has_active_jobs() or busy() or hair_busy() or guided_busy())
        return runs.ACTIVE
    def hair_factory():
        from .workflows.hair_creation import runs
        if runs.ACTIVE is None:
            from ..single_image_routes import NativeQueue,has_active_jobs
            from ..routes import resources
            runs.ACTIVE=runs.HairRuns(state/'hair-runs',folder_paths.get_input_directory(),
                folder_paths.get_output_directory(),NativeQueue(PromptServer.instance.prompt_queue),
                resources,lambda:has_active_jobs() or busy() or image_busy() or guided_busy(),library)
        return runs.ACTIVE
    def guided_factory():
        from .workflows.guided_mesh import runs
        if runs.ACTIVE is None:
            from ..single_image_routes import NativeQueue,has_active_jobs
            from ..routes import resources
            from ..finishing.package_catalog import VARIANTS,parse_selection
            runs.ACTIVE=runs.GuidedRuns(state/'guided',folder_paths.get_input_directory(),folder_paths.get_output_directory(),
                NativeQueue(PromptServer.instance.prompt_queue),resources,
                lambda:has_active_jobs() or busy() or image_busy() or hair_busy(),parse_selection,VARIANTS)
            runs.ACTIVE.finisher.library=library
        return runs.ACTIVE
    library.busy=lambda:PromptServer.instance.prompt_queue.get_tasks_remaining()>0 or busy() or image_busy() or hair_busy() or guided_busy()
    from .resources import ResourceInventory
    from .. import models,description_helper
    import comfy.model_management as memory
    from ..single_image_routes import has_active_jobs
    def resources_in_use():
        from ..civitai_routes import DOWNLOADS
        return (library.busy() or has_active_jobs() or bool(memory.current_loaded_models)
                or description_helper.PROCESS is not None or models.DOWNLOAD.get("status")=="running"
                or DOWNLOADS.status().get("status")=="running")
    resource_inventory=ResourceInventory(models.MODEL_ROOT,resources_in_use)
    from .updates import ReleaseUpdates
    preferences = Preferences(state/"preferences.json")
    updates = ReleaseUpdates(state/"updates.json", preferences)
    register(PromptServer.instance.routes, library, preferences, wizard_factory, resource_inventory, updates,
             image_factory,lambda ident:PromptServer.instance.send_sync('mumblebox-foundry-image',{'id':ident}),
             hair_factory,lambda ident:PromptServer.instance.send_sync('mumblebox-foundry-hair',{'id':ident}),guided_factory)
