# English and Simplified Chinese — preview.22

Canonical source: C:/Dev/mumblebox-foundry, codex/initial-import. Verification used the existing Comfy Desktop installation and selected Mumblebox - Foundry GUI Review graph (461 nodes). Saved inputs, models, assets and the completed Utility rover were preserved. The installed Pinokio copy was not edited.

## Language and GUI proof

The actual language selector switched English to Simplified Chinese and back without navigation, model downloads or recreation of the graph. A filled description containing literal English and Chinese text remained unchanged. A loaded CCORE Image + Text GLB kept the same canvas and graph identities, stayed loaded, and visibly rendered after both switches. The image-reference control, exact reference URL, text controls and edited prompt also stayed intact.

Reviewed the workflow chooser, Images, History, Integrations, About and Roadmap, plus Single Image, Turnaround, both CCORE wizards, HairDeck, Garment Particles, 3D-Guided and Splat & Solid. Human headings and controls are localized; existing user asset names, official model names and file paths remain exact. HairDeck opened in dark theme with its native viewer and five saved review images; no alert was present. English remains available through the same selector.

The actual Font radio selected 200%. All six top-level sections and Settings opened in Chinese with no horizontal overflow or error alert. The normal size was restored. The globe and native-language label fit the existing header. Native 3D previews and the large-font Settings dialog were visually inspected in the real Desktop renderer.

## Built-in examples and local translation

The actual CCORE example selector displayed all twelve Chinese category/name pairs. Choosing the field-radio preset populated both its Chinese name and complete Chinese description. Choosing a language alone does not overwrite an existing description.

The current CCORE author instructions recommend English requests. Both wizards explain this and provide a separate Translate to English action. The existing local Qwen3.5-9B-Heretic helper receives a strict literal-translation instruction and JSON schema. A separate radio choice offers Q4 (about 5.8 GB of weights, recommended for less VRAM) and Q8 (about 9.8 GB of weights, higher numerical precision), with additional working memory required. The backend owns the default through a memory-profile hook; capabilities deliver that default to both wizards. Translation shares the existing lifecycle barrier, memory release, isolated worker and cancellation owner with enhancement. It uses an 8,192-token context, explicit full CUDA placement and automatic layer fitting disabled: it does not silently offload to CPU. A failed load preserves the original prompt and explains the Q4/free-VRAM alternatives. Translation does not queue asset generation automatically.

A real GUI translation converted a Chinese radio description to:

> Create a static portable field radio. The casing is olive green metal, 30 cm wide, with only two cream-colored knobs, both on the front right; a black circular speaker on the front left. There is only one orange handle on top. The back is flat, with no logos, text, figures, base, or surrounding scene. Do not add an antenna or extra buttons.

Review confirmed the exact count, color, placement, width and exclusions were retained with no creative additions. A subsequent real pointer activation of the translation control completed successfully. A bounded NVIDIA-driver sample measured 14,197 MiB peak total GPU usage, then about 5.2–5.4 GiB after the helper exited. The worker model appeared during processing and was removed afterward. No inference or memory crash occurred. Comfy's own memory reading was not used as proof of the separate helper's GPU allocation.

After adding the precision selector, both Q4 and Q8 separately completed the same Chinese request through the actual translation button under the strict GPU policy, preserving the requirements above. The radio selection survived reopening the wizard, and both the selector and its help switched between English and Chinese without changing the prompt. A focused failed-CUDA-worker test verifies no CPU retry, unchanged source input and worker cleanup. A final review also caught and repaired a misplaced operation check in the new-job start path; a regression test confirms fresh asset requests reach the existing native queue owner.

The Stop assistant control cancelled another translation request. The original Chinese prompt remained exact, the helper returned idle and no helper model remained resident. This validates the exercised GPU/runtime configuration, not every device, language or memory pressure condition.

## Packages, contracts and review

The shared package renderer uses the saved interface language for newly published package READMEs. A Chinese package fixture passed its file-inventory/link and checksum validation, preserved the source mesh bytes, and left user names and retained license summaries unchanged. Existing packages are not rewritten.

The Chinese text received a separate editorial review, including workflow terminology, memory warnings, all twelve complete example descriptions and both READMEs. The release validates raw catalog key parity and named placeholders. The agent skill remains authoritative English guidance and tells agents to check live capabilities, app/skill compatibility and available updates, communicate notices in the user's language and refresh separately copied skills.

Verification passed: 168 Foundry Python tests, 34 browser-module tests, five CCORE description contract tests, seven release/installer tests and the companion-skill validator. All 58 Foundry JavaScript modules parsed. Catalog and package checks were repeated after the final editorial corrections. Published source/archive identity is recorded in the release record. Local detailed logs remain in bench/localization-20261110 and are excluded from the software package.

## Scope

This is an English/Simplified Chinese release. French, Latin American Spanish and the other languages remain pending a separate agreed plan. No new announcement or installed Pinokio update was performed. Asset generation was not repeated for every language or workflow; saved previews, inputs and GUI controls were exercised proportionally. The new inference test was the local text translation itself.
