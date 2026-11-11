# Foundry localization research

Date: 2026-11-10. Scope: the existing plain JavaScript DOM frontend and Python backend. Research/source inspection only; no runtime, installed-app or native-speaker review credit.

## Recommendation

Use shared UTF-8 catalogs with stable semantic IDs, complete messages, named arguments and explicit English fallback. Keep messages grouped by feature/domain and one authoritative locale/formatting resolver. Bind DOM text and attributes explicitly, updating them in place. Python can consume the same catalogs for user-facing backend messages and package documentation. This architecture is a project recommendation, not a standards requirement.

Inspected starting points: web/foundry/shell.js has disabled future languages including “Mandarin”; foundry/preferences.py always reads English and rejects other languages; web/foundry/dom.js uses createElement/append; finishing/package_readme.py owns generated package documentation. Reuse these owners.

## Locale and natural Chinese

Offer English (en) and 简体中文 (zh-CN). Call the latter “Simplified Chinese” in English rather than “Mandarin”: this task concerns a written locale/script, whereas Mandarin identifies a language variety. BCP 47 distinguishes language, script and region: zh-Hans explicitly means Simplified script, and zh-CN means Chinese used in Mainland China. W3C documents compatibility reasons for retaining zh rather than substituting cmn. For the requested Mainland-oriented translation, zh-CN is appropriate; it does not represent every Chinese locale. Consider zh-Hans deliberately if regional neutrality becomes a requirement. [W3C: choosing tags](https://www.w3.org/International/questions/qa-choosing-language-tags.en.html), [W3C: script and region](https://www.w3.org/International/articles/language-tags/).

Translate whole meanings into natural Chinese, not English word order. Use a short consistent Foundry glossary: workflow/工作流, model/模型, mesh/网格, texture/纹理 and export/导出 are proposed wording, not mandated upstream terminology. Preserve brands and model names. Review compact controls, explanatory text, remedies and accessibility labels in context. Native-speaker review remains the strongest idiomatic-quality check. Microsoft provides established terminology and locale style resources; its official listing was verified, but the downloadable Simplified Chinese PDF endpoint could not be fully read through the web tool, so this report makes no detailed claim from that PDF. [Microsoft language resources](https://learn.microsoft.com/en-us/globalization/reference/microsoft-language-resources), [Microsoft style-guide listing](https://github.com/MicrosoftDocs/globalization/blob/main/globalization/reference/microsoft-style-guides.md).

## Catalog ownership, locality and formatting

- Use semantic IDs such as export.completed and models.unload.action, plus translator context. The same English word can require different translations: navigation “Back” differs from an asset’s rear view. Reuse only an identical meaning/context. [W3C: string reuse](https://www.w3.org/International/articles/text-reuse/).
- Use complete messages with named, reorderable placeholders, for example “Exported {count} files to {folder}”. Do not concatenate translated sentence fragments or append English suffixes. [W3C: composite messages](https://www.w3.org/International/articles/composite-messages/).
- Shared JSON is suitable here: locale → message ID → string, with documented argument types/context and optional whole-message variants. English owns the source text. Check message-key and placeholder parity mechanically. Avoid independently maintained duplicate dictionaries in Python and JavaScript.
- Use Intl.NumberFormat, Intl.DateTimeFormat and, when needed, Intl.PluralRules with the selected interface locale explicitly. Keep values numeric in state/API data. Chinese has one cardinal plural form; English has two. Do not apply an English count-equals-one rule universally. [MDN: Intl](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl), [MDN: plural rules](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules).
- Named interpolation and whole-message variants are reasonable for this two-language first version; explicitly document that this is not ICU syntax. Adopt a maintained ICU/MessageFormat implementation if nested grammar or translation tooling later requires it, rather than writing its parser. ICU recommends complete message units and whole-sentence plural/select variants; its syntax quoting is separate from HTML escaping. [ICU: formatting messages](https://unicode-org.github.io/icu/userguide/format_parse/messages/). Unicode separately documents current MessageFormat 2; older ICU guide prose about its development status is not current-standard evidence. [Unicode MessageFormat](https://messageformat.unicode.org/).

## Safe DOM and state-preserving switching

Insert plain translations/arguments as text nodes; set placeholder, title, aria-label, alt and option labels through explicit DOM setters. Never parse interpolated user filenames, asset names or errors with innerHTML. Escape at the actual output sink; interpolation is not HTML escaping. Keep Markdown escaping in the existing README renderer. [MDN: innerHTML security](https://developer.mozilla.org/en-US/docs/Web/API/Element/innerHTML).

Retain message descriptors so already-visible errors and progress can be reformatted after a switch. Update dedicated text leaves: assigning a container’s textContent removes every child, including icons and controls. [MDN: textContent behavior](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent).

Project recommendation: do not rebuild the shell, reopen a wizard or reload the page on locale change. Preserve drafts, file inputs, step selection, focus/selection, previews, timers, subscriptions and in-flight jobs. New asynchronous output uses the currently selected locale. Set lang on the Foundry root because it is embedded in ComfyUI; do not change the surrounding host document’s language. W3C describes inheritance and scoping differently localized content. [W3C: declaring language](https://www.w3.org/International/questions/qa-html-language-declarations).

Keep layouts flexible for translated controls and Chinese wrapping; spaces are not required between all break opportunities. [W3C: language-sensitive line breaking](https://www.w3.org/International/techniques/authoring-html.en?open=language&open=langvalues). Persist an allowlisted locale, use English for invalid/missing values and respect explicit user choice. If switching optimistically, handle failed saves and stale responses without reverting a later selection.

## Backend, documentation and protected content

| Surface | Recommended contract |
|---|---|
| Known errors/validation | Stable message ID/code plus typed arguments; render using the current UI locale. Preserve original diagnostic detail separately. Unknown third-party errors get a translated wrapper with unchanged technical detail. Do not identify arbitrary errors by matching English prose. |
| Progress | Stable stage/status ID, counts, timestamps and arguments. Keep raw worker logs intact. Reformat the latest status on switch; do not restart the operation. |
| Python-rendered text | Shared catalog with explicit per-call locale; no process-global locale mutation in a concurrent server. Python’s gettext class API is an established alternative for separately owned backend catalogs/on-the-fly switching, but adds a second catalog format here. [Python gettext](https://docs.python.org/3/library/gettext.html). |
| Export README | Extend the existing package_readme.py renderer with explicit export locale. Translate headings, controlled descriptions, recorded labels and prose while preserving actual inventory, counts, limitations and provenance. Snapshot the locale for that export; do not rewrite completed exports after a UI switch. |
| Machine/user data | Preserve filenames/directories, URLs, model/checkpoint/LoRA identifiers, API enums, JSON keys, workflow IDs, seeds, hashes, license source texts, user asset names, prompts and generated content unless another explicit feature authorizes changing them. |

The export recommendation follows the repository’s package-catalog/README consistency contract. Localize controlled description/status IDs, not arbitrary manifest values, and do not create a competing translated inventory. Keep README.md and archive structure stable; language changes its human-readable content.

Use translate="no" on prompt/code/identifier displays when useful to browser translation tools. It is a presentation hint, not a data-integrity boundary. [MDN: translate attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/translate).

**Interface language and generation language are separate behaviors.** A locale switch must not translate prompts, alter model input, select another model or add output-language instructions. An English example already inserted into a prompt remains actual model input; translate surrounding help separately. Offering a localized sample prompt later should be an explicit user action.

## Evidence needed during implementation

Check catalog/placeholder parity, fallback and malicious-looking argument text. Verify shell, cards, settings, dialogs, active wizard, validation, progress, history/gallery and README in both languages. Switch away/back with a draft, file selection and running job; compare prompt/model/file payloads before/after. Inspect compact/large-text Chinese layout and compare generated README against archive contents. Report automated, runtime, mechanical and linguistic review separately; this research supplies none of those completion credits.

## CCORE preset and translation follow-up

The current official CCORE model card (checked 2026-11-10) explicitly instructs users to send an English asset request. The base Qwen3.5-9B documentation describes multilingual support. Foundry therefore offers localized built-in descriptions for reading/editing and a separate literal Translate to English action using its existing Qwen3.5-9B-Heretic helper. The translated English remains editable and is never sent into asset generation automatically. Creative enhancement remains separate. Real translation and memory validation is recorded in the release validation document.

Sources: [CCORE model card](https://huggingface.co/ccore/Qwen3.5-4B-GLB-3D-Coder), [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B).
