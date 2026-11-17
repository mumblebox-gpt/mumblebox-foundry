"""MCP controls for the open Foundry rigging session and its rendered view."""
import base64
import json
from typing import Annotated, Any, Literal

from mcp.types import ImageContent, TextContent
from pydantic import Field

from client import identifier
from tool_contracts import LOCAL, READ, RunId, tool_registration


def register(server, client, checked):
    tool = tool_registration(server, checked)

    @tool(READ)
    def foundry_rig_current() -> dict[str,Any]:
        """Read the open rig: exact mesh, shared wizard step, revision, selected joint, coordinates, pose and binding validity."""
        return client.request("/rigging/live")

    @tool(READ)
    def foundry_rig_capabilities() -> dict[str, Any]:
        """Read available rigging actions, parts, poses, presets and runtime setup requirements."""
        return client.request("/rigging/capabilities")

    @tool(LOCAL)
    def foundry_rig_command(
        run_id: RunId,
        rig_revision: Annotated[int, Field(ge=0, description="Skeleton revision from foundry_rig_current.")],
        request_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$", description="Reuse this ID when retrying the same edit.")],
        action: Literal["move", "orient", "label", "role", "lock", "add_chain", "add_part", "remove_chain", "reparent",
                        "mirror_chain", "pair",
                        "weight_stroke", "weight_lock", "landmark_put", "landmark_remove", "side",
                        "refit_branch", "undo", "redo"],
        args: Annotated[dict[str, Any], Field(description=(
            "move: joint, point [X,Y,Z], optional mirror/move_children. orient: bone_id, roll in radians. "
            "label: bone_id, label. role: bone_id, role, optional digit for a finger. lock: bone_id, locked. "
            "add_chain: parent_id, points in glTF Y-up, part. remove_chain: bone_id. "
            "add_part: parent_id, part, tip, segments, optional width_point, waypoints, digit. "
            "mirror_chain: bone_id, optional parent_id, axis, center. pair: bone_id, other, optional axis, center. "
            "reparent: bone_id, parent_id or null. weight_lock: bone_id, locked. "
            "weight_stroke: bone_id, mode (paint/add/subtract/smooth/rigid), points (1–24 surface positions), "
            "radius in source units, strength 0–1, and optional target 0–1. Requires a matching prior bind and a rebind to review. "
            "side: bone_id, side (L, R or null), optional apply_to_branch. "
            "landmark_put: source_sha256, primitive_id, triangle_id, barycentric and position from an anchorable probe hit; "
            "optional id, label and joint_id. landmark_remove: id. "
            "refit_branch: root_id, candidate_points mapping joint IDs to source XYZ, optional fixed_ids and landmark_ids. "
            "A refit preserves the branch attachment and all outside bones. Rebinding weights is separate. "
            "undo/redo: empty object."
        ))],
    ) -> dict[str, Any]:
        """Edit the open rig through the shared wizard commands. Check the actual viewport before and after structural edits."""
        active = client.request("/rigging/live")
        if active["id"] != identifier(run_id):
            raise ValueError("Open the intended rigging session in Foundry before editing.")
        return client.request(f"/rigging/runs/{run_id}/command", {
            "rig_revision": rig_revision, "request_id": request_id, "action": action,
            "args": args, "origin": "agent",
        })

    @tool(LOCAL)
    def foundry_rig_batch(
        run_id: RunId,
        rig_revision: Annotated[int, Field(ge=0)],
        request_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")],
        operation: Literal["preview", "apply", "discard"],
        commands: Annotated[list[dict[str, Any]] | None, Field(max_length=64,
            description="For preview, up to 64 related action/args objects using the advertised structural commands.")] = None,
        preview_id: Annotated[str | None, Field(pattern=r"^[0-9a-f]{32}$",
            description="The previous preview ID, required to apply or discard.")] = None,
    ) -> dict[str, Any]:
        """Preview related edits without saving. Apply a reviewed preview as one undoable change; retry an apply with the same request ID."""
        active = client.request("/rigging/live")
        if active["id"] != identifier(run_id):
            raise ValueError("Open the intended rigging session in Foundry before editing.")
        return client.request(f"/rigging/runs/{run_id}/batch", {
            "rig_revision": rig_revision, "request_id": request_id, "operation": operation,
            "commands": commands, "preview_id": preview_id,
        })

    @tool(READ, structured_output=False)
    def foundry_rig_view(
        view: Annotated[Literal["current","front","side","back","oblique","part"], Field(description="View from the open wizard, or a close-up of the selected part.")] = "current",
    ) -> list[TextContent | ImageContent]:
        """See the actual wizard viewport and skeleton to judge joint placement or deformation. Requires the open rig editor."""
        run = client.request("/rigging/live")
        request = {"view":view,"revision":run["revision"],"id":run["id"]}
        if "drag_active" in run:
            capture = client.request("/rigging/live/capture", {**request,"format":"json"})
            return [TextContent(type="text",text=json.dumps(capture["metadata"])),
                    ImageContent(type="image",mimeType="image/png",data=capture["png"])]
        payload = client.request("/rigging/live/capture",request,binary=True)
        summary = {"run_id":run["id"],"revision":run["revision"],"pose":run["pose"],"step":run.get("step","fit"),
                   "selected_joint":run["selected_joint"],"view":view}
        return [TextContent(type="text",text=json.dumps(summary)),
                ImageContent(type="image",mimeType="image/png",data=base64.b64encode(payload).decode("ascii"))]

    @tool(READ)
    def foundry_rig_probe(
        capture_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")],
        pixels: Annotated[list[tuple[float, float]], Field(min_length=1, max_length=16,
            description="Normalized image points from the recent capture, [0,0] top left and [1,1] bottom right.")],
    ) -> dict[str, Any]:
        """Measure surface intersections in a captured wizard view. A geometric span is evidence, not an anatomical joint placement."""
        return client.request("/rigging/live/probe", {"capture_id": capture_id, "pixels": pixels})

    @tool(LOCAL)
    def foundry_rig_edit(
        run_id: RunId,
        revision: Annotated[int, Field(ge=0, description="Revision from the current rig. Read the wizard again after a conflict.")],
        action: Annotated[Literal["select","move","reset","undo","pose","pose_joint","step","view"], Field(description="Select or move a joint, reset, undo, preview a pose, request a camera view, or navigate the wizard.")],
        joint: Annotated[str | None, Field(description="Joint name from the current rig, for example elbow.R.")] = None,
        point: Annotated[list[float] | None, Field(min_length=3, max_length=3, description="Target XYZ in the rig's glTF Y-up coordinates.")] = None,
        mirror: Annotated[bool, Field(description="Mirror a paired joint on the other side for this move.")] = False,
        pose: Annotated[Literal["rest","elbow","arms","crouch","finger","finger_left","finger_right","finger_spread","toe","tail","wing"] | None, Field(description="Select an offered test pose after binding.")] = None,
        step: Annotated[Literal["build","fit","review","export"] | None, Field(description="Wizard step. Export requires a current binding. Fit returns to the rest pose.")] = None,
        orientation: Annotated[int | None, Field(ge=0, le=3, description="Facing for reset: 0 front, 1 right, 2 back, 3 left.")] = None,
        test_pose: Annotated[dict[str, Any] | None, Field(description="For pose_joint in Review: bone_id, local axis x/y/z, angle in radians (±π/2). Omit to reset.")]=None,
        view: Literal["current","front","side","back","oblique","part"] | None=None,
    ) -> dict[str,Any]:
        """Change the open rig without taking desktop focus. UI and agent edits share one revision and undo history."""
        active = client.request("/rigging/live")
        if active["id"] != identifier(run_id):
            raise ValueError("Open the intended rigging session in Foundry before editing.")
        data = {"revision":revision,"action":action,"mirror":mirror}
        data.update({key:value for key,value in (("joint",joint),("point",point),("pose",pose),("step",step),("orientation",orientation)) if value is not None})
        if test_pose is not None:
            data["test_pose"] = test_pose
        if view is not None:
            data["view"] = view
        return client.request("/rigging/runs/"+run_id+"/edit",data)

    @tool(READ)
    def foundry_rig_check(
        run_id: RunId,
        rig_revision: Annotated[int, Field(ge=0)],
        selection: Annotated[dict[str, Any], Field(description="bone_id and optional neighbor_ids (up to 32 comparison bones).")],
        pose: Annotated[dict[str, Any] | None, Field(description="Optional saved-binding test in Review: bone_id, local axis x/y/z, angle in radians.")]=None,
        cursor: Annotated[int, Field(ge=0)]=0,
    ) -> dict[str, Any]:
        """Read attributable rig findings and sampled deformation. Does not save or change the visible pose."""
        return client.request(f"/rigging/runs/{run_id}/check",
                              {"rig_revision":rig_revision,"selection":selection,"pose":pose,"cursor":cursor})
