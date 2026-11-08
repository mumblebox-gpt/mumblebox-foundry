# Single Image floor placement — preview.17

Single Image now offers **Level and place on floor**, **Place on floor only**, and **Keep original orientation**. The setting affects final export placement, so changing it reuses geometry, Hi3D refinement, cleanup, texturing and baking checkpoints. Other workflow families retain their existing frames, including the linked splat/mesh coordinates.

The new isolated `Hi3DGroundingFrame` node measures each mesh independently. It uses trimesh stable support poses, accepts only candidates within 30 degrees of the current up direction, chooses the smallest correction and preserves heading with a minimal rotation. It centers/grounds the result without flattening vertices. If no near-upright stable pose is found, it reports translation-only placement. This is geometric support estimation, not recognition of the intended pose of every object.

The frame is applied after inference and baking. Native GLB position, normal and tangent attributes are transformed; UVs, topology and embedded image bytes are retained. Blender authoring files use the corresponding Z-up frame. Reduced variants receive a small measured floor offset; print STL keeps its requested height. The original checkpoints and earlier packages remain untouched. Final GUI previews load the actual grounded files.

## Actual proof

The saved cargo-lander run completed packaging-only with a **13.718295-degree** correction. This number came from its support geometry; it is not a preset in the implementation. The final package is `Single-Image-Cargo-Lander-e5fcf464-3010-8bed9dda.zip`.

| Variant | Triangles / authoring quads | Lowest exported point | Maximum error against the measured rigid frame |
| --- | --- | --- | --- |
| Detailed GLB | 1,893,032 triangles | Y = 0 | 1.58e-8 |
| Compact GLB | 100,000 triangles | Y = 0 | 2.36e-8 |
| Quad runtime GLB | 49,992 triangles | Y = 0 | 2.85e-8 |
| Editable BLEND | 24,996 quads | Z = 0 | Blender relocated re-import: matching bounds |

Indices/faces and embedded image bytes matched the original GLBs. The package’s existing Blender 5.2.2 verification reopened the actual GLB and BLEND files and checked counts, UV layers, bounds and packaged material images. The native Comfy viewer loaded the grounded output with its floor at zero, and the result was visually inspected. The ordinary export action was exercised through the real wizard; inference stages were not repeated.

**Important limit:** one generated landing foot remains slightly shorter than the others (roughly 1.6% of the asset width above the support plane). The object has a stable three-point resting pose. A rigid orientation correction cannot make imperfect feet exactly coplanar; that would require a separate shape edit. Grounding does not certify collision, physical stability under arbitrary forces, semantic pose or printability.

Four focused geometry tests cover a different synthetic tilt, already-level and translation/original modes, near-upright rejection, no added yaw, distance preservation, coordinate conversion, GLB topology and invalid inputs. Two additional Single Image tests cover package-only invalidation and saved-checkpoint graph wiring. The host declares scipy/networkx alongside trimesh and the normal installer probes the stable-pose entry point. No model or new AI runtime is added.

Sources: [trimesh stable poses](https://trimesh.org/trimesh.poses.html), [SciPy convex hull](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.ConvexHull.html).

The initial local repair plan prohibited publication. Brian subsequently authorized committing and publishing after verification, while explicitly forbidding an update of the installed Pinokio copy. No installed Pinokio update or direct edit is part of this release verification.
