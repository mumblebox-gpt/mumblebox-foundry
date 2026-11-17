"""Persistent rigging sessions shared by the UI and local MCP."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from threading import RLock
import time
from uuid import uuid4

from ...artifacts import digest, fingerprint
from .commands import STRUCTURAL_ACTIONS, apply_edit
from .control import AgentControl
from .document import SCHEMA_VERSION, geometry_key, guided_skeleton, landmarks, migrate, validate_skeleton
from .geometry import POSES, bone_frame, mesh_bounds, template
from .weights import weight_key


class RevisionConflict(ValueError):
    code = "stale_revision"


class ExpiredPreview(ValueError):
    code = "expired_preview"


MAX_COMMANDS = 64
MAX_BATCH_BYTES = 256 * 1024
PREVIEW_TTL = 120
MAX_PREVIEWS_PER_RUN = 4
MAX_PREVIEWS = 64


class RigSessions:
    def __init__(self, root, library):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.library = library
        self.lock = RLock()
        self.control = AgentControl(self.root / "agent-control.json", self.lock)
        self.previews = {}

    def sources(self, record_id):
        record = self.library.record(record_id)
        return source_files(record) if record["kind"] == "mesh" else []

    def create(self, record_id, file_id, *, context=None, step="fit"):
        record = self.library.record(record_id)
        source = next((item for item in source_files(record) if item["id"] == file_id), None)
        if not source:
            raise ValueError("Choose a recorded static GLB from this export.")
        path = self.library.file(record_id, file_id)
        key = hashlib.sha256(f"{record_id}:{file_id}".encode()).hexdigest()[:32]
        with self.lock:
            self.control.check(context)
            if self.path(key).exists():
                return self.get(key)
        try:
            bounds, vertices = mesh_bounds(path)
        except (IndexError, KeyError, TypeError):
            raise ValueError("The GLB mesh data could not be read.") from None
        identity = {"fingerprint": fingerprint(path), "sha256": digest(path)}
        self.library.file(record_id, file_id)
        with self.lock:
            self.control.check(context)
            if self.path(key).exists():
                return self.get(key)
            state = {"id": key, "schema_version": SCHEMA_VERSION, "revision": 0, "rig_revision": 0,
                     "view_revision": 0, "source": {**source, "record_id": record_id,
                     "asset_name": record["name"], **identity},
                     "bounds": bounds, "vertices": vertices, "skeleton": guided_skeleton(template(bounds)),
                     "orientation": 0, "selected_joint": "elbow.L", "pose": "rest", "step": step,
                     "undo": [], "redo": [], "output": None, "surface_landmarks": []}
            return self.save(state)

    def path(self, run_id):
        return self.root / (identifier(run_id) + ".json")

    def get(self, run_id):
        with self.lock:
            path = self.path(run_id)
            if not path.is_file():
                raise ValueError("This rigging session is no longer available.")
            return session_view(migrate(json.loads(path.read_bytes())))

    def save(self, state):
        path = self.path(state["id"])
        payload = json.dumps({key: value for key, value in state.items() if key != "joints"}, allow_nan=False)
        with self.lock:
            partial = path.with_suffix(".tmp")
            if path.is_file():
                original = path.read_bytes()
                version = json.loads(original).get("schema_version", 1)
                legacy = path.with_suffix(f".v{version}.json")
                if version in (1, 2) and version < state["schema_version"] and not legacy.exists():
                    backup = legacy.with_suffix(".tmp")
                    backup.write_bytes(original)
                    backup.replace(legacy)
            partial.write_text(payload, encoding="utf-8")
            partial.replace(path)
        return session_view(state)

    def source_path(self, run):
        source = run["source"]
        path = self.library.file(source["record_id"], source["id"])
        if fingerprint(path) != source["fingerprint"]:
            raise ValueError("The source mesh changed. Reopen an owned History mesh.")
        return path

    def checked(self, run_id, revision):
        state = self.get(run_id)
        if type(revision) is not int or revision != state["revision"]:
            raise RevisionConflict("The rig changed. Read the current revision before editing.")
        return state

    def admit(self, run_id, expected_rig_revision, actor_context):
        with self.lock:
            run = self.get(run_id)
            context = self.control_context(actor_context)
            if type(expected_rig_revision) is not int or expected_rig_revision != run["rig_revision"]:
                raise RevisionConflict("The rig changed. Read the current revision before editing.")
            return {**context, "run_id": run_id, "expected_rig_revision": expected_rig_revision,
                    "source_sha256": run["source"]["sha256"]}

    def control_context(self, actor_context):
        with self.lock:
            if actor_context.get("actor") not in ("human", "agent"):
                raise ValueError("Open the rig in Foundry or connect a local agent.")
            self.control.check(actor_context)
            return {**actor_context, "control_epoch": self.control.status()["epoch"]}

    def check_context(self, context, run):
        if context is None:
            return
        self.control.check(context)
        if (context["run_id"] != run["id"] or context["expected_rig_revision"] != run["rig_revision"]
                or context["source_sha256"] != run["source"]["sha256"]):
            raise RevisionConflict("The rig changed. Read the current revision before editing.")

    def replace_joints(self, run_id, revision, joints, orientation, fit):
        return self.replace_skeleton(run_id, revision, guided_skeleton(joints)["bones"], fit, orientation)

    def replace_skeleton(self, run_id, revision, bones, fit, orientation=None, *, context=None):
        skeleton = validate_skeleton({"bones": bones})
        if fit.get("prediction_id"):
            fit = {**fit, "prediction_geometry": geometry_key(skeleton)}
        with self.lock:
            run = self.checked(run_id,revision)
            self.check_context(context, run)
            self.source_path(run)
            remember_fit(run)
            run.update(skeleton=skeleton, fit=fit, pose="rest", step="fit", revision=revision+1,
                       rig_revision=run["rig_revision"]+1, weight_edits=[], weight_locks=[], joint_pose=None)
            if orientation is not None:
                run["orientation"] = orientation
            if run["selected_joint"] not in landmarks(skeleton)[0]:
                run["selected_joint"] = bones[0]["id"]
            return self.save(run)

    def command(self, run_id, rig_revision, request_id, action, args, *, actor_context=None):
        identifier(request_id)
        if action not in (*STRUCTURAL_ACTIONS, "undo", "redo") or not isinstance(args, dict):
            raise ValueError("Choose a supported rig edit.")
        # Keep receipts saved by earlier versions replayable.
        content = json.dumps([rig_revision, action, args], sort_keys=True, allow_nan=False)
        request_hash = hashlib.sha256(content.encode()).hexdigest()
        with self.lock:
            run = self.get(run_id)
            if receipt := self.replay(run, request_id, request_hash, actor_context):
                return run, receipt
            context = self.admit(run_id, rig_revision, actor_context) if actor_context is not None else None
            if type(rig_revision) is not int or rig_revision != run["rig_revision"]:
                raise RevisionConflict("The rig changed. Read the current revision before editing.")
            was_bound = current_output(run) is not None
            if action in ("undo", "redo"):
                old = {bone["id"]: bone for bone in run["skeleton"]["bones"]}
                restore_checkpoint(run, action)
                new = {bone["id"]: bone for bone in run["skeleton"]["bones"]}
                changed = sorted(key for key in old.keys() | new.keys() if old.get(key) != new.get(key))
            else:
                remember_fit(run)
                changed = apply_command(run, action, args, request_id)
            advance_geometry_edit(run, review=action in ("weight_stroke","weight_lock") or run["step"]=="review" and action in ("undo","redo"))
            receipt = {"request_id": request_id, "rig_revision": run["rig_revision"],
                       "changed_ids": changed, "binding_stale": was_bound and current_output(run) is None}
            if context is not None:
                receipt.update(control_epoch=context["control_epoch"], replayed=False)
            remember_receipt(run, request_id, request_hash, receipt, actor_context)
            run["revision"] += 1
            return self.save(run), receipt

    def replay(self, run, request_id, request_hash, actor_context, *, batch=False):
        prior = run.get("edit_receipts", {}).get(request_id)
        if prior is None:
            return None
        agent = (actor_context or {}).get("agent_session_id")
        if request_hash != prior["hash"] or prior.get("agent_session_id") != agent:
            raise ValueError("Use a new request ID for a different edit.")
        result = prior["result"]
        if batch or agent:
            result = {**result, "replayed": True}
            if agent:
                result["applied_before_stop"] = result["control_epoch"] != self.control.status()["epoch"]
        return result

    def preview_batch(self, context, commands):
        if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_COMMANDS:
            raise ValueError(f"Preview 1 to {MAX_COMMANDS} related rig edits.")
        if any(not isinstance(item, dict) or set(item) != {"action", "args"}
               or item["action"] not in STRUCTURAL_ACTIONS or not isinstance(item["args"], dict)
               for item in commands):
            raise ValueError("Send supported structural commands with their arguments.")
        content = encode_edit(commands)
        if len(content) > MAX_BATCH_BYTES:
            raise ValueError("The rigging batch is too large.")
        preview_id = uuid4().hex
        run_id = context["run_id"]
        with self.lock:
            run = self.get(run_id)
            self.check_context(context, run)
            candidate = deepcopy(run)
            apply_batch(candidate, commands, preview_id)
            differences = bone_differences(run, candidate)
            now = time.monotonic()
            for key, entry in list(self.previews.items()):
                if entry["deadline"] <= now:
                    del self.previews[key]
            run_previews = [key for key, entry in self.previews.items() if entry["context"]["run_id"] == run_id]
            if len(run_previews) >= MAX_PREVIEWS_PER_RUN:
                del self.previews[run_previews[0]]
            if len(self.previews) >= MAX_PREVIEWS:
                del self.previews[next(iter(self.previews))]
            preview = {
                "preview_id": preview_id, "run_id": run_id, "base_rig_revision": run["rig_revision"],
                "command_hash": hashlib.sha256(content).hexdigest(), "commands": deepcopy(commands),
                "changed_bone_ids": list(differences), "bones": differences,
                "binding_effect": "stale" if current_output(run) and not current_output(candidate) else "unchanged",
                "weight_scope": sorted({item["args"]["bone_id"] for item in commands
                                        if item["action"] in ("weight_stroke", "weight_lock")}),
                "warnings": ["compare_mirrored_surface"] if any(
                    item["action"]=="mirror_chain" or item["args"].get("mirror") is True for item in commands) else [],
                "expires_at": time.time() + PREVIEW_TTL,
            }
            self.previews[preview_id] = {"data": preview, "deadline": now + PREVIEW_TTL, "context": dict(context),
                                         "binding": (run.get("output") or {}).get("binding")}
            return deepcopy(preview)

    def get_preview(self, context, preview_id):
        entry = self.previews.get(identifier(preview_id))
        if entry is None or entry["deadline"] <= time.monotonic():
            raise ExpiredPreview("The rigging preview expired. Create a new preview.")
        original = entry["context"]
        keys = ("run_id", "actor", "active_browser_id", "agent_session_id")
        if any(original.get(key) != context.get(key) for key in keys):
            raise ValueError("Preview the edits in this editor before applying them.")
        if original["expected_rig_revision"] != context["expected_rig_revision"]:
            raise RevisionConflict("The rig changed. Preview the edits again.")
        return entry

    def commit_batch(self, context, preview_id, request_id):
        identifier(request_id)
        request_hash = edit_hash(["batch", context["expected_rig_revision"], preview_id])
        with self.lock:
            run = self.get(context["run_id"])
            if receipt := self.replay(run, request_id, request_hash, context, batch=True):
                return run, receipt
            self.control.check(context)
            entry = self.get_preview(context, preview_id)
            original, preview = entry["context"], entry["data"]
            self.check_context(original, run)
            if (run.get("output") or {}).get("binding")!=entry["binding"]:
                raise RevisionConflict("The binding changed. Preview the edits again.")
            if preview["command_hash"] != edit_hash(preview["commands"]):
                raise ValueError("Preview the changed rig edits again.")
            was_bound = current_output(run) is not None
            remember_fit(run)
            apply_batch(run, preview["commands"], preview_id)
            review = run["step"] == "review" and all(
                item["action"] in ("weight_stroke", "weight_lock") for item in preview["commands"])
            advance_geometry_edit(run, review=review)
            run["revision"] += 1
            receipt = {"request_id": request_id, "applied_revision": run["rig_revision"], "replayed": False,
                       "changed_bone_ids": preview["changed_bone_ids"], "control_epoch": original["control_epoch"],
                       "binding_stale": was_bound and current_output(run) is None}
            remember_receipt(run, request_id, request_hash, receipt, context)
            saved = self.save(run)
            del self.previews[preview_id]
            return saved, receipt

    def discard_batch(self, context, preview_id):
        with self.lock:
            self.control.check(context)
            self.get_preview(context, preview_id)
            del self.previews[preview_id]

    def edit(self, run_id, revision, action, *, joint=None, point=None, mirror=False, pose=None, orientation=None,
             step=None, context=None, test_pose=None, view=None):
        with self.lock:
            run = self.checked(run_id, revision)
            self.check_context(context, run)
            if action in ("select","move") and joint not in run["joints"]:
                raise ValueError("Choose one joint in the current skeleton.")
            if action in {"move","reset"}:
                remember_fit(run)
            if action == "move":
                apply_command(run, "move", {"joint": joint, "point": point, "mirror": mirror}, None)
            elif action == "select":
                run["selected_joint"] = joint
            elif action == "reset":
                if type(orientation) is not int or orientation not in range(4):
                    raise ValueError("Choose a supported character direction.")
                run["orientation"] = orientation
                run["skeleton"] = guided_skeleton(template(run["bounds"], orientation))
                run["fit"] = {"method":"guided_template"}
                run.update(weight_edits=[], weight_locks=[])
            elif action in ("undo", "redo"):
                restore_checkpoint(run, action)
            elif action == "pose":
                output = current_output(run)
                offered = output["report"].get("pose_seconds", POSES) if output else ()
                if pose not in offered:
                    raise ValueError("Bind this skeleton before choosing a test pose.")
                run["pose"] = pose
                run["joint_pose"] = None
            elif action == "pose_joint":
                from .diagnostics import joint_pose
                if not current_output(run) or run["step"]!="review":
                    raise ValueError("Bind the current skeleton and open Review to test one joint.")
                run["joint_pose"] = joint_pose(run, test_pose)
                run["pose"] = "rest"
            elif action == "view":
                if view not in ("current","front","side","back","oblique","part"):
                    raise ValueError("Choose one of the supported rigging views.")
            elif action == "step":
                if step not in ("build", "fit", "review", "export"):
                    raise ValueError("Choose a supported rigging step.")
                if step == "export" and not current_output(run):
                    raise ValueError("Bind the current skeleton and review it before exporting.")
                run["step"] = step
                if step in ("build", "fit"):
                    run["pose"] = "rest"
                if step != "review":
                    run["joint_pose"] = None
            else:
                raise ValueError("Choose select, move, reset, undo, pose or step.")
            if action in ("move","reset","undo","redo"):
                advance_geometry_edit(run, review=run["step"]=="review" and action in ("undo","redo"))
            else:
                run["view_revision"] += 1
            run["revision"] += 1
            return self.save(run)


def identifier(value):
    if not isinstance(value,str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Choose a valid rigging session.")
    return value


def encode_edit(data):
    return json.dumps(data, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")


def edit_hash(data):
    return hashlib.sha256(encode_edit(data)).hexdigest()


def apply_command(run, action, args, request_id):
    if action in ("role", "side") and current_output(run) and "pose_key" not in run["output"]:
        run["output"] = {**run["output"], "pose_key": pose_key(run)}
    changed = apply_edit(run, action, args, request_id)
    if action == "remove_chain":
        surviving = {bone["id"] for bone in run["skeleton"]["bones"]}
        run["weight_edits"] = [edit for edit in run.get("weight_edits", []) if edit["bone_id"] in surviving]
        run["weight_locks"] = [bone for bone in run.get("weight_locks", []) if bone in surviving]
    return changed


def apply_batch(run, commands, preview_id):
    for index, item in enumerate(commands):
        command_id = edit_hash([preview_id, index])[:32]
        apply_command(run, item["action"], item["args"], command_id)


def bone_differences(before, after):
    old = {bone["id"]: bone for bone in before["skeleton"]["bones"]}
    new = {bone["id"]: bone for bone in after["skeleton"]["bones"]}
    return {key: {"before": old.get(key), "after": new.get(key)}
            for key in sorted(old.keys() | new.keys()) if old.get(key) != new.get(key)}


def remember_receipt(run, request_id, request_hash, receipt, actor_context):
    requests = run.setdefault("edit_receipts", {})
    requests[request_id] = {"hash": request_hash, "result": receipt,
                            "agent_session_id": (actor_context or {}).get("agent_session_id")}
    if len(requests) > 128:
        requests.pop(next(iter(requests)))


def source_files(record):
    result = []
    for item in record.get("catalog", {}).get("files", []):
        name = item.get("path", "")
        variant = item.get("variant_id")
        if (name.lower().endswith(".glb") and variant not in ("rigged","wearable")
                and item.get("kind", item.get("role")) in ("mesh","geometry","model","asset")
                and item.get("role") not in ("preview","thumbnail")):
            result.append({"id":hashlib.sha256(name.encode()).hexdigest()[:24], "name":name,"variant":variant})
    return result


def skeleton_key(run):
    return geometry_key(run["skeleton"])


def pose_key(run):
    settings = [(bone["id"], bone.get("role"), bone.get("side"), bone.get("anatomical_name"),
                 bone.get("landmark_label")) for bone in run["skeleton"]["bones"]]
    return hashlib.sha256(json.dumps(settings, separators=(",",":")).encode()).hexdigest()


def fit_receipt(run):
    return run.get("fit", {"method":"guided_template"})


def remember_fit(run):
    checkpoint(run, "undo")
    run["redo"] = []


def checkpoint(run, stack):
    run[stack] = [*run[stack][-19:], {"skeleton": deepcopy(run["skeleton"]), "orientation": run["orientation"],
                                      "fit": fit_receipt(run), "selected_joint": run["selected_joint"],
                                      "weight_edits": run.get("weight_edits", []).copy(),
                                      "weight_locks": run.get("weight_locks", []).copy(),
                                      "surface_landmarks": deepcopy(run["surface_landmarks"]),
                                      "output": run.get("output")}]


def restore_checkpoint(run, action):
    if not run[action]:
        raise ValueError(f"There is no joint edit to {action}.")
    checkpoint(run, "redo" if action == "undo" else "undo")
    previous = run[action].pop()
    saved_output = previous.pop("output", None)
    run.update({"weight_edits": [], "weight_locks": [], "surface_landmarks": [], **previous})
    if saved_output and not current_output(run):
        run["output"] = saved_output


def advance_geometry_edit(run, review=False):
    if run["selected_joint"] not in landmarks(run["skeleton"])[0]:
        run["selected_joint"] = run["skeleton"]["bones"][0]["id"]
    run.update(pose="rest", joint_pose=None, step="review" if review else "fit", rig_revision=run["rig_revision"]+1)


def session_view(run):
    return {**run, "joints": landmarks(run["skeleton"])[0]}


def current_output(run):
    output=run["output"]
    if (output and output["skeleton"] == skeleton_key(run) and output.get("weight_key") == weight_key(run)
            and ("pose_key" not in output or output["pose_key"] == pose_key(run))
            and output.get("fit",{"method":"guided_template"}) == fit_receipt(run)):
        return output
    return None


def public_state(run):
    from ... import VERSION
    from .commands import tip_id
    selected = run["selected_joint"]
    bone = next((item for item in run["skeleton"]["bones"] if selected in (item["id"],tip_id(item))), None)
    return {**{k:v for k,v in run.items() if k not in ("undo", "redo", "edit_receipts")}, "undo_available": bool(run["undo"]),
            "redo_available": bool(run["redo"]),
            "step":run.get("step", "fit"), "steps":["build", "fit", "review", "export"],
            "bound": current_output(run) is not None, "fit":fit_receipt(run),
            "chains": landmarks(run["skeleton"])[1],
            "local_frame": bone_frame(bone, run["joints"][selected]) if bone else None, "version": VERSION}
