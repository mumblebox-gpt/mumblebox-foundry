"""Rig session API and the active Foundry viewport's local capture relay."""
import asyncio
import base64
import binascii
import hashlib
import json
import math
import re
import struct
import time
from threading import Event
from uuid import uuid4

from aiohttp import web

from ...agent_connection import SESSION_HEADER, local_request
from ...artifacts import owned_path
from .commands import LockedJoint, PART_TYPES, ROLES, STRUCTURAL_ACTIONS, part_layout
from .control import AgentEditingConflict
from .document import MAX_BONES, SCHEMA_VERSION
from .geometry import POSES
from .live import ViewportRequests
from .methods import capabilities as method_capabilities, fit_settings
from .observations import ObservationStore, normalized_pixels, probe_results, scene_identity
from .sessions import (
    MAX_BATCH_BYTES, ExpiredPreview, RevisionConflict, RigSessions, current_output, identifier,
    public_state, skeleton_key,
)
from .weights import MODES, MAX_POINTS

PREFIX = "/mumblebox-foundry/v1/rigging"
VIEW_EVENT = "mumblebox-foundry-rigging"
MAX_CAPTURE = 900_000
MAX_JSON_CAPTURE = 700_000
CAPTURE_VIEWS = ("current", "front", "side", "back", "oblique", "part")
DRAG_SECONDS = 12
ACTIVE_BUSY = lambda: False


def busy():
    """Expose the same owned job state to Foundry's existing resource guards."""
    return ACTIVE_BUSY()


async def body(request, limit=8192):
    payload = bytearray()
    async for block in request.content.iter_chunked(8192):
        payload.extend(block)
        if len(payload)>limit:
            raise ValueError("The rigging request is too large.")
    data = json.loads(payload or b"{}")
    if not isinstance(data,dict):
        raise ValueError("Send one rigging operation.")
    return data


def response(run):
    from .runtime import binding_method

    data = public_state(run)
    data["recommended_binding"] = binding_method(run)
    data["mesh_url"] = f"{PREFIX}/runs/{run['id']}/source.glb"
    if data["bound"]:
        data["rig_url"] = f"{PREFIX}/runs/{run['id']}/rig.glb?binding={run['output']['binding']}"
    if output := weight_preview(run):
        data["weight_preview_url"] = f"{PREFIX}/runs/{run['id']}/rig.glb?binding={output['binding']}"
    return data


def weight_preview(run):
    output = run.get("output")
    if output and output["skeleton"] == skeleton_key(run) and output.get("file") == "rig.glb":
        return output
    return None


def native_tools(names):
    """Resolve exports from the installed native viewer bundle."""
    from pathlib import Path
    from server import PromptServer
    root = Path(PromptServer.instance.web_root) / "assets"
    for path in sorted(root.glob("vendor-three-*.js")):
        with path.open("rb") as stream:
            stream.seek(max(0,path.stat().st_size-8192))
            tail = stream.read().decode("utf-8",errors="ignore")
        exports = tail.rsplit("export{",1)[-1].split("}",1)[0]
        aliases = {name:re.search(r"(?:^|,)"+name+r"(?: as ([\w$]+))?(?:,|$)",exports) for name in names}
        if all(aliases.values()):
            return {"url":"/assets/"+path.name,"exports":{name:match.group(1) or name for name,match in aliases.items()}}
    return None


def native_weight_tools():
    return native_tools(("Raycaster", "BufferAttribute", "MeshBasicMaterial"))


def register(routes, library, endpoint, notify, lifecycle=None):
    global ACTIVE_BUSY
    service = RigSessions(library.root/"rigging",library)
    live = None
    drag_lease = None
    pending = None
    operation = asyncio.Lock()
    fitting = None
    binding = None
    processing = None
    preparing = {}
    observations = ObservationStore()
    viewport_requests = ViewportRequests(lambda event: notify(VIEW_EVENT,event))

    def busy():
        return operation.locked() or any(job and job[0]["status"] == "running" for job in (fitting,binding))
    ACTIVE_BUSY=busy

    def displayed():
        if live and live["expires"] > time.monotonic():
            return live
        raise ValueError("Open a mesh in the Rig a Character wizard window first.")

    def local(request):
        if not local_request(request):
            raise ValueError("Use the Foundry window on this computer for rig editing.")

    def conflict(error):
        return web.json_response({"error":str(error), "code":getattr(error,"code","stale_revision")}, status=409)

    def mutation(function):
        @endpoint
        async def guarded(request):
            try:
                return await function(request)
            except (AgentEditingConflict, ExpiredPreview, LockedJoint, RevisionConflict) as error:
                return conflict(error)
        return guarded

    def ui_only(request):
        local(request)
        if SESSION_HEADER in request.headers:
            raise ValueError("Use the controls in the active Foundry wizard.")

    def browser_owner(data, run_id):
        return (live and live["expires"] > time.monotonic() and live["id"] == run_id
                and live["browser"] == data.get("browser"))

    def actor(request, data, run_id=None):
        session = request.headers.get(SESSION_HEADER)
        if session is not None:
            return {"actor": "agent", "agent_session_id": identifier(session)}
        browser = identifier(data.get("browser"))
        owns = browser_owner(data, run_id) if run_id else preparing.get(browser, 0) > time.monotonic()
        if not owns:
            raise ValueError("Open the rig in the active Foundry wizard before editing.")
        return {"actor": "human", "active_browser_id": browser}

    def admit(request, data, run_id, revision):
        owner = actor(request, data, run_id)
        service.control.check(owner)
        if owner["actor"] == "agent" and displayed()["id"] != run_id:
            raise ValueError("Open the intended rigging session before editing.")
        if active_drag(run_id):
            raise AgentEditingConflict("human_drag_active", "Finish the current joint drag before editing.")
        run = service.checked(run_id, revision)
        return service.admit(run_id, run["rig_revision"], owner)

    def payload(run):
        return {**response(run), "agent_control": service.control.status()}

    def active_drag(run_id):
        if (drag_lease and live and drag_lease["id"] == run_id == live["id"] and
                drag_lease["browser"] == live["browser"] and drag_lease["expires"] > time.monotonic()):
            return drag_lease
        return None

    def changed(run, actor_context=None, operation_name=None, view=None):
        event = {"action":"changed","id":run["id"],"revision":run["revision"]}
        if view:
            event["view"] = view
        if actor_context and actor_context["actor"] == "agent":
            event.update(actor="agent", operation=operation_name, joint=run["selected_joint"])
        notify(VIEW_EVENT, event)
        return payload(run)

    @routes.get(PREFIX+"/capabilities")
    @endpoint
    async def capabilities(request):
        from ..image_to_3d.readiness import viewer_module
        from .tokenrig_runtime import readiness
        return {"viewer":viewer_module(), "poses":POSES,"units":"glTF Y-up world coordinates",
                "source":"Recorded static self-contained GLB", "binder":"local Blender CPU",
                "schema_version": SCHEMA_VERSION, "max_bones": MAX_BONES,
                "commands": [*STRUCTURAL_ACTIONS, "undo", "redo"], "parts": PART_TYPES, "roles": ROLES,
                "binding_methods": ["learned", "conditioned", "voxel"], "capture_views": CAPTURE_VIEWS,
                "weight_tools":native_weight_tools(), "weight_modes":MODES, "weight_points":MAX_POINTS,
                "spatial_tools":native_tools(("WebGLRenderTarget", "PerspectiveCamera", "OrthographicCamera",
                                               "Raycaster", "MeshBasicMaterial")),
                "methods": {**method_capabilities(), "guided_template": {}}, "local_ai":readiness()}

    @routes.get(PREFIX+"/sources/{record_id}")
    @endpoint
    async def sources(request):
        return {"sources": await asyncio.to_thread(service.sources, identifier(request.match_info["record_id"]))}

    @routes.get(PREFIX+"/exports/{export_id}")
    @endpoint
    async def exported(request):
        export_id = identifier(request.match_info["export_id"])
        record_id = hashlib.sha256(("mesh:"+export_id).encode()).hexdigest()[:32]
        try:
            items = await asyncio.to_thread(service.sources, record_id)
        except ValueError:
            from ...receipts import sync
            await asyncio.to_thread(sync, library)
            items = await asyncio.to_thread(service.sources, record_id)
        return {"record_id": record_id, "sources":items}

    @routes.post(PREFIX+"/runs")
    @mutation
    async def create(request):
        local(request)
        data = await body(request)
        context = service.control_context(actor(request, data))
        run = await asyncio.to_thread(service.create, identifier(data.get("record_id")), data.get("file_id"),
                                      context=context, step="build" if context["actor"] == "human" else "fit")
        return payload(run)

    @routes.get(PREFIX+"/runs/{id}")
    @endpoint
    async def status(request):
        return payload(service.get(request.match_info["id"]))

    @routes.post(PREFIX+"/runs/{id}/show")
    @mutation
    async def show(request):
        local(request)
        data = await body(request)
        run=service.get(request.match_info["id"])
        service.control.check(actor(request, data, run["id"]))
        notify("mumblebox-foundry-rig-open",{"id":run["id"]})
        return {"id":run["id"],"display_requested":True}

    @routes.post(PREFIX+"/runs/{id}/edit")
    @mutation
    async def edit(request):
        local(request)
        data = await body(request)
        run_id = request.match_info["id"]
        context = admit(request, data, run_id, data.get("revision"))
        if active_drag(run_id):
            return conflict("A joint is being moved in Foundry. Retry after the drag finishes.")
        try:
            run = service.edit(run_id,data.get("revision"),data.get("action"),context=context,
                               **{key:data[key] for key in ("joint","point","mirror","pose","orientation","step",
                                                           "view","test_pose") if key in data})
        except RevisionConflict as error:
            return conflict(error)
        return changed(run, context, data.get("action"), data.get("view") if data.get("action")=="view" else None)

    @routes.post(PREFIX+"/runs/{id}/command")
    @mutation
    async def command(request):
        nonlocal drag_lease
        local(request)
        data = await body(request)
        run_id = identifier(request.match_info["id"])
        identity = actor(request, data, run_id)
        if identity["actor"] == "agent" and displayed()["id"] != run_id:
            raise ValueError("Open the intended rigging session before editing.")
        lease = active_drag(run_id)
        owner = (lease and data.get("drag") == lease["drag"] and data.get("browser") == lease["browser"]
                 and identity["actor"] == "human")
        if lease and not owner:
            return conflict(AgentEditingConflict("human_drag_active",
                "A joint is being moved in Foundry. Retry after the drag finishes."))
        endpoint = {"move":"joint", "orient":"bone_id"}.get(data.get("action")) if owner else None
        if owner and (not endpoint or not isinstance(data.get("args"), dict) or
                      data["args"].get(endpoint) != lease["joint"]):
            return conflict("The drag belongs to a different joint or operation.")
        try:
            run, result = service.command(run_id, data.get("rig_revision"), data.get("request_id"),
                                          data.get("action"), data.get("args", {}), actor_context=identity)
        except RevisionConflict as error:
            return conflict(error)
        finally:
            if owner:
                drag_lease = None
        return {**(payload(run) if result.get("replayed") else changed(run, identity, data.get("action"))),
                "command": result}

    @routes.post(PREFIX+"/runs/{id}/batch")
    @mutation
    async def batch(request):
        local(request)
        data = await body(request, MAX_BATCH_BYTES + 1024)
        run_id = identifier(request.match_info["id"])
        owner = actor(request, data, run_id)
        if owner["actor"] == "agent" and displayed()["id"] != run_id:
            raise ValueError("Open the intended rigging session before editing.")
        if active_drag(run_id):
            raise AgentEditingConflict("human_drag_active", "Finish the current joint drag before editing.")
        revision = data.get("rig_revision")
        if type(revision) is not int or revision < 0:
            raise ValueError("Read the current rig revision before editing.")
        request_id = identifier(data.get("request_id"))
        operation_name = data.get("operation")
        if operation_name == "preview":
            context = service.admit(run_id, revision, owner)
            preview = service.preview_batch(context, data.get("commands"))
            if owner["actor"]=="agent":
                notify(VIEW_EVENT,{"action":"agent-preview","id":run_id,"rig_revision":revision,
                    "preview_id":preview["preview_id"],"count":len(preview["changed_bone_ids"]),
                    "bones":[change["after"] for change in list(preview["bones"].values())[:64]
                             if change["after"] is not None]})
            return preview
        context = {**owner, "run_id": run_id, "expected_rig_revision": revision}
        if operation_name == "discard":
            service.discard_batch(context, data.get("preview_id"))
            if owner["actor"]=="agent":
                notify(VIEW_EVENT,{"action":"agent-preview-ended","id":run_id,"preview_id":data["preview_id"]})
            return {"discarded": True}
        if operation_name == "apply":
            run, receipt = service.commit_batch(context, data.get("preview_id"), request_id)
            return {**(payload(run) if receipt["replayed"] else changed(run, owner, "batch")), "batch": receipt}
        raise ValueError("Choose preview, apply or discard.")

    @routes.post(PREFIX+"/runs/{id}/part-preview")
    @endpoint
    async def preview_part(request):
        local(request)
        data=await body(request)
        run=service.get(request.match_info["id"])
        if data.get("rig_revision")!=run["rig_revision"]:
            return conflict("The rig changed. Read the current revision before placing the part.")
        return {"part":part_layout(run,data)}

    async def run_fit(job, cancelled, initial, source, settings, orientation, preset, context):
        from .fit_mapping import suggest_roles
        from .tokenrig_runtime import fit
        from .runtime import prediction_path

        def check():
            if cancelled.is_set():
                raise ValueError("Local AI fitting was cancelled. The previous joints are still available.")

        def progress(phase):
            job["phase"] = phase

        try:
            async with operation:
                if lifecycle:
                    await lifecycle().barrier()
                    await lifecycle().release("before Local AI rig fitting")
                check()
                destination = prediction_path(service, initial["id"], job["request_id"])
                bones, info = await asyncio.to_thread(fit, source, initial["source"]["sha256"], settings,
                                                      destination, check, progress)
                check()
                suggest_roles(bones, initial["bounds"], orientation)
                run = service.replace_skeleton(initial["id"], initial["revision"], bones,
                    {"method": "local_ai", "preset": preset, "settings": settings, **info}, orientation,
                    context=context)
                changed(run, context, "fit")
                job.update(status="complete",phase="review",revision=run["revision"])
        except Exception as error:
            if isinstance(error, ValueError):
                message = str(error)
            else:
                message = "Local AI setup or fitting could not finish. Check the connection and available disk space, then retry."
            job.update(status="cancelled" if cancelled.is_set() else "failed",error=message)

    @routes.post(PREFIX+"/runs/{id}/fit")
    @mutation
    async def start_fit(request):
        nonlocal fitting
        local(request)
        data = await body(request)
        run_id, revision = identifier(request.match_info["id"]), data.get("revision")
        orientation = data.get("orientation",0)
        if type(orientation) is not int or orientation not in range(4):
            raise ValueError("Choose a supported character direction.")
        method = data.get("method")
        if method == "guided_template":
            context = admit(request, data, run_id, revision)
            try:
                return changed(service.edit(run_id,revision,"reset",orientation=orientation,context=context))
            except RevisionConflict as error:
                return conflict(error)
        if method != "local_ai":
            raise ValueError("Choose Guided Template or Local AI.")
        request_id = identifier(data.get("request_id"))
        preset = data.get("preset","standard")
        settings = fit_settings(preset,data.get("custom",{}))
        identity = actor(request, data, run_id)
        request_key = (run_id,revision,orientation,preset,settings,identity)
        if fitting and fitting[0]["request_id"] == request_id:
            if fitting[3] != request_key:
                raise ValueError("Use a new request ID when changing the fit settings.")
            return {**fitting[0], **({"replayed": True} if identity["actor"] == "agent" else {})}
        context = admit(request, data, run_id, revision)
        if busy() or library.busy():
            raise ValueError("A rigging operation is already running. Try again when it finishes.")
        try:
            initial = service.checked(run_id,revision)
            source = service.source_path(initial)
        except RevisionConflict as error:
            return conflict(error)
        job = {"run_id":run_id,"request_id":request_id,"status":"running","phase":"starting"}
        cancelled = Event()
        task = asyncio.create_task(run_fit(job,cancelled,initial,source,settings,orientation,preset,context))
        fitting = (job,cancelled,task,request_key,context)
        notify(VIEW_EVENT,{"action":"operation","id":run_id,"kind":"fit","job":dict(job),"actor":context["actor"]})
        return dict(job)

    @routes.get(PREFIX+"/runs/{id}/fit")
    @endpoint
    async def fit_status(request):
        local(request)
        if fitting and fitting[0]["run_id"] == request.match_info["id"]:
            return dict(fitting[0])
        return {"status":"idle"}

    @routes.post(PREFIX+"/runs/{id}/fit-cancel")
    @mutation
    async def cancel_fit(request):
        local(request)
        data = await body(request)
        service.control.check(actor(request, data, request.match_info["id"]))
        if fitting and fitting[0]["run_id"] == request.match_info["id"] and fitting[0]["request_id"] == data.get("request_id"):
            fitting[1].set()
            return dict(fitting[0])
        raise ValueError("This fit request is no longer active.")

    async def run_bind(job, cancelled, data, context):
        from .runtime import bind
        try:
            async with operation:
                kwargs = {}
                method = data.get("binding_method")
                if method is not None:
                    kwargs = {"requested_method": method, "progress": lambda phase: job.update(phase=phase)}
                if method == "conditioned" and lifecycle:
                    await lifecycle().barrier()
                    await lifecycle().release("before learned rig binding")
                run = await asyncio.to_thread(bind,service,job["run_id"],data.get("revision"),job["request_id"],
                                              data.get("preset","standard"),data.get("custom"),cancelled.is_set,
                                              context=context,**kwargs)
                changed(run, context, "bind")
                job.update(status="complete",revision=run["revision"])
        except InterruptedError as error:
            job.update(status="cancelled",error=str(error))
        except Exception as error:
            job.update(status="cancelled" if cancelled.is_set() else "failed",
                       error=str(error) if isinstance(error,ValueError) else "Binding could not finish. Your joints are preserved; retry with a lighter mesh or binding preset.")

    @routes.post(PREFIX+"/runs/{id}/bind-start")
    @mutation
    async def start_bind(request):
        nonlocal binding
        local(request)
        from .methods import bind_settings
        data=await body(request)
        run_id,request_id=identifier(request.match_info["id"]),identifier(data.get("request_id"))
        preset=data.get("preset","standard")
        settings=bind_settings(preset,data.get("custom",{}))
        identity = actor(request, data, run_id)
        key=(run_id,data.get("revision"),preset,settings,data.get("binding_method"),identity)
        if binding and binding[0]["request_id"]==request_id:
            if binding[3]!=key:
                raise ValueError("Use a new request ID when changing bind settings.")
            return {**binding[0], **({"replayed": True} if identity["actor"] == "agent" else {})}
        context = admit(request, data, run_id, data.get("revision"))
        if busy() or library.busy():
            raise ValueError("A rigging operation is already running. Try again when it finishes.")
        try:
            service.checked(run_id,data.get("revision"))
        except RevisionConflict as error:
            return conflict(error)
        job={"run_id":run_id,"request_id":request_id,"status":"running","phase":"binding"}
        cancelled=Event()
        task=asyncio.create_task(run_bind(job,cancelled,data,context))
        binding=(job,cancelled,task,key,context)
        notify(VIEW_EVENT,{"action":"operation","id":run_id,"kind":"bind","job":dict(job),"actor":context["actor"]})
        return dict(job)

    @routes.get(PREFIX+"/runs/{id}/bind-status")
    @endpoint
    async def bind_status(request):
        local(request)
        return dict(binding[0]) if binding and binding[0]["run_id"]==request.match_info["id"] else {"status":"idle"}

    @routes.post(PREFIX+"/runs/{id}/bind-cancel")
    @mutation
    async def cancel_bind(request):
        local(request)
        data=await body(request)
        service.control.check(actor(request, data, request.match_info["id"]))
        if binding and binding[0]["run_id"]==request.match_info["id"] and binding[0]["request_id"]==data.get("request_id"):
            binding[1].set()
            return dict(binding[0])
        raise ValueError("This bind request is no longer active.")

    @routes.post(PREFIX+"/runs/{id}/{kind:bind|export|open-blender}")
    @mutation
    async def process(request):
        nonlocal processing
        local(request)
        data = await body(request)
        run_id, kind = request.match_info["id"],request.match_info["kind"]
        context = admit(request, data, run_id, data.get("revision"))
        if busy() or library.busy():
            raise ValueError("A rigging operation is already running. Try again when it finishes.")
        async with operation:
            cancelled = Event()
            processing = (context, cancelled)
            try:
                from .runtime import bind, checked_binding_file
                if kind == "bind":
                    if data.get("binding_method") == "conditioned" and lifecycle:
                        await lifecycle().barrier()
                        await lifecycle().release("before learned rig binding")
                    return changed(await asyncio.to_thread(bind,service,run_id,data.get("revision"),data.get("request_id"),
                                                           data.get("preset","standard"),data.get("custom"),
                                                           cancelled.is_set, requested_method=data.get("binding_method"),
                                                           context=context))
                run = service.checked(run_id,data.get("revision"))
                output = current_output(run)
                if not output:
                    raise ValueError("Bind the current rig before exporting.")
                if kind == "export":
                    from .package import publish
                    result = await asyncio.to_thread(publish,service,run,context=context)
                    return {"record_id":result["id"],"download":f"/mumblebox-foundry/v1/library/{result['id']}/files/archive"}
                path = await asyncio.to_thread(checked_binding_file,service,run,output)
                service.check_context(context, service.get(run_id))
                from ....blender_handoff import open_mesh
                return await asyncio.to_thread(open_mesh,path)
            except RevisionConflict as error:
                return conflict(error)
            except InterruptedError as error:
                return conflict(AgentEditingConflict("cancelled", str(error)))
            finally:
                processing = None

    @routes.get(PREFIX+"/runs/{id}/{name:source\\.glb|rig\\.glb}")
    @endpoint
    async def artifact(request):
        from .runtime import binding_path
        run=service.get(request.match_info["id"])
        name=request.match_info["name"]
        if name == "source.glb":
            path=service.source_path(run)
        else:
            output=weight_preview(run)
            if not output or request.query.get("binding") != output["binding"]:
                raise ValueError("This preview is no longer the current rig.")
            path=binding_path(service,run["id"],output["binding"])/"rig.glb"
            path=owned_path(service.library.output_root,path)
        return web.FileResponse(path,headers={"Content-Type":"model/gltf-binary",
                                               "X-Content-Type-Options":"nosniff","Cache-Control":"no-store"})

    @routes.post(PREFIX+"/live")
    @endpoint
    async def focus(request):
        nonlocal live
        ui_only(request)
        data=await body(request)
        browser=identifier(data.get("browser"))
        if data.get("prepare") is True:
            now = time.monotonic()
            for key, expires in list(preparing.items()):
                if expires <= now:
                    del preparing[key]
            if browser not in preparing and len(preparing) >= 16:
                raise ValueError("Too many rig editors are opening. Try again shortly.")
            preparing[browser] = now + 38
            return {"ready": True}
        if data.get("closed") is True:
            if live and live["browser"]==browser:
                live=None
            return {"active":False}
        state=service.get(data.get("id"))
        if live and live["browser"]!=browser and live["expires"]>time.monotonic() and not data.get("opened"):
            return {"active":False}
        live={"browser":browser,"id":state["id"],"expires":time.monotonic()+38}
        return {"active":True, "agent_control": service.control.status()}

    @routes.post(PREFIX+"/live/control")
    @endpoint
    async def agent_control(request):
        ui_only(request)
        data = await body(request)
        if not browser_owner(data, data.get("id")):
            raise ValueError("Use Stop or Resume in the active Foundry wizard.")
        action = data.get("action")
        if action == "prepare_resume":
            return {"capability": service.control.offer_resume(data["browser"])}
        if action == "resume":
            state = service.control.resume(data.get("capability"), data["browser"])
        elif action == "stop":
            state = service.control.stop("user_stopped")
            for operation_job in (fitting, binding):
                if operation_job and operation_job[4]["actor"] == "agent":
                    operation_job[1].set()
            if processing and processing[0]["actor"] == "agent":
                processing[1].set()
        else:
            raise ValueError("Choose Stop or Resume agent editing.")
        notify(VIEW_EVENT, {"action": "agent-control", "id": live["id"], "agent_control": state})
        return state

    @routes.get(PREFIX+"/live")
    @endpoint
    async def active(request):
        local(request)
        run_id = displayed()["id"]
        return {**payload(service.get(run_id)), "drag_active": bool(active_drag(run_id))}

    @routes.post(PREFIX+"/live/drag")
    @endpoint
    async def drag(request):
        nonlocal drag_lease
        ui_only(request)
        data = await body(request)
        window = displayed()
        run_id, browser = window["id"], window["browser"]
        token = identifier(data.get("drag"))
        if data.get("browser") != browser or data.get("id") != run_id:
            return conflict("This editor no longer owns the active rig.")
        lease = active_drag(run_id)
        if data.get("release"):
            if lease and lease["drag"] == token:
                drag_lease = None
            return {"active": False}
        if lease and lease["drag"] != token:
            return conflict("A different drag is already in progress.")
        run = service.get(run_id)
        if data.get("rig_revision") != run["rig_revision"]:
            return conflict("The rig changed. Select the joint again.")
        joint = data.get("joint")
        if not isinstance(joint, str) or joint not in run["joints"]:
            raise ValueError("Select a joint in the current rig.")
        drag_lease = {"id":run_id, "browser":browser, "drag":token, "joint":joint,
                      "expires":time.monotonic()+DRAG_SECONDS}
        return {"active":True}

    @routes.post(PREFIX+"/live/capture")
    @mutation
    async def capture(request):
        nonlocal pending
        local(request)
        request_data=await body(request)
        view=request_data.get("view","current")
        if view not in CAPTURE_VIEWS:
            raise ValueError("Choose a supported rigging view.")
        window=displayed()
        if pending:
            raise ValueError("A rigging view is already being captured.")
        run=service.get(window["id"])
        if active_drag(run["id"]):
            return conflict("Wait for the current joint drag to finish before capturing the rig.")
        if request_data.get("id",run["id"])!=run["id"] or request_data.get("revision",run["revision"])!=run["revision"]:
            return conflict("The open rig changed. Read it again before capturing.")
        future=asyncio.get_running_loop().create_future()
        token=uuid4().hex
        with_metadata = request_data.get("format") == "json"
        pending={**window,"token":token,"future":future,"revision":run["revision"],
                 "with_metadata":with_metadata, "joints":run["joints"]}
        try:
            notify(VIEW_EVENT, {"action":"capture","id":run["id"],"view":view,
                               "token":token,"browser":window["browser"],"revision":run["revision"]})
            try:
                image, details=await asyncio.wait_for(future,timeout=12)
            except asyncio.TimeoutError:
                raise ValueError("The wizard did not supply a view. Open the rig editor and try again.") from None
            if (service.get(run["id"])["revision"]!=run["revision"] or
                    displayed()["browser"] != window["browser"] or displayed()["id"] != run["id"]):
                raise ValueError("The rig changed during capture. Request the current view again.")
            if with_metadata:
                identity = scene_identity(run)
                camera = details["camera"]
                observation = {**identity, **details, "selected_joint": run["selected_joint"],
                               "selected_ids": [run["selected_joint"]], "view": view,
                               "source_to_display": camera["source_world"], "camera_world": camera["world"],
                               "projection": camera["projection"], "viewport_size": details["size"],
                               "units": {"frame": "glTF Y-up source", "calibrated": False}}
                capture_id = observations.put(window["browser"], observation)
                return {"png":base64.b64encode(image).decode("ascii"),
                        "metadata":observations.get(window["browser"], capture_id, identity)}
            return web.Response(body=image,content_type="image/png",
                                headers={"Cache-Control":"no-store","X-Rig-Revision":str(run["revision"])})
        finally:
            pending=None

    @routes.post(PREFIX+"/live/capture-result")
    @endpoint
    async def capture_result(request):
        ui_only(request)
        data=await body(request,MAX_CAPTURE*4//3+64*1024)
        if (not pending or pending["future"].done() or
            any(data.get(key)!=pending[key] for key in ("browser","token","revision"))):
            return {"accepted":False}
        try:
            binary=base64.b64decode(data.get("png",""),validate=True)
            limit = MAX_JSON_CAPTURE if pending["with_metadata"] else MAX_CAPTURE
            if not 24 <= len(binary) <= limit or binary[:8]!=b"\x89PNG\r\n\x1a\n":
                raise ValueError("The rigging preview is invalid.")
            if not all(1 <= dim <= 1280 for dim in struct.unpack(">II",binary[16:24])):
                raise ValueError("The rigging preview dimensions are invalid.")
        except (binascii.Error, TypeError):
            raise ValueError("The rigging preview is invalid.") from None
        details = {}
        if pending["with_metadata"]:
            camera, visible = data.get("camera"), data.get("visible_joints")
            if (not isinstance(camera, dict) or camera.get("type") not in ("orthographic", "perspective") or
                    type(camera.get("revision")) is not int or not 0 <= camera["revision"] < 2**53):
                raise ValueError("The viewport camera metadata is invalid.")
            matrices = {}
            for name in ("world", "projection", "source_world"):
                matrix = camera.get(name)
                if not isinstance(matrix, list) or len(matrix) != 16 or any(
                    type(value) not in (int, float) or not math.isfinite(value) for value in matrix
                ):
                    raise ValueError("The viewport camera matrix is invalid.")
                matrices[name] = matrix
            if not isinstance(visible, list) or len(visible) > len(pending["joints"]) or any(
                not isinstance(joint, str) or joint not in pending["joints"] for joint in visible
            ):
                raise ValueError("The captured joint list is invalid.")
            details = {"camera":{**matrices,"type":camera["type"],"revision":camera["revision"]},
                       "visible_joints":visible, "size":list(struct.unpack(">II",binary[16:24]))}
        pending["future"].set_result((binary, details))
        return {"accepted":True}

    @routes.post(PREFIX+"/live/probe")
    @endpoint
    async def probe(request):
        local(request)
        data = await body(request)
        window = displayed()
        if active_drag(window["id"]):
            raise ValueError("Wait for the joint drag to finish.")
        pixels = normalized_pixels(data.get("pixels"))
        identity = scene_identity(service.get(window["id"]))
        observation = observations.get(window["browser"], identifier(data.get("capture_id")), identity)
        result = await viewport_requests.ask("probe",window,{"observation":observation,"pixels":pixels},
                                             lambda data: probe_results(data.get("probes"),pixels))
        observations.get(displayed()["browser"], observation["capture_id"], scene_identity(service.get(displayed()["id"])))
        return {"observation": observation, "probes": result}

    @routes.post(PREFIX+"/live/probe-result")
    @endpoint
    async def probe_result(request):
        ui_only(request)
        return viewport_requests.receive("probe",await body(request,512*1024))

    @routes.post(PREFIX+"/runs/{id}/check")
    @mutation
    async def check_rig(request):
        from .diagnostics import checked_metrics, findings, joint_pose, selection_for
        local(request)
        data=await body(request)
        run_id=identifier(request.match_info["id"])
        run=service.get(run_id)
        if type(data.get("rig_revision")) is not int or data["rig_revision"]!=run["rig_revision"]:
            raise RevisionConflict("The rig changed. Inspect the current revision.")
        selection=selection_for(run,data.get("selection"))
        pose=joint_pose(run,data.get("pose"))
        if pose and pose["bone_id"]!=selection["bone_id"]:
            raise ValueError("Choose a test pose for the selected bone.")
        evidence=None
        if current_output(run) and pose:
            window=displayed()
            if window["id"]!=run_id or run["step"]!="review" or active_drag(run_id):
                raise ValueError("Open the current rig in Review to measure a joint pose.")
            identity=scene_identity(run)
            evidence=await viewport_requests.ask("measure",window,
                {"identity":identity,"selection":selection,"pose":pose},
                lambda result:checked_metrics(result.get("metrics")))
            if displayed()["browser"]!=window["browser"] or scene_identity(service.get(run_id))!=identity:
                raise RevisionConflict("The rig changed during the movement check.")
        entries=findings(run,selection,pose,evidence)
        offset=data.get("cursor",0)
        if type(offset) is not int or not 0<=offset<=len(entries):
            raise ValueError("Choose an available findings page.")
        return {"findings":entries[offset:offset+100],"total":len(entries),
                "next_cursor":offset+100 if len(entries)>offset+100 else None}

    @routes.post(PREFIX+"/live/measure-result")
    @endpoint
    async def measure_result(request):
        ui_only(request)
        return viewport_requests.receive("measure",await body(request))

    return service
