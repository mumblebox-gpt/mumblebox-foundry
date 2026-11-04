# Preview 0.1.0-preview.11 validation

Validated on 2026-11-04 in the usual ComfyUI Desktop installation, using an RTX 4080 SUPER with 16 GB VRAM and approximately 64 GB system RAM. Turnaround and 3D-Guided have independent wizards and processing branches. This is an Objects-method release, not a comparative quality benchmark or a fresh-machine installation claim.

- One fresh chest was driven through the actual installed wizard: original image, concept generation, selected-area concept edit, single-image proxy, automatic working-proxy preparation, measured Blender views, joint depth-guided enhancement, view selection, reconstruction, Hi3D refinement, cleanup and final texturing. Manual review and Rocket continuation were exercised; saved checkpoints survived frontend reloads and normal Desktop restarts.
- The concept edit retained its 4096×1024 canvas and original source. All pixels outside the selected mask matched exactly; 34,500 selected pixels changed. The real preview and Keep control accepted that edit before generation continued.
- All four view checkboxes were exercised. Front, back and left were selected; right was excluded, and Front was restored as the finishing reference. The submitted reconstruction used exactly those three prepared images and their matching numerical cameras.
- Camera targets were azimuths 0/90/180/270 degrees, elevation 10 degrees and horizontal FOV 20 degrees, with 1024-pixel panels and black separators. Enhanced-image camera records explicitly inherit these targets with adherence unverified. Numerical records do not establish that an image model preserved calibration perfectly.
- The cleaned master had 2,918,036 triangles and 1,459,274 render vertices, with zero boundary edges, nonmanifold edges and degenerate faces in its authoritative connectivity audit. It was watertight and winding-consistent. Self-intersections, wall thickness and physical printability were not established by that audit.
- The actual wizard displayed the byte-identical textured master and the 250,000-triangle Balanced and 100,000-triangle Compact derivatives. The retained source geometry was used for the 4096-pixel material bakes. No display-only corrected mesh was substituted.
- 3D-Guided quad choices, quad targets, Rocket choices and quad previews are disabled for this release. Its existing native quad node remains retained, disabled and excluded from processing. A stale saved selection was normalized, and a direct quad export request returned HTTP400 with an empty queue. Turnaround's separate output choices and published remeshing implementation are preserved.
- The optional STL attempt was rejected by the existing shape-preservation guard: contact repair exceeded the sampled 1%-of-height deviation limit. Print was deselected for this chest; its final package contains Detailed GLB/FBX plus Balanced and Compact GLB. No successful STL or physical printability claim is made for this case.
- The real Cancel and Retry controls were exercised. Cancelling finishing preserved completed generation; the Retry control unlocked after cleanup and resumed the same export run. The detailed preview remained available after recovery.
- Regression checks passed: 290 asset-workshop Python tests, 109 Foundry service tests, seven focused JavaScript checks and seven portable release/installer tests. The Pinokio checks also passed (22 Python tests and three launcher checks). The legacy Playwright fixture could not start because Playwright is absent from this repository's Node resolution; required installed proof used the guarded Desktop integration instead.

The completed 39-file shareable ZIP passed CRC, every catalog file checksum, unique README inventory, resource notices, selected-view and numerical-camera checks. Its SHA-256 is `b91f13bbe9d9b1a937a5504948777ce4f0553fbcfe1e30ea2c1f9b68f9c6a105`. The separate private production ZIP contained 112 files; all 58 original/intermediate artifact hashes matched. Both HTTP download endpoints were checked; native Save As dialogs were not exercised.

The actual Create an image entry opened the existing image creator. An accepted saved pair returned through the method chooser into a new 3D-Guided draft with its primary image and creation provenance; no new image or mesh generation was needed. The completed chest, original creator state and latest result were restored afterward. Its final wizard displayed no quad choices, targets, previews or quad statistics; the retained quad node remained disabled.

Remaining limits: some enhanced side/rear bands differ in material from the front. Vehicle and character presets, exhaustive format combinations, physical webcam capture, Unreal import and animation are not qualified by this run. Earlier published-release evidence follows below and does not substitute for the new method's proof.

# Preview 0.1.0-preview.10 validation

Validated on 2026-11-02. HairDeck adds a separate five-node workflow in two colored groups, its own six-page wizard, saved variations, fitting/material controls, static GLB, spring-bone VRM and optional motion MP4. Existing generation workflows retain their owners. [HairDeck implementation and limits](HAIR-WORKFLOW.md) records the pinned dependencies, runtime, public model acquisition and output evidence.

- The actual installed wizard generated two variations from the licensed upstream example, reused the second generation for fitting/material changes, and produced a checked 29-file ZIP with GLB, VRM, a three-second motion video, textures, diagnostics, editable source data, provenance, licenses and README. VRM validation recorded 22 spring groups and 23 retained chains. The GUI download matched the recorded SHA-256; the archive's hashes and README inventory passed validation.
- Seven focused hair tests cover bounded controls, graph/variation identity, source integrity, cancellation/retry, export-only reuse and selected archive contents. Real installed MCP stdio-to-HTTP checks discovered 30 tools, including seven hair tools. The actual native HairDeck entry points imported successfully.
- Release checks passed: 107 Foundry unit tests, seven portable-release/installer tests and 22 Pinokio tests. These are contract and runtime checks, not a fresh-machine install or qualification of every hairstyle.
- First-use acquisition used public sources without a token and matched the pinned checksums, including an independent 1.2 GB DINOv3 transfer. Software installation does not download model weights. Hair export's Blender 4.2/VRM tools remain separate from the mesh-finishing Blender installation.
- After review, all secondary workflow cards measured 180px high with 150×180 images; the hair artwork decoded and displayed. File drag-and-drop uploaded into the hair wizard without changing the selected graph. The Gallery picker loaded saved images. HairDeck is named on the card, wizard, progress and output records.
- Existing Desktop workflow and saved results were restored across a reboot and a controlled idle restart. No active generation was interrupted. Physical camera capture remains untested without attached hardware. No arbitrary-avatar fitting, strand Groom or rigged FBX is claimed.

---

# Preview 0.1.0-preview.9 validation

Validated on 2026-11-02 in the existing Comfy Desktop workflow. This pass changes feedback and monitoring, not generation settings, geometry, textures or export contents.

- The installed interface reports preview.9. Both header and wizard stars have running 4.8-second animations when Spin is selected. The actual Settings select was changed to Pause and back to Spin; the stored preference changed correctly. System motion remains the default for other users.
- Opened the real image creator and LoRA disclosure. Selector/Add and Browse controls have separate measured gaps; existing drafts and LoRA selections were preserved.
- A rendered stage-panel fixture verified selected-stage count, an overall percentage, and monotonic progress after a node counter resets. Contract tests cover print-only selection, all optional outputs, legacy records, recovery and cleanup failures. No full asset was regenerated for this feedback pass.
- The real isolated-worker bridge was exercised with a tiny local PyTorch module moving between CPU and CUDA, without downloaded weights. It reported offloaded and loaded states, then removed the worker on exit. Tests reject stale/wrong-process reports and cover Windows venv interpreter children. Hi3D reporting uses the service's post-load events and labels its CPU-offload policy; it does not claim per-layer instantaneous device measurements from that service.
- The live system endpoint produced distinct samples approximately one second apart, with changing CPU and RAM readings. Polling tests cover non-overlap, offline backoff and disposal. Hardware sampling is shared for half a second across clients and reads device-wide CUDA usage.
- The five completed items are removed from the public Roadmap and recorded in CHANGELOG.md. The agent run-status response includes the same selected-stage progress object used by the wizard.

## Retained preview.8 validation

Preview.8 corrects the owned-process shutdown found during the actual Pinokio update run. The installed preview.6 detected the preview.7 GitHub release; the repaired updater then downloaded and checksum-verified that archive and ran the installed maintenance path. Tests additionally cover rejecting unrelated PIDs and waiting for this installation's runtime to exit. This is update-path validation, not another generation-quality test.

Preview.7 adds the categorized Roadmap tab, repairs text clipboard handling and keeps Pinokio Update accessible while running. Targeted checks cover clipboard ownership/native editing, running-menu visibility, the idle guard, update stop/install/restart ordering and fresh manual release checks. The source and installed ComfyUI clipboard path were exercised with Ctrl+C/Ctrl+V. No new asset generation or category-quality qualification is claimed for this release. Earlier pipeline evidence below remains from prior previews.

Validated on 2026-11-02 on Windows/NVIDIA. This release adds the Pinokio installer and embedded Foundry interface, and repairs first-use model preparation and isolated texture-worker dependencies. The checks below distinguish actual generation from automated contract checks.

## Model acquisition and installation

- Downloaded all three required DINOv3 files without authentication from the public distribution already used by the pinned upstream TRELLIS wrapper. Their SHA-256 hashes matched the existing model manifest, including the 1,212,559,808-byte weights. The model and its license are unchanged; this acquisition path does not require the original repository's approval queue.
- The complete selected-workflow resource set is prepared before generation, including downstream texture resources and back-view resources for image pairs. Print-only selection does not acquire unnecessary texture models. Files are prepared on disk; model loading/offloading remains stage-specific.
- The installed texture-worker entry-point probe passed in both the native ComfyUI configuration and Pinokio's isolated worker environment. Its ComfyUI utility imports are now declared worker dependencies instead of relying on the host environment.
- Focused automated checks passed: seven workflow/Rocket checks, ten readiness checks, seven bootstrap checks, six release/installer checks and two quad-diagonal checks. Release packaging rejects invalid UTF-8 and known corrupted-punctuation sequences.

## Saved asset and geometry

The Pinokio Ranger test used saved checkpoints to resume the failed workflow rather than regenerate successful stages. Turnaround, initial mesh, Hi3D, cleanup, texture, compact export preparation and optional quad preparation completed in the managed installation.

- Hi3D used CUDA: recorded allocated/reserved GPU memory was 8,565/9,232 MB. The texture worker recorded 3.503/3.691 GB allocated/reserved.
- The cleaned master had 359,200 vertices and 718,356 triangles. It had zero boundary edges, non-manifold edges and degenerate faces, with consistent winding and a watertight result.
- Texturing retained 718,356 triangles; UV seams increased the vertex count to 422,768. The measured maximum positional difference was approximately 1.64e-8.
- The compact version reached 100,000 triangles and passed the same boundary, non-manifold, degenerate-face, winding and watertight checks.
- The optional authoring version contained 24,399 quads and eight small triangular caps, with no n-gons. Its triangulated export had 48,806 triangles and was watertight. All 17 disconnected components were retained. A deterministic 10,000-point comparison measured mean/p95 surface deviation of 0.000156/0.000538 of the source bounding-box diagonal; this does not establish animation-ready edge flow.
- Quad corrections preserve the detailed master. They resolve triangulation conflicts and bounded small boundary loops; they do not merge all components or globally weld the source. Temporary NumPy mesh archives are closed before Windows scratch cleanup.

The saved test asset's final packaging retry and archive review were deferred by user instruction; they are not claimed as preview.6 validation. These measurements describe this asset, not a guarantee for arbitrary generated subjects. Category generation and physical webcam checks remain user testing.

## Release boundary

The portable package includes the launcher, app entry point, dependency manifest and update/repair paths. Model weights, generated test assets, credentials and private runtime records are excluded. Models download on workflow first use, not when installing or opening Foundry. A Windows/NVIDIA managed-install run is not a claim of Linux/macOS or 8 GB compatibility.

---

# Retained preview.5 evidence

Validated on 2026-11-01. This release adds the independent image creator, paired editing, Image Gallery and image-to-3D handoff. The existing four-view mesh, refinement, cleanup and export stages retain their owners and settings. Test images and private runtime records are not distributed.

## Real generation and installed controls

Checks operated the actual Foundry interface in the existing Alt-Tab-accessible Comfy Desktop window through its supported integration, without moving or focusing the operating-system window.

| Path | Observed result |
|---|---|
| Front/back creation | FLUX.2 Klein 4B generated a clockwork courier front and an image-conditioned back at 512 pixels, four steps, CFG 1, seeds 42/43. Both previews loaded. |
| Selected-area edit | A vest color edit completed through the installed editor. Comparison against the actual source-resolution selection found 19,500 changed pixels inside and **zero outside**. Accepting the edit retained the original and left the rear revision unchanged. |
| Single image and LoRA | General Image generated a 512-pixel paper observatory using the installed Paper Diorama Klein 4B LoRA. The result and resource hash/source appeared in its record. General Image offered no 3D handoff. |
| Gallery | Saving produced one grouped pair entry and one single-image entry with loaded thumbnails. Saved files and entry removal have separate confirmation controls. |
| 3D handoff | Save & Create a 3D Mesh opened page 1 with accepted front/back copies, roles, descriptions and a server-validated provenance receipt. No additional mesh generation was required. |
| Reload recovery | A restored Comfy property proxy initially broke creator initialization. The installed repair restored the saved draft and both previews after reload. |
| Separate graph | The creator materialized its own colored node group on the same graph. The existing 94-node 3D workflow and its completed alien output records were preserved. |

These are representative checks, not qualification of every model, LoRA or category. The accepted edit can make the two views inconsistent; the UI asks users to review both. Physical webcam capture remains deferred because no camera is connected.

## Automated and protocol checks

- Foundry Python suite: **83 passed**, including 20 image-creation tests. Coverage includes input contracts, pair preservation/recovery, revisions, selection compositing, package privacy, bounded Gallery queries, deletion ownership and handoff validation, alongside the existing 3D contracts.
- Portable installer: **5 passed**. Reinstallation preserves settings/models, backs up changed files and rejects unsafe runtime configuration before writes.
- Existing JavaScript wizard-session regression passed. Changed image UI modules passed syntax checks.
- Real MCP stdio against installed services discovered **23 tools**. Image capabilities, create/update/status, idle cancellation, save, Gallery, handoff and invalid operation rejection passed. Existing 3D status/package/create/update/cancel operations also passed. This protocol check did not start a GPU run.

## Output documentation

The actual accepted pair ZIP contained `Images/front.png`, `Images/back.png`, `README.md` and `Metadata/creation.json`. The single-image ZIP contained `Images/single.png` and the same two documentation files. ZIP integrity and member checksums passed. README dimensions, roles, model terms and the single image's LoRA source matched the records. Embedded private recipe metadata was excluded.

The mesh README renderer was exercised with originating-image provenance and produced its model/license section. The handoff's copied input hashes and provenance were verified independently. This is not a claim that a fresh complete image-to-mesh generation/export was run during preview.5; the existing mesh run and export contract tests were retained.

## Release boundary

The explicit archive inventory includes the new image backend, editor/Gallery assets, MCP adapter and documentation. It excludes generated assets, model weights, credentials, local runtime records and obsolete logo drafts. The public workflow has empty user inputs and no saved outputs. The independent image graph is populated when image creation runs.

The release uses the existing portable installer and dependency setup. Relocation/package checks are not a fresh-machine installation test. Windows/NVIDIA is the tested platform: RTX 4080 SUPER, 16 GB VRAM and 64 GB system RAM. Additional memory profiles do not establish 8 GB compatibility.

Optional quads do not imply automatic rigging or animation-ready deformation. Strand Groom/Alembic, deferred workflow cards and Pinokio packaging remain future work. Third-party licenses remain separate from Foundry's Apache-2.0 license. GitHub records the release commit and attached archive digest; the archive also contains per-file `SHA256SUMS.json`.

---

# Retained preview.4 evidence

Validated on 2026-11-01. Preview.4 corrects an archive inventory omission of the retained Materials Lab HTML entry point; the main wizard and mesh pipeline are unchanged. A regression check now requires that entry point in the archive. Public preview.3 was downloaded without authentication, its digest matched, and the installed update control successfully read its GitHub release. Evidence below separates installed control actions, automated tests and exported-asset checks. Generated test assets and local diagnostic receipts are not distributed.

## Installed interface checks

The existing Comfy Desktop window remained available through Alt-Tab. Checks used its supported integration without bringing the operating-system window forward. The main graph retained 94 nodes, 20 groups, 137 links and 31 output records.

| Area | Observed result |
|---|---|
| Main shell and wizard | Compact grouped navigation, requested removals, combined reference intake and model/licensing section afterward. All five wizard pages inspected. |
| New versus resumed work | Open Wizard opened an empty page 1; Resume previous asset restored the saved asset. No generation was started by either action. |
| Themes and artwork | Real theme controls switched light/dark presentation. The approved shared logo and six workflow illustrations loaded. |
| Settings | Automatic update preference saved off/on and persisted through bootstrap reads. Check for updates reported a real GitHub availability/rate-limit failure before publication instead of claiming success. |
| Resource deletion | An exclusive 50-byte test file appeared in the LoRA list. Cancel preserved it; confirmed deletion removed only that file. Shared-resource Delete controls were disabled. No user model was deleted. |
| Civitai | Family changes requested new results automatically. NSFW filtering sent true/false. API-key help opened the correct Settings field. Download selected Pixel Art XL and verified an existing 162.6 MB file, without another weight download. |
| History | The saved asset displayed its generated front image. The public package-import panel was absent. |
| Rocket confirmation | Opened from the wizard, selected versions/formats, rejected an empty selection, and cancelled without altering saved choices. The same selector serves normal exports. |
| Review workspace | Mesh preview appears beside export choices. Settings and Rocket dialogs fit within the available embedded viewport in both themes. |

The latest checks did not submit a new full GPU generation or execute a real mid-generation cancellation. Rocket orchestration, retry and failure paths have the automated coverage described below; those checks are not presented as manual end-to-end generation proof.

## Automated tests

- Foundry Python suite: **63 passed**. Coverage includes run contracts/recovery, Rocket branch selection and retry idempotency, cancellation/error checkpoint preservation, library paths, resource ownership, MCP boundaries, first-use readiness, missing-only downloads and update checks.
- Release installer: **5 passed**. Installation/reinstallation preserves settings and model sentinels; changed files are backed up; remote Hi3D URLs and OneDrive runtime paths are rejected before installation writes.
- JavaScript activity/viewer/session suite: **6 passed**. Includes activity states, drag-only viewer input and fresh-versus-resumed wizard state and missing-field defaults for older agent-opened runs.
- Ten installed texture snapshot files matched the pinned manifest; verification required **zero model downloads**.
- Original source diff whitespace checks passed; retained upstream license/vendor text was not reformatted.

## MCP runtime

The distributed Foundry MCP ran through the real stdio protocol against installed Foundry HTTP services. Nine tools were discovered. Capabilities, saved-run status/package access, create/update, idle cancellation and invalid-start rejection passed. Test configuration did not start generation. Input restrictions and other adapter contracts have separate automated coverage. The real display action exposed a legacy run missing its turnaround-model field; session restoration now retains the original Qwen default when that field is absent and copies inputs independently. The fix has a regression test and is verified in the installed interface.

## Portable install and export proof

The allowlisted release was installed into a separate local directory and imported using the existing ComfyUI host dependencies without starting a second server. **44 node classes and 141 routes** registered. Python compilation passed. This checks relocation and package completeness; it is not a fresh-machine installation test.

From that relocated package, the exporter used preserved local assets to create only these requested outputs:

- Compact game mesh: GLB and FBX.
- Light quad authoring mesh: OBJ and FBX, with required material companions.

The resulting archive contained 22 files. All four mesh files were re-imported in Blender 5.2.2 LTS; polygon counts, UV layers, bounds and packaged texture paths passed. The root README matched the selected directories, files, measurements and recorded limitations. Source asset hashes were unchanged; ZIP integrity passed.

This direct exporter test intentionally supplied no upstream generation metadata, and the README reported that absence. It is not evidence for complete generation-model provenance by itself; the saved full workflow package and provenance contract checks cover that separate path.

The sanitized public graph has empty inputs and no saved output previews or wizard session. Its 94 nodes, 20 groups and 137 links preserve the working pipeline. Source/archive checks exclude credentials, weights, generated test assets, personal installation paths and local runtime state.

## Preserved pipeline and limits

The retained local reference run completed turnaround, native four-view geometry, Hi3D refinement, cleanup, final mesh texturing and multiple exports. This release preserves those results and stage owners. It does not claim that every future subject will be watertight or that arbitrary topology is animation-ready.

- Windows/NVIDIA preview with manual dependency setup; reference system RTX 4080 SUPER, 16 GB VRAM, 64 GB RAM.
- Alternate model/category generation quality tests remain user testing. Physical webcam capture is deferred because no camera is connected.
- Additional memory profiles are placeholders. No 8 GB compatibility claim.
- Quad retopology is optional; no automatic rigging/deformation qualification.
- FBX material interpretation and Unreal import require destination-specific review. Physical printing is not tested.
- Strand Groom/Alembic, deferred workflow cards and Pinokio packaging remain future work.
- Model licenses remain separate from the original code's Apache-2.0 license.

Public release URLs, commit and final archive digest are recorded by GitHub's release and its attached checksum file. The archive also contains SHA256SUMS.json for individual files.
