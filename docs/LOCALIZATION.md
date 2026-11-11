# Foundry localization

English is the authoritative interface and documentation source. Simplified Chinese uses natural contemporary wording, translating meaning rather than English sentence structure. Model/researcher names stay recognizable. Say GPU VRAM (显存) and system RAM (系统内存) distinctly; do not promise automatic CPU fallback for GPU-required models.

## One owner per responsibility

- web/foundry/locales/manifest.json owns supported language IDs, native-language names and domain locations.
- Each workflow owns its nearby English and translated JSON catalogs. Common shell messages live in web/foundry/locales; package explanations live in web/foundry/package/locales.
- web/foundry/i18n.js owns browser resolution, named parameters and in-place text/attribute bindings. dom.js uses those bindings. preferences.py owns the saved language.
- foundry/localization.py reads the same manifest and JSON for server message metadata and the shared package README renderer. There is no second set of Python translations.
- finishing/package_readme.py owns human package documentation. The archive publisher selects the saved interface language at publication. Existing packages, machine catalogs, checksums and retained licenses are unchanged.

## Message contract

Use msg("domain.stable_id", {namedValue}) at a presentation site. Pass the descriptor to el, button, field, hint, setText or bindAttribute. Use a complete sentence with named parameters. Do not join English word endings or assume translated word order. Supply complete singular/plural alternatives when needed.

A language change only changes bound text and attributes. It does not recreate the wizard, viewer, selected files or form controls, reload models or reload the page. The Foundry root gets its own lang attribute; the surrounding ComfyUI interface is independent. Chinese fonts use local system fallbacks with no download.

Stable source English remains available for logs, MCP/tool identifiers and native graph metadata. New service errors include error_i18n with {key, values} alongside the original diagnostic. sourceMessage and translate_source are explicit presentation adapters for known human messages from older saved runs and capability captions. They are never applied to a whole DOM, document, user prompt or arbitrary user data.

Built-in CCORE example names and complete descriptions are intentionally localized content. English entries are checked against the authoritative examples.json. Choosing a preset fills the selected language; switching language never overwrites user edits. CCORE recommends English input, so its separate Translate to English action uses the existing local Qwen helper, strict literal-translation instructions and the shared memory/cancellation lifecycle. The result is editable and reviewed before generation. Q4/Q8 are explicit API precision values. enhancement.py owns the profile-default function and returns its result through capabilities; the wizard owns the saved explicit selection. Translation uses a bounded 8K context and requires full CUDA placement with automatic CPU offloading disabled. A failure keeps the draft and explains the smaller-model option. Creative enhancement remains a different action.

Keep all of these exact: user prompts and names, model instructions, model/file identifiers, numerical settings, paths, URLs, schemas, tool/action IDs, retained third-party notices and license texts. Translate explanations around them. Unknown diagnostics remain available verbatim for support.

## Add another language

1. Add its BCP 47 ID and native name to the manifest; create that language's JSON beside every English catalog.
2. Keep keys and named placeholders identical. English fallback handles a missing translation; release review must check completeness.
3. Review meaning, terminology, memory warnings, technical limitations and accessibility labels separately from authoring.
4. Add a linked root README named README.<locale>.md. The release builder includes READMEs for all languages declared in the manifest.
5. Run the focused Python and JavaScript localization checks. Test the real language selector with a filled form, selected reference and loaded preview, including 200% text. Confirm no reinitialization and no horizontal overflow.

README.md and README.zh-CN.md describe the same product, benefits, limits and installation choices. English skill instructions remain the agent authority: check current app capabilities, app/skill compatibility and update availability, then explain relevant notices in the user's language. Do not translate model prompts merely because the interface language changed.
