# Asset package layout and root README design

Status: planning only, 2026-10-31. Implementation is not authorized by this document.
Owner: Brian. Repository: C:\Dev\mumblebox-foundry.
Related: [implementation plan](../plans/2026-10-31-asset-package-catalog.md), [README design example](2026-10-31-asset-package-readme-example.md).

## Goal and stopping boundary

Plan the next change to the current standalone ComfyUI finishing graph: organize each exported asset version with its matching files and generate one polished root README.md describing the actual archive. The planning goal is complete when this design, the executable implementation plan, and a representative README are saved, checked against the existing exporter and Brian's requirements, and presented for review. Stop there.

No runtime code, graph, node settings, assets or archives change in this planning pass. No generation/export tests, Blender inspection, GUI work, Groom creation, workflow portability installer, publishing or commits. A later instruction must authorize implementation.

## Accepted document requirements

- One human-and-agent-readable catalog at ZIP root, named README.md. No separate agent guide, resource-index guide or per-directory READMEs.
- Each directory entry follows this exact order: directory name/path; a plain-English paragraph describing its contents and intended use; complete filenames with brief factual descriptions; grouped statistics and relevant recorded validation.
- Use restrained Markdown headings, whitespace, file tables and grouped statistics. No wizard language, suggested next actions, "choose the version", "your next task", marketing slogans or instructions addressed to the reader.
- The opening identifies the asset/package and states what the document records.
- Include Mumblebox information and configured project URLs, production provenance, upstream acknowledgments, resource notices and Brian-approved own terms.
- Describe actual included outputs. Unselected/failed/unsupported variants must not appear as included.
- No invented counts, estimated minimum hardware requirements, approved licenses, website URLs, animation readiness, Unreal compatibility or print certification.
- Paths are package-relative and stable across selection combinations. Exact units, polygon domains, map conventions and verification scope matter.

## Current implementation findings

Read-only source inspection on codex/initial-import at HEAD 062b1f91f01a2302eed114b7b77d12488c449a5d; existing dirty work is preserved.

1. experiments/qwen_pixal_connected/finishing/quad_nodes.py:171-233 owns Hi3DExportBundle, node 3010 in the 93-node Gray Alien Four View Complete graph. It copies detailed/game/print files, produces FBX derivatives, copies quad directories, writes hard-coded AGENT-README.md and RESOURCE-INDEX.md, and builds/checks the ZIP.
2. Its optional balanced/compact/print sockets are effectively compulsory: lazy status requests all three and export unconditionally dereferences them. Quad manifest sockets are not lazy. Future selection must fix both scheduling and inventory.
3. quad_blender.py:109-202 owns existing legacy FBX and quad authoring export/re-import. It writes image-number filenames, maps/ and .fbm copies; OBJ refers to sibling PNGs. Moving folders blindly can break references. Packed BLEND and GLB provide self-contained material data.
4. The current 54-entry file manifest includes internal absolute paths and worker details. The narrative credits mention unused/failed remeshers. Production lineage needs to distinguish used resources from installed alternatives.
5. The print report contains pre-repair and final measurements. The final exported STL is 794,076 triangles; the older source field says 735,580. Reporting must bind checks to the exact exported file/stage, not pick the first matching field.
6. The existing GUI exporter, comfyui_asset_workshop/package_export.py, already has revision checks, a file manifest and atomic archive publication. Reuse those design principles; do not modify the GUI exporter in this standalone change.
7. Git origin is https://github.com/mumblebox-gpt/mumblebox-foundry.git. The proposed project link is https://github.com/mumblebox-gpt/mumblebox-foundry. This is verified as local configuration, not as a publicly accessible release. No approved homepage, Pinokio URL or Mumblebox terms document has been established here.

Read-only live check: selected Gray Alien Four View Complete, 93 nodes, node 3010 Hi3DExportBundle, existing comparison outputs retained, queue empty. Execution graph SHA-256: 1af7d4db5c66ccb9de2a14ffae95dedc90bc2c5000b20e3fa6ca154c85de2dce.

## Proposed archive layout

Only populated directories are emitted. Folder names are not renumbered when other outputs are omitted.

    README.md
    Detailed/
        mesh.glb
        mesh.fbx
        Textures/
    Game/
        Balanced/
            mesh.glb
            mesh.fbx
            Textures/
        Compact/
            mesh.glb
            mesh.fbx
            Textures/
    Editable_Quads/
        Light/
            editable-quads.blend
            editable-quads.obj
            editable-quads.mtl
            editable-quads.fbx
            runtime.glb
            runtime.fbx
            Textures/
    Print/
        mesh.stl
    Metadata/
        manifest.json
    Licenses/
        [exact applicable notice filenames]
        Mumblebox/
            TERMS.md [only when approved and configured]

Light maps to the existing quad_light port, not a promise of a universal polygon budget. Actual target and counts belong in statistics. The existing quad_detail port may map to Editable_Quads/Detail/ only when it supplies a separately successful, validated artifact; this plan does not qualify the failed 50k preset. Groom/ is a reserved future variant path, not an emitted empty directory or selectable working feature.

README.md is the sole explanatory guide. Metadata/manifest.json preserves machine-readable indexing/checksums and is described in the README; it does not contain a competing narrative. Legal notice texts remain separate files because they are source documents. Source images, prompts, raw workflow JSON, model weights, logs, caches and unrelated project files are outside this asset-package selection.

Each variant's texture files live beneath its own Textures/. Names come from the actual material binding: base-color.png, metallic-roughness.png, normal-opengl.png, roughness.png, metallic.png and normal-directx.png only when present. Multiple materials use stable material identifiers in filenames. Never infer map role from image position alone or label the packed MR texture as AO/ORM without evidence.

FBX/OBJ are re-exported or their supported relative references rewritten into the selected variant folder. Prefer the established Blender exporter with relative paths. Preserve exact quad topology, UVs, shading, scale and texture pixels. Pack BLEND dependencies. Copy GLB/STL bytes unchanged. If a supported exporter truly needs a .fbm sidecar, keep it inside the owning variant, list every file in the same directory entry, and prove its reference closure. Do not remove a referenced file merely because it appears duplicated. Deduplicate only within a variant and only after mapping every consumer to the retained identical resource.

## README structure and copy

1. H1: "{asset_name} — Mumblebox Asset Package".
2. Fixed opening: "This package contains the exported assets and associated files listed below. Each directory entry describes its contents, intended use, filenames and recorded specifications."
3. Compact metadata: asset name, export timestamp with timezone, export ID, workflow/package version when recorded. Do not print a missing value as a made-up version.
4. Directory index: actual paths linked to their entries. Organizational parent directories have a short entry; nested texture directories are listed and described within their variant entry. Every file appears exactly once in a file listing.
5. Directory entries, in the layout's stable order:
   - Heading uses the exact relative directory path.
   - Paragraph describes the contents and intended use.
   - Files table: relative filename/link, what it contains. No numerical statistics before this table.
   - Geometry statistics; texture statistics; dimensions/units/orientation; validation and limitations. Use only relevant groups.
6. Production record: stage, resource/tool, version/revision when recorded, source link, applicable notice link. Actual successful lineage only.
7. About Mumblebox: concise product description, configured GitHub, homepage and Pinokio links when set. No unavailable URLs or promotional claims.
8. Terms and notices: link the approved Mumblebox terms when available; identify upstream documents separately. Asset licensing is a separate explicitly supplied field, not inferred from tool/model licenses.

A directory's file list uses paths relative to that directory; Markdown link targets are relative to ZIP root. Escape Markdown-sensitive display text and percent-encode link components. Only controlled internal anchors and safe configured HTTP(S) links are rendered. Do not embed raw user HTML.

The complete readable document must stand alone. JSON is optional for a reader. Preserve the concrete selected-file list and explicit conventions rather than relying on prose guesses by an agent.

## Measurements and evidence

- Report actual triangles/quads/ngons and vertices per authoritative mesh, with the file/measurement basis. Render vertices split at UV seams can differ from welded geometry counts.
- Distinguish editable base mesh counts from evaluated modifiers and any hidden comparison object in BLEND. Never add both and call that the asset's polygon count.
- Texture sizes are measured from included resources. Per-map roles, channels, color space, normal handedness and consumer files are explicit.
- Show dimensions in the file's axes and units. Generated metre-scale geometry is not a measured physical object. STL has no inherent unit metadata: record the intended millimetres from its stage receipt.
- Use final file-bound checks over intermediate/source-stage fields. A report must match the output digest, or its checks are labeled historical/source-only rather than attached to the final export.
- Validation records have pass/fail/not_run/not_recorded states. Missing data is never zero or success. A failed structural export/reference/hash check blocks publication; known visual limitations can be included factually.
- Topological closure, self-intersections, wall thickness, physical printing, rigging, deformation and engine import are separate properties.
- The failed 50k candidate is not an included output. Historical tests do not belong in a selected asset directory's inventory.

## Selection and publication contract

Use one normalized catalog for archive members, README and manifest. A request represents desired outputs; the catalog represents successful staged outputs and their required dependencies.

Blank selection preserves old graph behavior for connected/explicitly supplied variants: include all supported formats available from those inputs. Explicit selections name variants and formats. An omitted variant must not be evaluated solely by the packager, copied, given a directory, or described as included. Other output nodes in the full graph can still cause generation; packaging selections are not yet the future GUI's full run scheduler.

Unsupported or explicitly requested-but-missing outputs fail with the exact variant/format named. Do not silently return an apparently complete subset. An unrequested disconnected optional branch is skipped. At least one mesh/asset output is required. Selected OBJ implies MTL plus all referenced maps; selected FBX implies its dependencies; maps needed by selected formats cannot be unchecked independently. No unconditional access to old saved paths.

Build a new unique staging folder and .partial ZIP, validate it, then atomically publish the final ZIP. Preserve all prior assets and archives. Cancellation/interruption leaves no new successful ZIP and no changed original. All archive-relative paths must reject traversal, absolute/drive/UNC paths, symlink escape and case-insensitive collisions.

Order: resolve request -> close dependencies -> stage outputs/relative references -> inspect final files and bind evidence -> render README -> hash members including README -> write Metadata/manifest.json -> ZIP -> CRC/exact-member/hash/link checks -> atomic rename. The manifest excludes its own hash; this exception is explicit. Final ZIP size/hash remain in a local receipt, avoiding self-referential document content.

Public metadata is allowlisted; worker paths, usernames, environment variables, arbitrary prompts and logs stay local. The README has no unconfigured links or boilerplate legal text. Missing Mumblebox terms are recorded plainly as "Mumblebox terms: not supplied for this export"; the node reports that configuration gap. Do not invent terms or require Brian to draft them before this plan can finish. A configured but missing terms file is an error.

## Project identity and resource policy

Proposed About copy: "Mumblebox combines image-to-3D generation, mesh refinement, cleanup, texturing and export in a configurable workflow." Project identity is a versioned, portable metadata document, not hard-coded into README rendering.

Store approved name, description, URLs and optional terms-relative-path/version/hash in package_identity.json. Default unknown homepage/Pinokio/terms fields to null; omit missing links. Keep authored terms unchanged and separate from upstream notices. The existing model lock and notice files are candidate sources, not proof every resource was used in a run. A small resource registry maps the actual lineage IDs to names, source/revision and notice files. Missing required notice coverage must be identified before public release; do not blanket-credit unrelated tools.

## Scope of the later implementation

Extend Hi3DExportBundle in place, keeping its ID, old input/widget ordering and return types. Append metadata/selection controls and optional file-bound stage receipts. Keep lazy scheduling selection-aware. Add focused catalog/README helpers alongside the finishing module. Reuse isolated Blender workers for format/path verification; no new AI inference or topology changes.

The current graph's generation/refinement/cleanup/baking nodes and Mumblebox GUI remain unchanged. The later proof repackages saved alien outputs and checks one all-output archive and one compact-only selection in the existing native Comfy window, without rerunning upstream models.

Groom creation, clean-machine workflow installation, GUI export checkboxes and actual Blender deformation review remain separately authorized follow-ups.


## Single Image production and closed-quad fallback — local 2026-11-08

Single Image or Text uses the existing selected-variant catalog and package layout. Its production record identifies the pinned official single-image template, actual model revisions/checksums, original reference hash, settings and optional image-creation lineage; it must not invent a turnaround stage or Qwen resource use when the reference was uploaded.

QuadriFlow is optional. When it introduces openings outside the existing bounded small-hole gate on a closed component, the worker may use topology-preserving reduction and planar triangle-to-quad subdivision. Report that fallback in variant warnings and the package README; do not label its edge flow as a pure QuadriFlow result or animation-ready. The selected quad authoring file retains quad faces and its runtime GLB is triangulated. Texture baking remains required. Saved masters and other successful variants remain unchanged.

## Optional grounded export frame

Single Image can choose level/place/original final orientation. Compute a near-upright stable support pose from its clean checkpoint, then apply a proper rigid transform after texturing/baking. Keep all raw stage files untouched. GLB placement is baked into dense position/normal/tangent attributes; UV/index/image buffers remain intact. Blender authoring exports receive the corresponding Z-up transform. Each reduced variant receives a measured vertical floor correction; print STL retains its requested height. Record the master transform, correction angle and support limits in production metadata and per-variant grounding measurements. A stable resting pose is not a guarantee of intentional semantic orientation or coplanar imperfect feet.

Final wizard previews must reference actual grounded output files. Keeping original orientation must restore original-frame previews, including print. Preview-only derivatives for formats without a GLB remain durable outside the public ZIP and inside the owned output tree.
