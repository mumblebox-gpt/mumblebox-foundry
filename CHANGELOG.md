# Changelog

## 0.1.0-preview.16 — Update after a closed runtime

- Allow normal Update after the backend has closed and left a stale runtime record. Require both a refused connection and a confirmed exited runtime; live or uncertain processes, timeouts and active queues still prevent interruption. Saved state is preserved.

## 0.1.0-preview.15 — Community credits and installer resilience

- Reinforce Foundry’s community toolbox approach in About, explain guidance for newcomers, and add a running Thank You section after model credits with specific contributor acknowledgments and source links.
- Refresh the Pinokio description and guide to welcome quality local workflow suggestions, improvements and pull requests, with clear contributor credit.
- Adopt Blender's mirror service and an identifiable Foundry download client, retaining the pinned Blender version and SHA-256 verification. Verified cached archives still avoid network downloads.
- Prevent HairDeck dependency builds from inheriting the removed stdlib distutils implementation from a Pinokio shell. Use setuptools' bundled implementation only in that build subprocess, preserving the parent environment, Torch constraints, current requirements path and both import probes.
- Thanks to [halr9000](https://github.com/halr9000/mumblebox-foundry) for the original installer fixes. Adapted from commits [7c731364](https://github.com/halr9000/mumblebox-foundry/commit/7c731364e92fbec4bec7bb65bed086c59c2210b7) and [3be2d239](https://github.com/halr9000/mumblebox-foundry/commit/3be2d2393e323d4edad404704671e13a9d85566e).

## 0.1.0-preview.14 — HairDeck full wizard experience

- Bring HairDeck's review experience into the existing independent workflow: compare up to four interactive variation cards, choose a variation, toggle its reference head and predicted chains, and inspect processing/crop/mask sheets in the wizard.
- Expose multi-view result sheets and full-size material/UV maps with downloads. Keep fitting and material changes attached to saved hair instead of regenerating it.
- Add matching spring bones to saved cards, separate rigged-avatar and motion previews, per-variation media retention, and an optional chain overlay in HairDeck's head-turn video.
- Add the official HairDeck ColorDiT model for per-card root-to-tip colors, with pinned public first-use preparation, managed GPU residency, checkpoint persistence and matching static/VRM material exports. Preserve older saved single-color runs.
- Add a simple reference-color/custom-color choice with a swatch and optional hex field. Color changes update saved hair materials without regenerating the hairstyle.
- Upgrade older saved graphs with the isolated HairDeck branch while preserving their other nodes, settings and results. Keep the finished viewer visible in compact layouts and remove duplicate finish controls.
- Extend dependency declarations, the real color entrypoint probe, agent operations, source attribution and package documentation. Include the probe in the distributed archive and check that release inventory automatically.

## 0.1.0-preview.13 — HairDeck installation and restored previews

- Fix HairDeck generation and review in Pinokio by explicitly installing the bundled DINOv3 and renderer dependencies: termcolor, six and imageio. Apply the same requirements through normal installs, updates and software repair.
- Extend the installation probe through the real local DINOv3 hub and lazy review renderer. Check these imports before recording installation success, without downloading weights or allocating GPU models.
- Restore HairDeck and Turnaround 3D previews with the newer native ComfyUI viewer. Infer the model filename from existing artifact URLs so the correct loader and owned file endpoint are used. Saved results can be viewed without regenerating them.
- Fix HairDeck controls staying busy after a failed or completed task. Refresh navigation and Retry when background cleanup releases the task.
- Add regression checks for lazy dependency failures, preview URL loading and the final busy-to-idle transition. Verify actual rendered previews separately from generated/exported files.

## 0.1.0-preview.12 — Splat & Solid

- Add **Splat & Solid**, powered by Idol from Sperid Labs, as the third independent method under Create a Mesh from an Image. Its six-page wizard supports upload/drop, camera and Gallery, real Advanced controls, Rocket Mode, saved checkpoints, resume and History.
- Preserve Idol's Gaussian splat and extracted mesh; optionally refine with Hi3D before native cleanup. Export a closed master and a lightweight companion in the splat's frame, plus selected SPZ/GLB/MP4/PNG files, catalog, README, checksums and upstream notices.
- Add a linked geometry comparison: rotate/zoom both meshes together, inspect triangle and shell counts, switch wireframe and reset the views. Show processing as creating the asset, with bounded overall progress through remaining stages.
- Audit the actual exported geometry for closure, winding, finite coordinates, nonmanifold topology, duplicate/zero-area faces and self-intersections before accepting a package. Closed geometry does not certify engine collision, physical printing or rigging.
- Extend Installed models across registered ComfyUI, Hi3D, TRELLIS, HairDeck and model-cache locations. Review exact-file deletion, preserve shared cache data, invalidate listings and restore missing selected resources before workflow processing.
- Give original researchers visible credit throughout the chooser and relevant workflow help; add Idol and MoGe to About and preserve component notices in exports.
- Add matching MCP tools, native-module/audit import probes and Pinokio model-location registration. Keep the archive compatible with older Pinokio updaters by placing hair installer requirements under scripts/.


## 0.1.0-preview.11 — Turnaround and 3D-Guided

### Two independent mesh methods

- Add **3D-Guided**, an Objects workflow with its own six-page wizard, saved sessions and processing branch. Keep **Turnaround**, its wizard and generation settings independent.
- Build the rough mesh from one original image. Keep the concept turnaround for appearance guidance, then render the actual working mesh in Blender to obtain four measured camera views and depth guides.
- Enhance the views together on a sheet with fixed black separators, split it into four images, and offer a checkbox for each image before reconstruction. Any nonempty subset keeps its corresponding numerical cameras.
- Feed selected views into measured-camera reconstruction, followed by Hi3D refinement, geometry cleanup and final texturing. Preserve the reconstructed, raw-refined, cleaned and textured checkpoints for comparison.

### Wizard and navigation

- Group mesh creation under a collapsible method chooser with provisional names and factual descriptions. Reduce workflow artwork to roughly one quarter of its previous area and tighten spacing; retain HairDeck and the other workflow entries.
- Include reference upload/drop, webcam entry, the existing image creator handoff, object description, special instructions, optional appearance references, generation settings and model/license notices.
- Reuse the selection editor for concept-area corrections: preview an edit, compare it with the original, then explicitly keep it. Preserve the original canvas dimensions and every pixel outside the selected mask.
- Make **Rocket Mode** unattended through remaining generation and selected exports. Manual mode retains stage reviews and view selection. Only cancellation or an actual failure stops Rocket.
- Restore saved jobs after frontend/backend recovery without silently repeating completed stages. Protect a running asset's live binding when another draft is opened, and retain pending image handoffs.
- Refresh failure/retry controls after background cleanup releases a job, so a failed export does not leave the wizard visibly locked in its busy state.
- Keep completed generation available when finishing is cancelled, and clear cancellation before resumed resource preparation.

### Exports and retained files

- Reuse the established output selector for detailed meshes, balanced/compact triangle meshes and print geometry in 3D-Guided. Keep GLB/FBX mesh exports, matching texture maps, triangle targets and print-height/STL controls.
- Hide quad retopology from the 3D-Guided wizard, its Rocket selector and output previews. Remove stale saved quad selections and disable the retained quad nodes. A single method feature flag preserves the route for future re-enabling; the server also rejects quad requests while disabled.
- Preserve Turnaround's existing output choices and published remeshing implementation. Retain the experimental quad repairs locally for later work.
- Include method identity, selected views and numerical camera records in the asset catalog and generated README. Camera records describe the Blender targets; enhanced-image adherence still requires visual review.
- Keep the generated README file inventory unique, including the new camera record, and verify its links against the ZIP catalog.
- Add an explicitly labeled private production archive for original references, concepts and edits, intermediate geometry, prompts, camera records and execution files. Keep private source files separate from the shareable asset ZIP.
- Preserve high-detail masters and completed outputs while releasing generation resources between heavy stages. Prepare the selected workflow's dependencies before generation.

### Compatibility and repairs

- Package the measured-view engine independently of the experimental repository. Use the configured Blender, isolated finishing worker and Hi3D service; no Blender MCP add-on is required.
- Pin the Union control model and include MoGe licensing/provenance. Extend software import probes without downloading model weights during installation.
- Correct the wide concept-editor encoding path, missing editor reference binding and native mesh-viewer file addressing. Report viewer load failures instead of leaving an apparently successful empty grid.
- Fix quad finishing's checkpoint variable collision so the mesh extractor remains callable. Retrying an interrupted export reuses completed generation and reduced-mesh checkpoints.
- Initially qualify 3D-Guided for solid standalone Objects. Vehicle and character presets, comparative quality rankings and lower-memory hardware remain separate work.

### Validation and limits

- Complete one fresh chest through the installed wizard, final texturing, detailed GLB/FBX, and balanced/compact GLB exports. Verify the 39-file asset ZIP, unique README inventory, notices, numerical cameras and separate private production download.
- The optional chest STL was rejected by its existing shape-preservation guard and excluded from this package. Quad retopology is disabled in 3D-Guided. Some enhanced side/rear materials vary from the front; broader categories and comparative benchmarks remain unqualified.
- Record the installed behavior, regression results and remaining limits in `docs/RELEASE-VALIDATION.md`.

## 0.1.0-preview.10

- Add **Create Rigged Hair with HairDeck**, a separately grouped workflow with its own artwork and six-page wizard. Existing image and image-to-3D workflows stay independent.
- Add sequential variations, saved matching card/chain checkpoints, rotatable review and chain-overlay previews, preprocessing diagnostics, head selection, uniform fitting, color/material/UV/texture controls, static GLB, skinned VRM 0.x and optional head-turn MP4.
- Reuse the shared queue, lifecycle, History and catalog-driven README/ZIP services. Record actual model hashes, selected settings and resource notices; preserve hair-card topology.
- Add `foundry_hair_*` MCP tools, pinned host dependencies, real upstream import probes and first-use model/export-tool acquisition. Keep Blender 4.2/VRM tools separate from the existing finishing stack. Installation does not download model weights.
- Keep HairDeck and image creation in the same compact card layout as the other secondary workflows. Restore the hair artwork, protect file drops from graph interception, and credit HairDeck explicitly in the card, wizard, progress and output records.
- No strand Groom, automatic complete-character fitting or rigged FBX is claimed by this workflow.

## 0.1.0-preview.9

- Add selected-stage overall completion in the wizard, including texture, selected game bakes, quads, print preparation, package/ZIP and final cleanup. Node sampling resets no longer reset overall completion; percentages measure completed work stages, not predicted time.
- Animate busy chaos stars with three accelerating/decelerating turns and a rest in the header, wizard and image creator. Settings offers Follow system, Spin and Pause so reduced-motion preferences can be respected or explicitly overridden.
- Separate the LoRA selector, Add LoRA and Browse buttons with compact, consistent spacing.
- Include isolated TRELLIS and Hi3D activity in model status. Distinguish loaded, CPU-offloaded and unknown residency; reject stale worker reports and remove them when workers exit.
- Refresh system meters every second with non-overlapping requests, shared bounded hardware sampling and retry backoff. Use device-wide CUDA usage so isolated-worker VRAM is included.
- Remove these five completed items from the public Roadmap. Preserve the existing geometry, texture, export defaults and model acquisition behavior.

## 0.1.0-preview.8

- Complete the running-app update repair: resolve the owned startup script explicitly and stop the verified installation runtime before acquiring the update lock. Pinokio can close its terminal while the Python runtime is still alive; other installations and active generation are protected.
- Includes preview.7's Roadmap tab, clipboard repair and startup/manual version-check improvements.

## 0.1.0-preview.7

- Added the Roadmap tab after About, organized by interface, monitoring, workflow improvements, upcoming workflows, model evaluations and integration.
- Fixed text copying and pasting inside the Foundry GUI and wizard without interfering with ComfyUI graph clipboard operations.
- Keep Pinokio's Update action visible while Foundry is running. Check for active generation before stopping, apply the published update and restart Foundry.
- Make manual version checks request fresh GitHub release information while respecting server rate limits. Startup checks use a five-minute cache and failures remain visible in Settings.
- Clarified the distinction between a source push and a published version, and how to apply updates in Pinokio or standalone ComfyUI.

## 0.1.0-preview.6

- Corrected corrupted punctuation in image-creation labels and workflow progress text.
- Reject invalid or corrupted UTF-8 source text during release packaging.
- Corrected quad triangulation conflicts and small boundary caps while preserving the detailed master and disconnected components. Close temporary mesh archives before cleanup on Windows.
- Added a Pinokio installer for the pinned ComfyUI host, TRELLIS finishing worker, Hi3D service, Blender and agent MCP environments.
- Foundry opens directly inside Pinokio, with the graph still available through View Workflow. Matching the launcher's localhost address preserves ComfyUI's cross-site protection while allowing the embedded interface to load.
- Added owned-service startup and shutdown, installation-specific loopback ports, restart recovery, verified release updates and software repair that preserves user data.
- Kept model weights as first-use downloads. Installing or opening Foundry does not download generation models.
- Added installation-specific MCP configuration and a launcher that follows the current local service address.
- Included Pinokio scripts, the approved icon and installation instructions in the portable release archive. Generated test assets and private settings remain excluded.
- Retained GUI-only presentation after embedded refresh, resolved the configured Hi3D address at runtime, and made Rocket retries continue from saved stages.
- Added bounded retries for transient Windows locks while Hi3D writes model-download status; completed model files are reused.
- Keep the same local addresses across restarts, show connection recovery in the embedded app, and retry failed page loads after reconnection without resubmitting generation.
- Fixed DINOv3 texture preparation to use the public distribution already used by the upstream TRELLIS node. The pinned files and SHA-256 checksums are unchanged; this download no longer depends on Meta's Hugging Face approval queue.
- Prepare all missing models for the selected workflow before generation begins, including back-view dependencies for image pairs. Files are downloaded to disk; stages still manage their own memory and model offloading.
- Model-access errors now link directly to the affected repository and Hugging Face settings. Retry retains verified completed mesh stages.
- Declare the texture worker's ComfyUI utility dependencies in its isolated environment and import the actual texture entry point during installation, before reporting success.

## 0.1.0-preview.5

- Added an independent image creation workflow in the existing Foundry graph, with a compact scrolling creator and section navigator.
- Generate front/back references for assets or a single general/background image using supported models, reference images and compatible installed LoRAs.
- Added paired editing and retained revisions, including ellipse and magnetic lasso selections. Preview changes before accepting them.
- Added Image Gallery, image packages and direct pair handoff to the 3D wizard. Copies protect 3D inputs from later Gallery removal.
- Extended the MCP with 14 image creation, editing, Gallery and handoff tools.
- Added image-model lineage to mesh export documentation and dedicated image ZIP documentation.
- Preserved the existing image-to-3D pipeline, export choices and model download-on-first-use policy.

## 0.1.0-preview.4

- Corrected the portable archive inventory to retain the Materials Lab HTML entry point.
