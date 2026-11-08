# Create Rigged Hair with HairDeck

Added in Foundry preview.10 on 2026-11-02, following qualification on top of preview.9. The existing image and image-to-3D workflows remain in place.

Preview.13 corrects missing Pinokio dependencies in DINOv3's lazy hub imports and the bundled review renderer. The software installer checks both paths before reporting success. It also restores the native 3D preview's model-format detection and refreshes Retry/navigation after task cleanup. Existing generations can be reopened; this repair does not require regenerating hair.

## Full experience correction (working tree, not published)

The 2026-11-08 repair is governed by `docs/research/2026-11-08-hairdeck-full-experience/REPORT.md`. It adds simultaneous 1–4 variation cards, per-variation reference-head and chain views, visible processing/crop/mask sheets, enlargeable material and UV maps, adding matching chains to saved cards, separate avatar review and head-turn motion, and per-variation saved media. These are HairDeck outputs and controls translated into Foundry's wizard, rather than a claim that a produced GLB proves the experience.

The current official ColorDiT source is adapted from HairDeck `cb20f7073419a33c9ab88f22f686fcb9060a99f0` (Apache-2.0). Its public 734,166,304-byte checkpoint is pinned to `hyz317/HairDeck@7d2e07c5b4b22fbffa2df58d20b242db035ed69c`, SHA-256 `47126c70c06b32fd87e5d419109fee4ba4e23363eba090e3fee00a6ccd8264cc`. It predicts 16 root-to-tip colors per card. First-use preparation includes the selected color weights before generation. The installer declares scikit-image 0.26.0 and probes the actual ColorDiT imports/conversion without weights or GPU allocation.

Predicted card colors require unique UV charts, so the output uses a unique atlas when `colors=true` and `color=auto`. A single-color override supports shared or unique UVs. Both static GLB and VRM use the same appearance bundle; source card JSON retains predicted colors. The package distinguishes predicted base colors from procedural strand/material maps and records the effective exported appearance.

The HairDeck graph remains independent. Generation node 70002 now adapts upstream generation and its color model; node 70005 adds chains to immutable saved cards. The API/MCP operations are `generate`, `rig`, `preview`, `avatar_preview`, `motion_preview`, and `export`. Existing saved runs retain their original single-color meaning and assets on migration. Material changes invalidate stale review media while preserving cards; previews for different variations retain their own identity.

Motion is the official three-second head-turn simulation, optionally showing chains. It is not a promised 360-degree rendered orbit or an exported animation clip. The 3D cards can be orbited interactively. Official model viewers are view-only; full card sculpting is done in an editor using the supplied source data, not in a nonexistent native HairDeck sculpting UI.

The corrected native ComfyUI wizard was exercised with two colored variations, adding chains to saved hair, reference-head/chain review, processing sheets, fitting/material/UV changes, avatar validation, playable motion, color swatch/hex controls, final exports and History/resume. The finished model was visually checked at normal and compact widths. The selected result contains 82 cards and 12 validated spring groups; its 29-file package passed CRC and README/provenance checks. This does not make the older implementation evidence below proof of the corrected release; see [current validation](RELEASE-VALIDATION.md).

## Delivered workflow

The Foundry home card opens a six-page hair wizard: reference image, generation options, generation review, head/materials, motion/exports, and finished result. Hair has its own backend owner, MCP tools, persistent runs and two colored groups beside the existing workflows. The repaired portable graph contains a six-node section, without test images, run identities or output paths. Opening HairDeck upgrades an older saved graph with only its missing HairDeck nodes/groups or old generation adapter; existing workflow inputs, settings, groups and output references are preserved.

- Upload a clear head or upper-body reference with the entire hairstyle visible. Existing camera capture and Gallery selection are shared with the image workflow.
- Recommended generation uses seed 0, 50 steps, CFG 2 and spring bones. One to four variations run sequentially. Advanced controls select the six locally available checkpoint roles, steps and CFG.
- Each variation retains matching cards, tokens and predicted chains. The rotatable static preview, optional chain overlay and preprocessing images support review.
- Export-only changes reuse that saved generation. Controls select a reference-head profile, uniform hair scale and XYZ translation, automatic or explicit hair color, material preset, shared/unique UV layout, and 1K/2K/4K textures. Cards and chains receive the same fitting transform.
- Select static GLB, rigged VRM 0.x, motion MP4, diagnostics and editable source data. ZIP delivery and a History record use the existing catalog/README publisher. The final page contains a 3D viewer, motion video when selected, file downloads and recorded measurements.
- Cancellation, retry identity, source-integrity checks, dependent-result invalidation and model release use the shared queue/lifecycle. Generated checkpoints and user files are retained. Only newly created, owned export/surface helper scratch directories are removed; the reusable CPU preprocessing cache remains.

## Model and software ownership

The existing community implementation is pinned to `FengLairh/ComfyUI-HairDeck@ad27f3433169ca6e1f61396525d30d6ca55428be`. It vendors HairDeck revision `5f1c18a32e622cb8d1acec2a856694fb43375c1a`. The weights/data release is `hyz317/HairDeck@129ad77fba42edfb79a59246f43b11d3fc64c6d1`.

Installation prepares the pinned node software and imports its real entry points without downloading weights. First workflow use prepares and verifies all selected model/data/tool files before generation. The sources and hashes are in `models.lock.json` and the pinned upstream installer. HairDeck, BiRefNet, SAM 3 and DINOv3 acquisition was verified from the documented public distributions without an account token; the DINOv3 public download independently matched SHA-256 `dcb2e45127cccbf1601e5f42fef165eea275c8e5213197e8dcf3f48822718179`. Separate upstream licenses still apply and are retained in the package.

The qualified Windows host uses Python 3.13.12, Torch 2.12.1+cu130 and Transformers 5.16.1. Twelve missing dependencies were explicitly installed without replacing the existing Torch stack. The hair exporter uses its own Blender 4.2.23 and VRM add-on 4.10.2; the existing Blender 5.2 installation and mesh worker environments were preserved. Installer, Pinokio bootstrap/update, dependency manifests and entry-point probes include the new software path.

The seven `foundry_hair_*` MCP tools use the same run owner as the wizard. The installed stdio-to-HTTP protocol check verified capability discovery, run lookup, create/update/cancel/show and invalid-operation rejection, with no additional inference.

## End-to-end evidence

The licensed upstream `ex01.png` example was uploaded through the real wizard. Run `f3e372177ab4425d90f321384ea42ab5`, named **HairDeck — complete workflow review**, generated two variations. The second was selected, changed to a unique 1K atlas, color `#8A4F29`, scale 1.03 and Z offset 0.003 metres, then previewed and exported with motion. Those appearance edits reused the saved generation.

- 113 hair cards; 27 predicted chains; 23 retained chains; 22 validated spring groups.
- 22,342 hair vertices and 34,152 hair triangles. These counts describe the hair surface, not the complete reference avatar.
- Unique UV atlas: 251 charts, no overlap and no degenerate UV triangles reported by the exporter.
- Static GLB, skinned VRM, three-second MP4, maps, diagnostics, source data, provenance, licenses and generated README: 29 files, 13,181,027-byte ZIP.
- ZIP SHA-256: `5bc3a5ed7167eeb75206191583d85ad816b98001e7f4cb2fa1e5c8194e4efbaf`. The actual GUI download matched this checksum. The shared archive validator verified CRC, file hashes and exact README inventory.
- The final viewer loaded the GLB; the motion player reached ready state with a three-second duration. History showed the hair workflow title, thumbnail, package statistics and details.
- Lifecycle release returned zero Torch allocated/reserved memory and zero loaded models after completion.

Focused automated coverage checks configuration bounds, graph/variant identity, export-only reuse, source/path integrity, cancellation and idempotent retries. Existing affected route/library/agent and Pinokio bootstrap checks passed. The installed real-node import probe passed. Physical camera capture was not exercised because no camera was attached.

The final seven-test hair run also verified static-only and VRM-only archive selections, omitted motion/diagnostics/source files, retained thumbnails and exact generated README inventories. The installed source matches the repository's hair runtime, graph and artwork. Release inventory/UTF-8 validation includes the new software, documentation and artwork, without local outputs.

After visual review, the secondary cards were corrected to a consistent 180px height with 150×180 artwork. The card reads **Create Rigged Hair with HairDeck**; the wizard and progress identify HairDeck explicitly. A file drop through the actual starting-image panel uploaded successfully, displayed its preview and preserved the selected Foundry graph. The Gallery picker loaded saved images. Reboot recovery restored the existing Desktop installation and saved workflow without starting a second Comfy backend.

## Scope and limits

This creates stylized volumetric hair cards, not strand-based Unreal Groom. Static GLB has no spring-bone rig. VRM includes a reference avatar and validated skinning/spring groups; rig quality and fitting still need visual review for a particular character. Motion MP4 demonstrates the rig and is not an exported animation clip. Arbitrary full-character automatic fitting, rigged FBX, Alembic Groom and general mesh remeshing/quad conversion are not part of this workflow.

Default behavior and checkpoint selection are wired, but alternate user-supplied weights, every head profile/material combination and all stylized hair shapes have not been quality-qualified. Model access is public through the documented sources; public access does not replace the separate license terms.
