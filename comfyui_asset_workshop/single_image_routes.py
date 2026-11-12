"""Local adapters around the single-image job owner and existing Comfy services."""
import asyncio
import copy
import io
import time
import uuid
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, web
from PIL import Image, ImageOps
import execution

from comfy.cli_args import args
from server import PromptServer

from . import description_helper, image_edits, memory_policy, models, recipes, package_export, prompt_contracts
from .jobs import JobCoordinator
from .profiles import PROFILES, capabilities
from .runtime import store, configuration
from .store import LOCK, JobConflict, digest, identifier

PREFIX = "/asset-workshop/v2"
COORDINATOR = None


def has_active_jobs():
    """A preparation/release/visible-ack gap still belongs to the running job."""
    return COORDINATOR is not None and bool(COORDINATOR.tasks)


class NativeQueue:
    def __init__(self, queue):
        self.queue = queue

    def active_ids(self):
        running, pending = self.queue.get_current_queue_volatile()
        return {item[1] for item in running + pending}

    def history(self, prompt_id):
        return self.queue.get_history(prompt_id).get(prompt_id)

    async def submit(self, graph, prompt_id, client_id, *, preview_method=None):
        async with ClientSession(timeout=ClientTimeout(total=60)) as client:
            async with client.post(f"http://127.0.0.1:{args.port}/prompt", json={
                "prompt": graph, "prompt_id": prompt_id, "client_id": client_id,
                "extra_data": {"preview_method": preview_method} if preview_method else {}}) as response:
                result = await response.json()
                from .foundry.queue_validation import rejection
                error=rejection(result,response.status)
                if error:
                    # Comfy can accept only valid outputs with HTTP 200. Cancel
                    # this exact prompt so a partial stage is never successful.
                    if response.status<400:self.cancel(result.get('prompt_id',prompt_id))
                    raise ValueError(error)
                return result["prompt_id"]

    async def wait(self, prompt_id, timeout, cancelled):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            history = self.queue.get_history(prompt_id).get(prompt_id)
            if history:
                return history
            if cancelled() and prompt_id not in self.active_ids():
                return {"status": {"status_str": "cancelled"}}
            await asyncio.sleep(.5)
        self.cancel(prompt_id)
        raise TimeoutError("This stage exceeded its agreed runtime limit. Saved results remain available.")

    def cancel(self, prompt_id):
        self.queue.delete_queue_item(lambda item: item[1] == prompt_id)
        self.queue.interrupt_if_running(prompt_id)


def artifact_public(artifact):
    result = copy.deepcopy({key: value for key, value in artifact.items() if key != "manifest"})
    if "recipe" in result:
        result["recipe"] = {key:result["recipe"][key] for key in
            ("profile","seed","steps","cfg","task","requested_view","lora_validation","pipeline_version",
             "texture_provider","variant","material_model","material_model_revision","preservation") if key in result["recipe"]}
    if artifact.get("kind") == "package" and artifact.get("manifest"):
        manifest = artifact["manifest"]
        result["manifest_summary"] = {"schema": manifest.get("schema"),
            "reference_count": len(manifest.get("reference_images", {})),
            "discrepancy_count": len(manifest.get("known_discrepancies", []))}
    return result


def project_public(project):
    result = copy.deepcopy(project)
    result["jobs"] = [{key: job[key] for key in ("id", "kind", "state", "phase", "error", "created", "updated") if key in job}
                      for job in project["jobs"][-10:]]
    result["artifacts"] = [artifact_public(artifact) for artifact in project["artifacts"]]
    for session in result.get("pipeline",{}).get("material_sessions",{}).values():
        session["draft"]={"regions":[{k:r[k] for k in ("kind","id","name") if k in r} for r in session.get("draft",{}).get("regions",[])]}
    for slot in result["images"].values():
        for revision in slot["revisions"]:
            if "recipe" in revision:
                edit = revision["recipe"].get("edit")
                revision["recipe"] = {key: revision["recipe"][key] for key in
                    ("profile", "seed", "steps", "cfg", "task", "requested_view", "lora_validation") if key in revision["recipe"]}
                if edit:
                    revision["recipe"]["edit"] = {"id": edit["id"], "source": {"id": edit["source"]["id"]}}
    return result


def artifact_record(project, artifact_id):
    identifier(artifact_id)
    record = next((r for r in project["artifacts"] if r["id"] == artifact_id), None)
    if record:
        return record
    for role, slot in project["images"].items():
        for revision in slot["revisions"]:
            if revision["id"] == artifact_id:
                return {**revision, "kind": "image", "role": role}
    raise ValueError("The requested artifact is not recorded in this project.")


def register(routes, endpoint, resources, native_queue):
    def coordinator():
        global COORDINATOR
        library = store()
        if COORDINATOR is not None and COORDINATOR.library.root != library.root:
            if COORDINATOR.tasks:
                raise JobConflict("Wait for the current job before changing the library folder.")
            COORDINATOR = None
        if COORDINATOR is None:
            async def build_stage(project, snapshot, stage, job):
                if description_helper.STATE.get("running"):
                    raise ValueError("Wait for the description helper to release its models first.")
                await resources().barrier()
                await resources().release("before single-image " + stage["name"])
                kind = stage["name"]
                if kind in ("geometry","refine","cleanup","texture","variant","material_guide","materials"):
                    from .pipeline_recipes import build_stage_recipe
                    if kind == "geometry":
                        memory_policy.preflight(snapshot,"mesh")
                        await asyncio.to_thread(models.verify,recipes.required_models(snapshot,"mesh"))
                    return build_stage_recipe(project,snapshot,stage,job)
                native_stage = "image" if kind in ("create_image", "three_quarter", "edit_image", "reference_view") else "master" if kind == "finish" else "prepare" if kind in ("prepare", "prepare_foreground") else "mesh"
                memory_policy.preflight(snapshot, native_stage)
                await asyncio.to_thread(models.verify, recipes.required_models(snapshot, native_stage, action=kind))
                if native_stage == "image":
                    await asyncio.to_thread(recipes.selected_image_model, snapshot, True)
                    return recipes.image_task_recipe(project, snapshot, kind, stage["role"], stage["id"])
                if kind == "prepare_foreground":
                    graph, details, bindings = recipes.foreground_recipe(snapshot, {"id": stage["id"]}, stage["role"])
                    return {"graph": graph.nodes, "details": details, "bindings": bindings}
                if kind == "prepare":
                    graph, details, bindings = recipes.mesh_recipe(snapshot, {"id": stage["id"]}, prepare_only=True)
                    return {"graph": graph.nodes, "details": details, "bindings": bindings}
                if kind == "mesh":
                    return recipes.single_image_mesh_recipe(snapshot, project, stage["id"])
                master_id = job["payload"].get("master_id") or next(
                    (s.get("result", {}).get("master") for s in reversed(job["stages"]) if s["name"] == "mesh"), None)
                master = artifact_record(project, master_id) if master_id else None
                if master is None:
                    raise ValueError("Complete reconstruction before finishing a mesh.")
                return recipes.finish_saved_master_recipe(snapshot, master, stage["id"])

            native = NativeQueue(native_queue())
            COORDINATOR = JobCoordinator(library, native, resources(), build_stage,
                lambda event: PromptServer.instance.send_sync("mumblebox_stage", event, event["client_id"]))
            COORDINATOR.reconcile()
        return COORDINATOR

    @routes.get(PREFIX + "/capabilities")
    @endpoint
    async def get_capabilities(request):
        return web.json_response({"profiles": {key: capabilities(key) for key in PROFILES},
                                  "hardware": memory_policy.hardware_info(),
                                  "pipeline": __import__(__package__+".pipeline_capabilities",fromlist=["inspect_runtime"]).inspect_runtime(configuration().get("pipeline_runtime",{}))})

    @routes.post(PREFIX + "/validate")
    @endpoint
    async def validate_graph(request):
        if request.content_length and request.content_length > 1024**2:
            raise ValueError("Validate one stage graph at a time, below 1 MiB.")
        graph = await request.json()
        if not isinstance(graph, dict) or not graph or len(graph) > 400:
            raise ValueError("Validate one stage graph with 1 to 400 nodes.")
        valid, error, outputs, node_errors = await execution.validate_prompt(str(uuid.uuid4()), graph, None)
        return web.json_response({'valid': valid, 'error': error, 'output_ids': outputs, 'node_errors': node_errors})

    @routes.get(PREFIX + "/loras")
    @endpoint
    async def local_loras(request):
        from .lora_catalog import catalog
        from .civitai_native import installed_records
        root = models.MODEL_ROOT / 'loras'
        result = await asyncio.to_thread(catalog, root, installed_records())
        result['downloadable'] = [{'name': recipes.MODELS['sdxl_pixel_art']['name'], 'family': 'sdxl',
                                  'profiles': ['sdxl_base', 'sdxl_juggernaut'], 'trigger': 'pixel art'}]
        return web.json_response(result)

    @routes.post(PREFIX + "/loras/refresh")
    @endpoint
    async def refresh_lora_info(request):
        from .civitai_downloads import register_included_lora_info
        await asyncio.to_thread(register_included_lora_info, models.MODEL_ROOT)
        return await local_loras(request)

    @routes.post(PREFIX + "/client")
    @endpoint
    async def client(request):
        body = await request.json()
        coordinator().connect(body["client_id"], body["visible"])
        return web.json_response({"connected": True})

    @routes.get(PREFIX + "/presets")
    @endpoint
    async def presets(request):
        hardware = memory_policy.hardware_info()
        return web.json_response({"hardware": hardware, "presets": {
            key: memory_policy.preset_settings(key, hardware) for key in ("standard_16gb", "experimental_8gb")}})

    @routes.post(PREFIX + "/projects")
    @endpoint
    async def create_project(request):
        return web.json_response(project_public(store().create_project()))

    @routes.get(PREFIX + "/projects")
    @endpoint
    async def projects(request):
        entries = store().list_assets()
        offset = max(0, int(request.query.get("offset", 0)))
        limit = min(50, max(1, int(request.query.get("limit", 12))))
        return web.json_response({"entries": entries[offset:offset+limit], "total": len(entries), "offset": offset, "limit": limit})

    @routes.get(PREFIX + "/projects/{project}")
    @endpoint
    async def get_project(request):
        return web.json_response(project_public(store()._checked_project(request.match_info["project"])))

    @routes.patch(PREFIX + "/projects/{project}")
    @endpoint
    async def update_project(request):
        body = await request.json()
        project = store()._checked_project(request.match_info["project"], body["expected_revision"])
        changes = memory_policy.project_patch(project, body["changes"], memory_policy.hardware_info())
        return web.json_response(project_public(store().update_project(request.match_info["project"],
            body["expected_revision"], changes)))

    @routes.patch(PREFIX + "/projects/{project}/pipeline")
    @endpoint
    async def pipeline_settings(request):
        body=await request.json()
        return web.json_response(project_public(store().update_pipeline(request.match_info["project"],body["expected_revision"],body.get("changes",{}))))

    @routes.post(PREFIX + "/projects/{project}/pipeline/select")
    @endpoint
    async def pipeline_select(request):
        body=await request.json()
        return web.json_response(project_public(store().select_pipeline_artifact(request.match_info["project"],body["expected_revision"],body["artifact_id"])))

    @routes.post(PREFIX + "/projects/{project}/reuse")
    @endpoint
    async def reuse(request):
        body = await request.json()
        return web.json_response(project_public(store().reuse_parameters(request.match_info["project"],
            include_images=body.get("include_images", False))))

    @routes.post(PREFIX + "/projects/{project}/images")
    @endpoint
    async def import_image(request):
        fields, content, filename = {}, None, None
        reader = await request.multipart()
        async for part in reader:
            if part.name == "image":
                buffer = io.BytesIO()
                while block := await part.read_chunk():
                    buffer.write(block)
                    if buffer.tell() > 64*1024**2:
                        raise ValueError("This upload exceeds 64 MiB. Use a smaller image file.")
                content, filename = buffer.getvalue(), Path(part.filename or "image").name
            else:
                fields[part.name] = await part.text()
        if content is None:
            raise ValueError("Choose an image file to upload.")
        with Image.open(io.BytesIO(content)) as opened:
            if opened.width*opened.height > 40_000_000:
                raise ValueError("This image exceeds 40 megapixels.")
            image = ImageOps.exif_transpose(opened).convert("RGBA")
        library = store()
        with LOCK:
            project = library._checked_project(request.match_info["project"], int(fields["expected_revision"]))
            role = fields.get("role", "source")
            library.slot(project, role)
            revision_id = uuid.uuid4().hex[:16]
            relative = f"originals/{revision_id}.png"
            path = library.path(project["id"], relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path, format="PNG")
            revision = {"id": revision_id, "file": relative, "sha256": digest(path), "origin": "uploaded",
                        "original_name": filename, "created": time.time(), "width": image.width, "height": image.height}
            project = library.add_revision(project["id"], role, revision)
        return web.json_response({"project": project_public(project), "image": revision})

    @routes.post(PREFIX + "/projects/{project}/reviews")
    @endpoint
    async def review_image(request):
        body = await request.json()
        project = store().approve_image(request.match_info["project"], body["role"], body["revision_id"],
            body["sha256"], body["decision"], body.get("reviewer", "user"), body.get("notes", ""), body["expected_revision"])
        return web.json_response(project_public(project))

    @routes.post(PREFIX + "/projects/{project}/images/select")
    @endpoint
    async def select_image(request):
        body = await request.json()
        return web.json_response(project_public(store().select_image(request.match_info["project"],
            body["expected_revision"], body["role"], body["revision_id"])))

    @routes.post(PREFIX + "/projects/{project}/images/clear")
    @endpoint
    async def clear_images(request):
        body = await request.json()
        return web.json_response(project_public(store().clear_images(request.match_info["project"],
            body["expected_revision"], body.get("role"), body.get("revision_id"))))

    @routes.post(PREFIX + "/projects/{project}/describe")
    @endpoint
    async def describe(request):
        body = await request.json()
        library = store()
        project = library._checked_project(request.match_info["project"], body["expected_revision"])
        if native_queue().get_tasks_remaining() or coordinator().tasks:
            raise JobConflict("Wait for the current job before using the local description assistant.")
        if body.get("action") not in ("describe", "enhance"):
            raise ValueError("Choose Auto Describe my image or Enhance description.")
        description_helper.claim(project["id"])
        try:
            await resources().barrier()
            await resources().release("before single-image description assistant")
            text = await asyncio.to_thread(description_helper.generate, project, body["action"])
            contract = prompt_contracts.contract(project["profile"], body["action"], bool(project["sources"]), project["category"])
            return web.json_response({"text": text, "profile": project["profile"], "input_revision": project["revision"],
                                      "contract": {k: v for k, v in contract.items() if k != "instruction"}})
        finally:
            description_helper.release()
            if not native_queue().get_tasks_remaining():
                await resources().release("single-image description assistant finished")

    @routes.post(PREFIX + "/projects/{project}/describe/cancel")
    @endpoint
    async def cancel_description(request):
        project = store()._checked_project(request.match_info["project"])
        description_helper.cancel(project["id"])
        return web.json_response({"cancel_requested": True})

    @routes.post(PREFIX + "/projects/{project}/images/adopt")
    @endpoint
    async def adopt_image(request):
        body = await request.json()
        return web.json_response(project_public(store().adopt_image(request.match_info["project"],
            body["expected_revision"], body["source_role"], body["revision_id"], body["role"])))

    @routes.post(PREFIX + "/projects/{project}/edits")
    @endpoint
    async def create_edit(request):
        fields, selection = {}, None
        reader = await request.multipart()
        async for part in reader:
            if part.name == "mask":
                buffer = io.BytesIO()
                while block := await part.read_chunk():
                    buffer.write(block)
                    if buffer.tell() > 16*1024**2:
                        raise ValueError("This selection exceeds 16 MiB.")
                selection = buffer.getvalue()
            else:
                fields[part.name] = await part.text()
        if selection is None:
            raise ValueError("Draw a selection first.")
        library = store()
        with LOCK:
            project = library._checked_project(request.match_info["project"], int(fields["expected_revision"]))
            edit = image_edits.create(library, project["id"], fields["role"], fields["revision_id"],
                fields["prompt"], selection, int(fields.get("feather", 0)), fields.get("replace_detail") == "true")
        return web.json_response(edit)

    @routes.post(PREFIX + "/projects/{project}/edits/accept")
    @endpoint
    async def accept_edit(request):
        body = await request.json()
        library = store()
        with LOCK:
            library._checked_project(request.match_info["project"], body["expected_revision"])
            project = image_edits.accept(library, request.match_info["project"], body["role"], body["revision_id"])
        return web.json_response(project_public(project))

    @routes.post(PREFIX + "/projects/{project}/jobs")
    @endpoint
    async def start_job(request):
        from .foundry.workflows.image_to_3d.runs import busy as foundry_busy
        if foundry_busy():raise ValueError("The Foundry wizard is running. Wait for it to finish.")
        body = await request.json()
        return web.json_response(coordinator().start(request.match_info["project"], body["expected_revision"],
            body["kind"], body["request_key"], body.get("payload", {})))

    @routes.get(PREFIX + "/projects/{project}/jobs/{job}")
    @endpoint
    async def get_job(request):
        return web.json_response(coordinator().get(request.match_info["project"], request.match_info["job"]))

    @routes.post(PREFIX + "/projects/{project}/jobs/{job}/cancel")
    @endpoint
    async def cancel_job(request):
        return web.json_response(coordinator().cancel(request.match_info["project"], request.match_info["job"]))

    @routes.post(PREFIX + "/jobs/{job}/visible")
    @endpoint
    async def ack_visible(request):
        body = await request.json()
        coordinator().ack_visible(request.match_info["job"], body["stage_id"], body["graph_hash"], body["client_id"])
        return web.json_response({"acknowledged": True})

    @routes.get(PREFIX + "/projects/{project}/artifacts/{artifact}")
    @endpoint
    async def read_artifact(request):
        library = store()
        project = library._checked_project(request.match_info["project"])
        artifact = artifact_record(project, request.match_info["artifact"])
        path = library.path(project["id"], artifact["file"])
        if not path.is_file():
            raise ValueError("This recorded artifact is missing from disk.")
        if request.query.get("metadata") == "1":
            return web.json_response(artifact_public(artifact))
        if request.query.get("preview") == "1":
            if artifact["kind"] != "image":
                raise ValueError("Image previews require a recorded image artifact.")
            with Image.open(path) as original:
                preview = original.convert("RGBA")
                preview.thumbnail((768, 768))
                buffer = io.BytesIO()
                preview.save(buffer, format="PNG")
            return web.Response(body=buffer.getvalue(), content_type="image/png")
        response = web.FileResponse(path)
        if request.query.get("download") == "1":
            response.headers["Content-Disposition"] = f'attachment; filename="{artifact["id"]}{path.suffix}"'
        return response

    @routes.post(PREFIX + "/projects/{project}/packages")
    @endpoint
    async def export_package(request):
        body = await request.json()
        result = await asyncio.to_thread(package_export.create_package, store(), request.match_info["project"],
            body["expected_revision"], body["artifact_ids"], body.get("audience", "agent"))
        return web.json_response(artifact_public(result))

    @routes.post(PREFIX + "/projects/{project}/blender")
    @endpoint
    async def open_in_blender(request):
        from .blender_handoff import open_mesh
        body = await request.json()
        library = store()
        project = library._checked_project(request.match_info["project"], body["expected_revision"])
        artifact = artifact_record(project, body["artifact_id"])
        if artifact["kind"] != "mesh" or artifact.get("stale"):
            raise ValueError("Choose a current exported mesh to open in Blender.")
        path = library.path(project["id"], artifact["file"])
        if not path.is_file() or digest(path) != artifact["sha256"]:
            raise ValueError("The mesh changed on disk. Export it again before opening it in Blender.")
        return web.json_response(await asyncio.to_thread(open_mesh, path))

    @routes.post(PREFIX + "/release")
    @endpoint
    async def release(request):
        await resources().barrier()
        return web.json_response(await resources().release("manual single-image controls release"))

    from .material_routes import register as register_material_routes
    register_material_routes(routes,endpoint,coordinator)
