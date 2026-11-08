# Grounded Single Image exports — implementation plan

**Goal:** level the generated lander on a meaningful support plane and deliver the same grounded pose in the native preview and every selected export, preserving the original checkpoints.

**Design:** use trimesh’s established stable-pose solver on the clean master’s convex hull, retaining only near-upright candidates (at most 30 degrees). Select the smallest correction, remove arbitrary yaw, apply one proper rigid rotation/translation, and center the ground footprint. No flattening, deformation, geometry regeneration or rebaking. If no suitable support plane exists, place on the floor and explicitly report that automatic leveling was unavailable.

Apply the rigid frame in the existing package conversion owner after inference/baking, where it cannot disturb image conditioning. GLB root transforms preserve original embedded geometry/material buffers. Convert the same Y-up transform to Blender Z-up for authoring files, FBX and OBJ. Print exports use the same rotation but retain their selected dimensions and receive their own floor offset. Default Level and place on floor for new Single Image sessions; expose Place on floor and Keep original orientation. Other workflow families retain existing coordinate behavior, especially the paired splat/mesh frame.

## Implementation and verification

- [x] Add a cohesive pure grounding/frame helper and visible plan node, using already-installed numpy/scipy/trimesh. Target tests: tilted multi-foot object, already-level object, original/translation-only modes, rigid distance/topology preservation, bounded tilt and degenerate input.
- [x] Wire the Single Image graph/package inputs, validated setting and wizard choice. Grounding changes invalidate packaging only. Preserve all existing nodes, other methods and saved assets.
- [x] Apply and validate frame conversion in package exports. Record transforms, support measurements and limits in the existing catalog/README. Point final previews at the actual grounded packaged files; label the original clean checkpoint clearly.
- [x] Use the saved lander: rerun packaging only, inspect actual native preview and exported GLB/BLEND floor contact/pose. Run targeted regression checks. Keep the finished result in the existing Comfy app.

Completion means the saved lander is visibly level and floor-placed, selected packaged formats agree, the option is wired for future runs, and targeted checks pass. Brian subsequently authorized committing and publishing after proof. Do not update or directly modify the installed Pinokio copy.

Sources: https://trimesh.org/trimesh.poses.html ; https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.ConvexHull.html

## Verified result

[Grounding validation](../../GROUNDING-VALIDATION.md) records the actual saved-lander export and limits. Detailed/compact/runtime GLBs have Y=0 floor contact, unchanged faces and embedded image bytes; Blender re-imported the 24,996-quad authoring file at Z=0. Four geometry tests and two package-policy tests passed. The generated fourth foot remains shorter; the rigid operation does not claim to reshape it. Publication of preview.17 is now authorized; the installed Pinokio copy remains excluded.
