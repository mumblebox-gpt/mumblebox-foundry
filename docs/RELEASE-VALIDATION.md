# Foundry release checklist

Use this checklist for the release commit and publication. Keep verification proportional to what changed and record the actual results in the release's validation entry.

## Before the release commit

- Match the app version, installer dependency manifest, main README, every translated README in the locale manifest, and the bundled Mumblebox Assets skill and its reviewed-version record. Run the release builder's version check. Preserve the minimum compatible app version according to the skill's actual fallback support.
- Review the MCP against changed workflows, actions, settings, statuses, and artifacts. Update its capability descriptions, the bundled skill's guidance and revision, and the setup guide as needed. Exercise the changed behavior through a real MCP client before committing.
- Update user-facing documentation and strings in every supported language, using Foundry's locale manifest. Check new controls and messages in the live GUI, including larger text sizes for changed layouts.
- Update the changelog. Mark delivered roadmap items with evidence and describe any experimental behavior clearly.
- Review workflow graphs, first-use downloads, model and software requirements, installer and updater changes, and credits and license notices. When exports change, verify the generated package contents and README against the selected outputs.
- Exercise the affected workflows and real previews in ComfyUI. Verify installer and update paths affected by the release, preserve saved work, and record the scope of the checks.

## Publish and verify

- Build the release archive from the verified commit. Confirm the tag, release notes, archive integrity and checksum, and intended GitHub release assets.
- Verify the public GitHub release and Pinokio listing for that release. Where an installed Pinokio update is part of the work, use its normal updater and verify the installed version and launch. Record published verification in the release entry.

# Preview 0.1.0-preview.26 validation

Both orbit wizards were walked through all five pages in the existing Comfy Desktop Foundry in English, Simplified Chinese, Latin American Spanish, French and Brazilian Portuguese at default and 200% text size. Checks covered translated presets and help, named export choices, layout fit, the top-row Orbit to Mesh card, Connect Your Agent, the Preview release label, History’s video deletion confirmation and Settings’ model names. Keyboard Tab reached the next control with a visible focus ring. The original graph and History view were restored.

The live Orbit to Mesh wizard applied size, duration, playback and sampling presets, reset both prompts independently, blocked a run with incompatible guide timing, preserved that draft across Resume and returned to defaults. Lower VRAM applied 512 × 512 at 73 frames. Rocket Mode displayed the steps and selected formats before launch. Both wizards rendered saved meshes and orbit videos. History played a saved clip and the deletion confirmation was dismissed.

A separate export recovery run started from a copied saved reconstruction after a simulated package failure. The retry reused the verified Hi3D result, ran texturing and the selected derivative, then returned a readable ZIP from the wizard. Saved source-run files and settings were preserved.

The real stdio MCP served both orbit preset catalogs, export limits and saved results. The focused Python checks (22), Foundry JavaScript checks (34) and release fixtures (7) passed. Generation and photogrammetry behavior was verified with saved checkpoints and the targeted export retry. This pass did not rerun H3 or either native photogrammetry engine.

# Preview 0.1.0-preview.25 validation

The existing Comfy Desktop Foundry displayed Preview 25, the five language choices, the agent setup dialog and both recommended Blender repositories. The dialog loaded its hero and enabled copying the setup prompt. The Roadmap showed Connect Your Agent as available. Two saved Orbit to Mesh previews rendered. The precheck graph and History view were restored.

A real stdio MCP client exercised discovery, capabilities, saved run status, native graphs and downloadable ZIP links for Orbit to Mesh and Virtual Turntable. The earlier live workflow runs produced a textured Pixal3D asset and completed both photogrammetry engines. Those GPU stages were reused for the release check. [Localization validation](LOCALIZATION-VALIDATION.md#french-and-brazilian-portuguese--local-preview24) records the five-language checkpoint and in-place preview continuity.

The pinned ComfyUI 0.45.2 and KJNodes revisions supplied the native H3 image/video nodes and both H3 memory controls. The release inventory includes the Meshroom graph template and all three new hero images. The focused Python checks (42), JavaScript checks (34), Pinokio checks (29), launcher checks (3), and release/installer fixture checks (7) passed. The updater checks used fixtures. The orbit workflows require the licensed weights and separate camera or photogrammetry tools listed in the setup guide.

# Preview 0.1.0-preview.24 validation

The current packaged Foundry graph completed Single Image or Text geometry and Hi3D refinement in the existing Comfy Desktop. The wizard displayed the initial and cleaned mesh. Separately, starting with an empty temporary model directory, the real first-use downloader fetched and verified the pinned 661,859,924-byte MoGe 2 FP16 file without credentials, and ComfyUI's model registry listed the exact filename requested by the graph.

The model dependency audit compared the files requested by the shipping Single Image, all nine Turnaround choices, 3D-Guided, both Splat & Solid modes, and Image Creator recipes with their preparation lists. CCORE text and image, HairDeck, Garment Particles, Hi3D and TRELLIS.2 were checked at their model or worker boundaries. These checks did not run every workflow through inference.

The live Preview 24 About page displayed the new credit alongside Hal Rottenberg's and linked to the original report. The release retains the three interface languages. Foundry (169 tests), Pinokio (29 tests), release packaging (7 tests) and the localization checks passed. Pinokio compatibility was checked with updater fixtures.

# Preview 0.1.0-preview.23 validation

Latin American Spanish was verified in 15 views at default and 200% text size in the existing Comfy Desktop. Language switching preserved an edited form and a rendered preview. [Spanish validation](LOCALIZATION-VALIDATION.md#latin-american-spanish-checkpoint) records the catalog, package and live checks.

# Preview 0.1.0-preview.22 validation

English/Simplified Chinese localization, bilingual CCORE presets and the local literal-translation action were verified in the existing Comfy Desktop. [Localization validation](LOCALIZATION-VALIDATION.md) records the actual GUI, preview preservation, 200% font, translation fidelity, GPU memory and cancellation checks, with their limits.

# Preview 0.1.0-preview.18 validation

The installed standalone ComfyUI Desktop workflow loaded all 12 example descriptions and cleared the editor with Custom. Two real local Qwen enhancements exercised creative elaboration and preservation of strict requirements. Restore recovered the original draft and Stop preserved the current draft. The CCORE generator received the edited description verbatim.

The edited supply-crate brief generated a 3,224-triangle GLB and a saved History entry. The actual GLB rendered in the native Foundry viewer. Two other attempts returned invalid generated JavaScript, which Foundry rejected at export. Retrying with a simpler description produced the crate.

The software archive includes the pinned CCORE runtime resources, workflow artwork, and Chromium installer probe. Installer and updater checks use temporary fixtures. The GUI evidence is from the existing standalone Desktop installation.

# Preview 0.1.0-preview.17 validation

The canonical-source update was exercised in the existing standalone Comfy Desktop development installation on Windows / RTX 4080 SUPER 16 GB / 64 GB RAM. Single Image or Text completed geometry, Hi3D refinement, cleanup, 4K texturing, compact baking, optional quad export and package creation with real visible previews. Image creation/direct handoff, Gallery selection, reload/Resume, method artwork, Font scaling, cache review and the other saved wizards were checked proportionally. [Local update evidence](LOCAL-UPDATE-VALIDATION.md) describes the exact checks and limits.

The subsequent grounding repair reused the saved outputs and reran packaging only. Detailed, compact and quad runtime GLBs touch the floor at Y=0; the actual editable quad BLEND reopened in Blender at Z=0. The measured frame is rigid, with unchanged topology and embedded image bytes. [Grounding evidence](GROUNDING-VALIDATION.md) records measurements, tests, coordinate conversion and the remaining uneven-foot limit.

The public graph adds an independent 71-node Single Image section. Existing method nodes and saved assets are retained. The release inventory now includes WebP method artwork and checks its inclusion. Geometry requirements and the real stable-pose import are declared/probed for normal future installations.

**The installed Pinokio copy was not updated or directly modified.** Pinokio unit checks used temporary fixtures; these do not constitute a new installed-Pinokio workflow test. The existing update path can offer the newly published preview. A fresh-machine installation, every asset category, physical webcam capture and all export/settings combinations were not retested. The validation is for the exercised local path, not a universal quality guarantee.

Verification passed: 41 targeted Foundry tests, 4 grounding tests, 2 closed-quad tests, 7 installer/release-inventory tests and 29 Pinokio tests using temporary fixtures. The previous full-app pass also parsed all 51 Foundry JavaScript modules.

Earlier release records follow unchanged.

# Preview 0.1.0-preview.16 validation

The actual Pinokio Update control in the stopped preview.14 installation failed its idle check because the saved backend address refused connection. The stale runtime process had exited. This is a reproduced updater failure, not an asset-generation or preview failure. The correction is made only in canonical development source: require both connection refusal and a confirmed exited saved runtime before accepting the stopped state. Live-process, timeout and active/queued-work protections remain.

Three focused regression cases cover exited/live runtime refusal and timeout; all 29 Pinokio tests passed. The repaired source also accepted the actual exited runtime with refused connection. To let preview.14 acquire its replacement, the usual Start Foundry action restored its backend, then the actual Update/Run controls and native confirmation installed preview.16. The updater receipt records previous commit `03e123d` and installed tag `v0.1.0-preview.16`; the clean installed checkout is `fa9a745`. No installed source or environment was patched directly.

Post-publication GUI acceptance used a different newly generated indigo hairstyle in the existing Pinokio window. The actual wizard input uploaded it, generated two variations (110/133 cards), selected the second and displayed head/chain toggles, enlarged processing and UV sheets, a pointer-orbitable model and all material maps. Fitting, swatch-to-hex synchronization, a custom-color shared-atlas ribbon preview, reference-color restoration and a 2K volumetric preview passed. Avatar validation retained four spring groups, and the three-second 480px motion preview played in the wizard. Selected static GLB, rigged VRM, MP4 and supporting exports completed. History displayed the new thumbnail/formats/details; Resume restored the same final model. About displayed the community guidance and Hal's specific Thank You acknowledgment after model cards. The completed result is left open and saved. The native ZIP save check was waived by Brian and was not repeated.

Both software archives were built from their exact Git archives and all 323 packaged file hashes matched their tag sources. GitHub's preview.16 asset digest matches `0f1995cfc570dd15ead238af12e970c2d005d6b7dc436c6215ce8692eae5cbd6`. These checks qualify the exercised paths on this machine; they are not a fresh-machine installation or every-hairstyle/Advanced-combination guarantee. Preview.15 community/installer and native HairDeck evidence follows.

# Preview 0.1.0-preview.15 validation

Community About/Thank You changes were visually inspected in the existing standalone Comfy Desktop Foundry. Contributor credit is specific to Hal Rottenberg's installer improvements, with both original source commits linked. The Pinokio description and contribution guide invite workflow suggestions and pull requests.

Installer verification: Python 3.13.12 reproduced the inherited `SETUPTOOLS_USE_DISTUTILS=stdlib` import failure; `local` succeeds. A fresh, SHA-256-verified iopath 0.1.10 source archive was downloaded through the actual repaired transport and built into a wheel with uv in an isolated cache/build environment. No user environment was changed. The bundled-distutils override remains scoped to HairDeck's dependency-build subprocess, retaining current requirements, Torch constraints and both real-entrypoint probes.

Bounded Blender primary/mirror requests each returned HTTP206, ZIP signatures and a 404,453,484-byte total; the mirror redirected to Purdue. The primary worked here, so the fork's earlier HTTP403 was not reproduced. Blender's pinned version/hash and mandatory full-download checksum check remain unchanged; this is not a fresh full Blender transfer or fresh-machine installation claim.

Focused regression checks passed: 26 Pinokio/bootstrap/update tests, one HairDeck installer test, three HairDeck probe tests and seven portable release/installer tests; both changed JavaScript files parsed, and the source whitespace check passed. Native GUI acceptance: a new auburn-haired reference produced two saved variations. The first checkpoint and data hashes remained unchanged when adding the second. The saved second variation gained spring chains without regenerating its hairstyle, then displayed 146 cards and 11 validated spring groups. Actual review/head/chain controls, enlarged sheets, pointer-driven orbit, scale/Z fitting, swatch/hex color override, ribbon/volume material previews, unique UV maps, reference-color restoration, avatar review and three-second 480px motion playback passed. The final 29-file package passed CRC, all 28 non-self catalog checksums and README inventory checks. History displayed its thumbnail/formats; the actual Resume control restored the same completed run and final preview. The original graph remains selected and saved.

Brian explicitly waived the native ZIP Save As/download-completion check on 2026-11-08 to proceed with release work. The package integrity checks above remain valid; successful native Save As is not claimed. Pinokio update/retest and publication follow the native acceptance pass.

# Preview 0.1.0-preview.14 validation

Validated in the existing standalone Comfy Desktop wizard on 2026-11-08. HairDeck remains an independently owned six-node branch; opening older graphs adds only the missing HairDeck section and preserves their existing nodes, groups, settings and output references.

- Generated two actual colored variations with 50 steps and CFG 2: 126 and 82 hair cards. Both interactive variation cards, processing sheets, crop, hair/face masks and multi-view results rendered in the wizard. Dragging the viewer changed its camera; Reset view restored it.
- Selected the second variation and added 12 predicted chains without changing its saved card curves, latent tokens or predicted colors. Head/chain view choices loaded their corresponding geometry.
- Applied scale/translation, a custom color, transparent cards and a unique 1K material atlas. All seven material/UV maps rendered. The simple swatch, optional hex field and reference-color choice remained synchronized without regenerating hair.
- Avatar review validated 12 retained chains and 12 spring groups. The actual player decoded and played HairDeck's three-second, 480px head-turn video with a chain overlay. This is a motion demonstration, not an exported animation clip or supplied 360-degree turntable video.
- The finished model was visually checked at normal and compact widths. The compact final page has one footer and keeps the complete viewer in its content viewport. History showed the saved thumbnail/package and resume restored the selected variation and completed media.
- The selected 29-file GLB/VRM/MP4 package passed ZIP CRC, source-color retention, accurate README/provenance and resource credits. SHA-256: `e11ed0f6ee7643f55872b20b14bc57faff82e19868289344c9d00f73ec1814ec`. This local test asset is not distributed with the software. Download endpoints and archive contents were checked; native Save As completion is not claimed.
- Targeted checks passed: 13 HairDeck Python checks, seven JavaScript checks, seven release/installer checks, seven bootstrap checks and three entrypoint-probe checks. The release inventory now explicitly includes the new color probe. The real ColorDiT entrypoint and CIELAB conversion imported in the Comfy host without loading weights or allocating a model.

Official ColorDiT weights use a pinned public revision, exact size and SHA-256. Installation only prepares software; selected first use acquires the missing model files. Official HairDeck and the community ComfyUI integration retain attribution and separate license terms. Model viewers are view-only; supported fitting/material controls and editable source files do not imply a card-sculpting editor. Physical camera capture, arbitrary custom checkpoints and every head/material combination are not quality-qualified.

Published-update and installed Pinokio verification are recorded after applying the release through its normal Update control. Pre-publication direct-copy diagnostics are not used as proof of that process.

# Preview 0.1.0-preview.13 validation

- Reproduced the reported missing `termcolor` failure in the actual Pinokio host. A real retry also exposed missing `six` and `imageio` in the lazy review renderer. All three now belong to the canonical HairDeck host requirements; the installer probes both lazy execution paths with no weight downloads or GPU model allocation.
- Reused the original failed reference and default generation settings in Pinokio. HairDeck generated 83 hair cards and nine predicted chains, then exported static GLB, a skinned VRM with nine spring groups, and a 28-file ZIP. The separate Comfy Desktop wizard also completed the selected GLB/VRM/package export using its saved generation.
- Diagnosed the blank native previews independently: older HairDeck and Turnaround callers did not supply the filename required by the current native loader. Verified the rendered hair in both actual app windows and the rendered saved Turnaround alien in Comfy Desktop. A CDP orbit drag changed the Turnaround preview image. Asset creation, HTTP success and canvas existence were not used as substitutes for visual review.
- Verified HairDeck's real Next controls through review, materials and exports, and that navigation unlocks after export cleanup. Targeted regression checks cover missing lazy imports, existing preview URL forms and the delayed active-to-idle transition. Saved source images, weights, settings and previous outputs are retained.

## Preview.12 validation

Validated on 2026-11-07 in the existing ComfyUI Desktop instance, on the reference RTX 4080 SUPER / 16 GB VRAM / 64 GB RAM system. The standalone experiment remains preserved. This is an integrated workflow test and existing-install update qualification, not a fresh-machine or universal hardware claim.

- Drove the real Splat & Solid chooser, upload control and Rocket confirmation. The independent branch generated the approved lander with Idol, extracted the original mesh, ran optional Hi3D refinement, cleaned and simplified geometry, audited exported files and created a selected package and History record.
- The canonical master has 550,008 vertices and 1,099,812 triangles in 101 closed components. The companion has 11,064 vertices and 22,128 triangles in one closed component. Both pass closure, winding, positive aggregate volume, finite coordinates, boundary/nonmanifold edges and vertices, duplicate/zero-area faces and PyMeshLab self-intersection checks. These checks do not establish collision behavior in a particular engine or physical printability.
- The actual wizard displays the SPZ splat and extracted GLB. Visual review found and repaired native-viewer URL rewriting and Spark first-paint readiness. The paired inspector displays master and companion, with linked rotation/zoom, wireframe, reset, triangle counts and recorded checks. Real controls were clicked and dragged. The comparison shows 98.0% fewer companion triangles.
- Navigated all six pages, inspected both Advanced sections, renamed the saved asset and used the actual Save selected package control. Reopening and saved-stage generation reuse retained the original prompt identities; no further Idol or Hi3D inference was needed. Finished-state controls unlock after memory cleanup.
- The final 22-file asset ZIP passed CRC, all catalog hashes, unique README inventory and file-bound geometry audit hashes. It includes 11 notice/model-card files, exact native model revisions/hashes and only selected asset outputs. Package SHA-256: `fb0e1e54eaab8c07f11d949a83a04958a5a7370a40320ae611d45a8a72751217`. It is a local test artifact, not bundled with the application release.
- Settings enumerated registered native, HairDeck, Hi3D, TRELLIS and model-cache stores. Deleted one 44-byte disposable fixture through the actual exact-file confirmation and verified its absence. No existing user weights were deleted. A filesystem/download fixture proves a deleted selected model is restored despite a previous verification receipt. Hi3D's own readiness checks compare the live file snapshot before reporting ready; HairDeck's installer and texture readiness also check missing files before processing.
- The real installed MCP stdio/HTTP check discovered 36 tools, including all six Splat & Solid tools. Capability/status/show worked; an invalid operation was rejected without inference. Native generation and complete combined API graphs passed installed validation.
- Automated checks passed: 291 asset-workshop Python tests, 119 Foundry Python tests, 19 Foundry JavaScript checks, seven release/installer checks, 23 Pinokio Python checks and three launcher checks. Archive compatibility is checked against the existing updater's original root-file policy; hair requirements now live under scripts/.
- The public graph adds 53 independent native/note nodes while retaining the existing workflow branches. No test images, outputs, history, credentials or developer paths are included. Native ComfyUI model requirements and the isolated geometry audit entry point have explicit installer probes.

Physical camera capture, every Advanced combination, fresh-machine installation, lower-memory systems, engine collision import and physical printing are not qualified by this run. Earlier workflow evidence remains below.

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
