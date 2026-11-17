# Foundry MCP rigging workflow

## Discover tools

Read `foundry_rig_capabilities` and `foundry_rig_current`. Use the advertised tools, `rig_revision`, exact `skeleton.bones`, `agent_control` and recommended binding method. On older clients, use only the available actions. Older builds may limit placement to a reference plane; confirm it from a second angle.

Use `foundry_rig_command` for supported joint and chain operations. Pass the current `rig_revision` and a unique 32-character lowercase hex request ID. Example argument fields for one correction are `joint`, `point` as three values in glTF Y-up world coordinates, and optional `mirror` and `move_children`. For `orient`, use `bone_id` and `roll` in radians. `add_chain` accepts `parent_id`, an explicit array of points and a supported `part`. See the tool schema for other actions. Read the current stage and available poses before changing either with `foundry_rig_edit`.

## Session and source

1. Read the agent connection guidance and rigging capabilities through the advertised workflow API. Resolve the actual client-qualified tool names; Codex and Claude can display different prefixes.
2. Read the active run. Match the user's selected History/export variant and source hash. Opening a different candidate or asset must be explicit; preserve the current session.
3. Capture the actual viewport at the relevant revision. Metadata should identify source, camera, selection and pose. A stale image is not evidence of the state you are editing.

Use the app's existing History selection and all supported wizard entry points. Do not build a private asset list inside the skill or change source files to avoid a missing action.

## Editing and concurrency

- Carry expected rig revision and a request ID for mutating operations. A timed-out response may have succeeded: inspect state or retry the same idempotent request before creating a new one.
- Use stable IDs from the current document. Labels are for people; renaming should not orphan weights or animation.
- Submit a meaningful group of related moves as one supported transaction when available. Retain clear undo boundaries. Avoid sending one network operation per pixel of drag or per vertex.
- Re-read after a revision conflict. Incorporate the user's edit, respect locks and resolve overlapping intent; never force-write the old snapshot.
- Changing camera/selection should not require re-binding. A changed rest skeleton/topology does. Check binding freshness from the service rather than guessing.
- When editing stops, keep read-only inspection available. Do not retry the operation, restart a worker or use a legacy tool to bypass Stop. Report the stop and wait for the person to resume. Old previews expire on control-epoch changes.

## Example correction

1. Capture the selected part with `foundry_rig_view({"view":"part"})`. Use its `capture_id` with `foundry_rig_probe` and up to 16 normalized image points, for example `{"pixels":[[0.52,0.43]]}`. Confirm the marked surface and any suggested pivot from a second view.
2. If useful, save a surface anchor using `landmark_put` with the hit's primitive ID, triangle ID, barycentric values, position and the captured source hash. Read the new rig revision. A marker does not move the bone.
3. Call `foundry_rig_batch` with `operation:"preview"`, the current run/revision, a request ID and one or more action/args objects. For a move, pass the stable joint ID and a reviewed source XYZ point. Check the returned changes, pins and binding effect. Call `operation:"apply"` with that preview ID and keep its request ID for safe retry.
4. Rebind only when needed. In Review, `foundry_rig_edit` with `action:"pose_joint"` accepts a `test_pose` containing the selected `bone_id`, local axis `x`, `y` or `z` and a radians `angle` within ±π/2. Omit the test pose to restore rest.
5. Use `foundry_rig_check` with `selection` containing the `bone_id` and relevant `neighbor_ids`, plus the same optional `pose`. Inspect the returned figures and the actual movement. Report a sample-based finding as sampled evidence.

## Model and binding lifecycle

Read the method's supported inputs, structure limits, presets and resource requirements. Use Foundry's preparation/job service for files, worker isolation, progress and cancellation. Do not install into ComfyUI's interpreter or replace Blender to satisfy a skill instruction.

Keep original prediction and candidates. Record checkpoint/revision, preprocessing transforms, settings and timing. Explain the recorded binding method. For an unchanged TokenRig prediction, the learned-weight bind transfers the model's sampled skin onto the exact History mesh. An edited skeleton can use Blender's deterministic binding while retaining all authored bones. Use a neural edited-skeleton binding only when discovery lists it and the result verifies that the model actually received and preserved the structure.

For a user-edited rig, require explicit conditioning evidence and structure preservation. A loader may otherwise erase an armature while a job still succeeds. Reject missing bones, changed parent relationships or unexpected rest-pose changes beyond documented quantization tolerance. A supported deterministic binding alternative must keep the authored skeleton and disclose the changed method.

## Recovery and proof

Cancel only the owned job. Preserve the last complete rig and edits. Reopen/reconnect to the existing job; do not launch duplicate inference because the view refreshed. If the host is disconnected, verify/recover its actual presentation through supported integration while preserving state.

After an edit, inspect the returned state and a new actual viewport capture. After binding, test the affected movement. After saving, reopen the same run. For export, inspect the package's source/rig signature and load that exact exported file in Blender. Retain material/scale/hierarchy and verify relevant poses there.

Report supported facts plainly: “The index finger now bends independently; the knuckle still pinches” is useful. “Perfect rig” after a success response is not.
