# Local Foundry update validation — 2026-11-08

This is a **local, uncommitted and unpublished** update. Work used canonical `C:\Dev\mumblebox-foundry` and Brian’s existing native Comfy Desktop development installation. The installed Pinokio copy was not edited or updated. No Git commit, push, tag or release was made.

## Delivered behavior

- **Single Image or Text** is first/recommended in the chooser. Its independent four-page wizard and 70-node graph section use the pinned official ComfyUI single-image Pixal3D recipe, original-reference Hi3D refinement, cleanup, final TRELLIS.2 texturing/baking and selected exports. The other methods remain independent.
- Inputs include upload/drop, Gallery, the existing webcam capture and Create Image. Single-context creation produces one image and returns one accepted reference with provenance; the normal paired creator session is retained.
- Four matching method illustrations; compact spacing/copy, consistent icons and navigation, preview room, contextual help and expandable technical failures.
- Persistent glasses-icon **Font** menu: Default, 112%, 125%, 150%, 175%, 200%. Light/dark styling and responsive layouts remain available.
- Header release flag: current/available/checking/unavailable states, release details, busy guard. It checks published releases and provides the supported update route; it does not apply unpublished changes or automatically install into native ComfyUI.
- **Purge Cache**, the additional usability improvement, previews scoped temporary files and sizes, supports selected categories and explicit confirmation, and refuses active processing. Models, saved references/assets/settings and durable editable quad data are excluded.
- QuadriFlow is optional/off by default. CPU use/spikes and duration are explained. A reported topology-preserving fallback handles invalid QuadriFlow openings without weakening the existing small-hole gate.
- Friendly product README, local changelog/roadmap, recipe provenance, package documentation and MCP method guidance updated.

## Actual GUI and output evidence

The existing Comfy Desktop instance and `Mumblebox - Foundry GUI Review.json` remained the working app. The local window guard verified the selected graph and healthy Desktop host. The app was allowed to remain minimized; no routine foreground takeover was needed.

The cargo-lander Single Image run `e5fcf4645eca454789a0d0822af52ae5` completed geometry, Hi3D1536/25 refinement, cleanup, 4K texture, compact baking, optional quad baking/export and package creation. Actual results:

| Output | Measured result |
| --- | --- |
| Clean master | 1,893,032 triangles; 0 boundary/nonmanifold edges; watertight and consistently wound |
| Compact mesh | 100,000 triangles; fresh UVs and 4K baked textures |
| Editable quad mesh | 24,996 quads; 0 boundary/nonmanifold edges; watertight |
| Quad runtime GLB | 49,992 triangles with baked textures |
| Package | 36 selected files: detailed GLB, compact GLB, editable BLEND, runtime GLB, textures, README, catalog and notices |

Initial, clean and final meshes rendered in the real native viewer. The finished-output selector, Fit view and a real pointer drag were exercised; the drag changed the native camera position. Saved results survived reload and Resume. Rocket Mode reused successful geometry/refinement/texture/compact/quad checkpoints and rebuilt only the package.

The optional quad path initially failed on openings introduced by QuadriFlow. A single bounded alternative-settings probe still failed. The repair retained strict checks and used topology-preserving reduction/subdivision on closed components. The complete export and bake then passed. The generated README now describes the fallback and the correct **single-image** Pixal3D source; it does not claim multiview reconstruction. Archive contents and production metadata were inspected directly; downloading the ZIP through a native Save As dialog was unnecessary.

A new image was generated through the actual embedded creator (FLUX.2 Klein 4B), visibly displayed, accepted and returned to Single Image as exactly one reference. Gallery was opened mechanically and a saved image selected successfully. A discovered invalid Gallery limit was repaired with bounded pages of 24 and Load more. The single-context creator hides paired-category choices and retains the normal creator’s saved session.

All four method artworks loaded at matching dimensions. Font controls were exercised at Default, 175% and 200%; the 175% preference was read back from the service. A 720-pixel actual app container at 200% in dark theme had no horizontal overflow; full-width light-theme layout was also visually reviewed. All top-level views (workflow chooser, Images, History, Integrations, About and Roadmap) were also opened at 200% without horizontal overflow or error alerts; the Settings dialog was visually reviewed at 200%. The remaining ratios and all six persistence values were checked through source and targeted tests.

Cache preview showed 144 existing disposable files. A separately created 27-byte test partial was the **only selected category/file** cleared through the real GUI. It disappeared; existing worker-cache files remained. Busy-cache and busy-update UI states were checked with controlled frontend status, supported by backend guard tests. The red available-update state and the real green current-release response were checked; no update was applied.

HairDeck, Turnaround, 3D-Guided and Splat & Solid saved wizards reopened without generation. HairDeck’s saved 3D preview and Splat & Solid’s two comparison canvases loaded. Earlier workflow settings were retained. The temporary image-generation graph was restored from its independent pre-test snapshot. The public graph retains all 320 pre-existing nodes, their links and groups, adding only the 70-node Single Image section; saved test paths/results were removed from that public section.

## Proportional automated checks

- 39 targeted Foundry tests passed: single-image recipe/conditioning, runner behavior, image handoff, cache ownership/guards, font persistence, partial queue validation and release checks.
- 2 closed-quad fallback tests passed in the existing worker interpreter. The actual failed component also produced closed, consistently wound all-quad geometry within budget.
- 51 Foundry JavaScript modules passed Node parse checks.
- Public graph ownership, link closure, existing-node preservation and absence of new test data checked. Relevant diff whitespace checks passed.

## Scope and limits

This qualifies the selected path on the reference Windows / RTX 4080 SUPER 16 GB / 64 GB RAM machine. It is not a benchmark against every model, an 8 GB claim, a guarantee for arbitrary subjects, or an animation/physical-print certification. The pinned BF16 checkpoint is a documented runtime qualification difference from the latest official INT8 template. Webcam wiring reuses the established capture control; no physical webcam photo was taken in this pass. Existing workflow runs were reopened, not regenerated. Pinokio installation/update testing and publication are outside this local goal.

Research and implementation decisions: [recipe research](research/2026-11-08-single-image-foundry.md), [accepted plan](superpowers/plans/2026-11-08-local-foundry-single-image-ui.md). Task screenshots and detailed diagnostics are retained in the local `bench/single-image-local-20261108` directory.

## Final saved state

The final native save was read back from Comfy’s user-workflow service: 439 nodes and the completed Single Image run ID were retained. The final viewer was loaded and framed, with no error alerts; the Desktop host/window guard passed. The final package is `Single-Image-Cargo-Lander-e5fcf464-3010-d625f061.zip`; it contains the expected 36 files and a separate production record naming Single Image or Text. All changes remain local.

## Subsequent release authorization

After the local goal completed, Brian authorized the grounding correction and then committing/publishing after proof, with the installed Pinokio copy explicitly excluded. Preview.17 adds the grounded export node to the previously tested local update; see [grounding evidence](GROUNDING-VALIDATION.md) and the current [release record](RELEASE-VALIDATION.md). Earlier statements above describe the local-only milestone, not the later publication status.
