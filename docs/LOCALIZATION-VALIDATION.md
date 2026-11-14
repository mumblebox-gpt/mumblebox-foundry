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

## Six-language expansion

The new pass uses the same nine domain owners and one manifest. The release builder derives translated root README filenames from the manifest, and the picker uses the same active language list. The live preview.22 baseline exposed four English Single Image step labels and two English Quads badges in Chinese. Their text now goes through the existing bindings, with a live recheck required for the new build.

| Locale | Editorial review and catalogs | Archive check | Live app check |
| --- | --- | --- | --- |
| es-419 | All 2,415 entries reviewed, including 12 CCORE prompts and the README | Passed | 15 views at default and 200%, plus preserved form and preview |
| fr | Pending | Pending | Pending |
| pt-BR | Pending | Pending | Pending |
| de | Pending | Pending | Pending |
| ja | Pending | Pending | Pending |
| ko | Pending | Pending | Pending |

### Latin American Spanish checkpoint

The local candidate adds Español (Latinoamérica) in the header and Settings, the nine catalog files and README.es-419.md. The Spanish editorial pass corrected workflow titles, model-memory language, mesh terminology, and all twelve CCORE prop descriptions against their English meaning. All raw catalog keys and named placeholders match. Remaining identical terms such as Rocket Mode are intentional product names.

The actual Foundry Comfy Desktop app opened the workflow chooser, Images, History, Integrations, About, Roadmap, Settings, and eight wizard entries at both default and 200% text. There was no horizontal overflow, clipped action or error alert in those 30 checks. Single Image steps now resolve through the mesh catalog. Switching Spanish to English and back preserved the edited textarea and loaded preview canvas. The preset selector exposed all twelve examples and populated the full localized description. The normal preference endpoint returned a localized invalid-language error and retained Spanish.

The package fixture retains its original user name, mesh bytes, license summary, catalog metadata and valid archive checksums. The final source checks passed 168 Foundry Python and 34 JavaScript tests, plus the seven release/installer tests during the Spanish install pass. Live check evidence is in bench/localization-six-20261110/live-es-419.json. Opening Splat during the live checks temporarily removed one graph note. Reloading the serialized graph restored the note, all 461 nodes and the selected preview. The final installed files match canonical source and Foundry is open in Spanish.

The live Spanish checkpoint used the local candidate before the release version bump. Preview.23 is the Spanish release of that candidate. The other locales were paused at that checkpoint.

## French and Brazilian Portuguese — local preview.24

French was installed and checked in the existing Comfy Desktop Foundry before Brazilian Portuguese drafting began. Both locales cover all 2,921 English keys across the same 12 catalog domains. Technical names, placeholders and numeric settings were checked against the source. CCORE’s twelve examples were reviewed against the original material, geometry and part-count instructions. The local project READMEs link to all five languages and match the app and companion skill version.

The live Foundry window was checked in both languages across 20 screens at default and 200% text size. The header and Settings pickers switched the interface in place. Both CCORE wizards populated all twelve localized examples. An edited description and two loaded Orbit to Mesh previews survived the language switches. The prior Foundry graph, output state, font size, language and History → Videos view were restored.

The focused Python localization and ZIP tests, JavaScript binding tests and release installer fixture tests passed. The ZIP fixtures retained mesh bytes, paths, license notices and checksums. The installed locale files match the canonical source. This is a local verification checkpoint.

## German, Japanese, Korean and Hindi — local update, 2026-11-13

This update continues the existing locale plan across the 13 active catalog domains. Add Deutsch, 日本語, 한국어 and हिन्दी one at a time, with a linked project README for each locale. Review plain, everyday language and retain exact technical and machine values. Check the saved Foundry workflow at default and 200% text, CCORE examples, localized package text and preference restoration. Brian requested this work locally. The earlier publication instructions apply to the historical plan.

- German — 3,078 messages, README and localized archive fixtures checked. Nine screens passed at default and 200% in the existing Comfy Desktop window. All twelve CCORE presets loaded localized descriptions. Language switching kept the edited description and previously loaded orbit video. The 620-node graph and original display preferences were restored.
- Japanese — 3,078 messages, README and localized archive fixtures checked. Nine screens passed at default and 200%. All twelve CCORE recipes loaded Japanese descriptions. The edited text and loaded video survived language switches. The original graph and preferences were restored.
- Korean — 3,078 messages, README and localized archive fixtures checked. Nine live screens at default and 200%, all twelve localized CCORE examples, and unchanged edited text and loaded video on language switches. Restored the original 620-node graph and preferences.
- Hindi — 3,078 messages, README and localized archive fixtures checked. Nine live screens at default and 200%, all twelve localized CCORE examples, and unchanged edited text and loaded video on language switches.

The final installed manifest offered all nine languages. Every picker option was selected in the real Comfy Desktop Foundry. Each new locale covered all 13 catalog domains. Across the new locales, 72 screen checks found no clipped controls or horizontal overflow. The shared catalog and in-place binding tests, per-locale asset ZIP fixtures and existing release inventory tests passed. The original 620-node graph, 11 output references, English display, default text size, light theme and saved Orbit with Splats export view were restored. All four installed locale sets match the source.
