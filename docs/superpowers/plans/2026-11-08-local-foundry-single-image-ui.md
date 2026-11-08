# Local Single Image and Foundry UI implementation plan

**Goal:** Deliver the approved local Single Image method and full-app accessibility/presentation improvements.
**Architecture:** Official single-image geometry recipe owns its inputs and sampling. Existing durable queue, checkpoint runner, Hi3D, cleanup and exports remain shared services. The new independent graph has its own ID namespace and GUI session. No existing recipe is replaced.
**Stack:** Existing Python Comfy nodes, vanilla shadow-DOM wizard, native Comfy preview, CSS tokens.
**Spec:** Brian's accepted goal in this chat and ../.. /research/2026-11-08-single-image-foundry.md.
**Execution:** Inline, existing branch, no delegation or commits per Brian.

## Constraints
Canonical C:/Dev/mumblebox-foundry; actual existing Comfy Desktop. Preserve all user graph/settings/assets and initial HairDeck result snapshot. No direct installed Pinokio mutations, commits, pushes or publication.

## Review focus
One reference only; no turnaround model ancestry or false stages. Correct original image at refinement/texture. Independent node IDs/output callbacks. Selected exports and resumed changes invalidate descendants correctly. All font choices reflow in both themes and small windows; real preview remains usable.

- [x] Recipe and runner: add single_image/graph.py and definition.py with archived official source/provenance; narrow method hooks in image_to_3d/{graph,runs,progress,readiness}. Tests in foundry_tests/test_single_image_method.py cover input count, reference conditioning, native sampler constants, IDs, no early texture/unused models, selected dependencies and invalidation. Expose template via existing routes, preserve shared package/catalog.
- [x] Wizard and live graph: single/{controller,pages,graph}.js reuse established output/preview/export controls. Starting page supports upload/drop/camera/Gallery/Create Image direct return. Four meaningful pages, Rocket, settings, initial/refined/clean/final previews and resume. Method first/default in views/home.js. Test actual control-to-node/run binding and one real complete output through Desktop; repair observed defects.
- [x] Artwork: create four consistent images using existing visual direction, store owned assets, match card proportions. No unrelated generated media.
- [x] UI/UX audit after pipeline works: inspect full app and apply focused theme/layout/component ownership fixes; concise copy/icons, output badges, help/errors, contrast/focus, navigation, preview space, compact spacing. Add persistent font_size preference/menu alongside Theme and relative CSS tokens. Check all major views at default/large sizes and narrow container in light/dark.
- [x] Separate improvement pass: implement Brian's requested Purge Cache control near the top of Settings. Preview exact owned disposable files/bytes; explicit confirmation, active-job guard, preserve models/inputs/saved outputs/settings. Scoped scratch/partial-download ownership and narrow fixture tests; never blanket-delete machine caches. This is the significant additional usability improvement.
- [x] Finish: relevant tests, one bounded GUI/regression pass, update local changelog/roadmap/README/model/catalog/MCP contracts as affected. Save public graph and actual working graph with reviewable completed result. Record evidence once in bench/single-image-local-20261108/RESULTS.md.

## Completion
Mark goal complete only when every agreed feature above is implemented and works locally in the actual GUI, the new method has real visible previews and correct selected outputs/resume, regressions are checked proportionally, and Brian can inspect the final result in the existing Comfy app. Leave all work uncommitted and unpublished.

## Accepted additions during execution
- Header update flag beneath top controls: green Up to date, red Update available, neutral checking/unavailable; reuse release-check owner/cache, actionable supported update details, disabled update action during processing/downloads/exports. No actual update, release or Pinokio mutation in this job.
- Create Image from Single Image must default to one-image creation and return one accepted reference directly, retaining provenance and preserving the normal paired creator session.
- QuadriFlow remains optional/off by default. Show its CPU use, normal high CPU load and potential several-minute duration beside its output choice and during the running stage.
- Latest Font direction: glasses icon + Font; options Default, 112%, 125%, 150%, 175%, 200% (no size names). Preserve older stored values as aliases; verify reflow up to 200%.
- Refactor root README into a friendly product introduction, workflow comparison, installation/start steps, outputs, credits and focused technical links. Local only.

## Delivered evidence

The six entries above are verified by [local update validation](../../LOCAL-UPDATE-VALIDATION.md): a completed real asset run, GUI interactions and reload/resume, four artwork checks, full-app large-text checks, a scoped cache fixture, proportional tests and the saved 439-node native graph with a loaded final preview. Work remains uncommitted and unpublished.
