# Foundry localization implementation plan

Goal. Deliver a reusable English and Simplified Chinese experience locally, with one catalog and resolver contract for each presentation runtime.

Architecture. Shared catalogs own navigation, controls and common messages. Workflow catalogs live beside their workflow services. Explicit message IDs and named parameters flow to a small browser resolver and a Python resolver consuming the same JSON. Language switching updates bound text and attributes in place. Source English remains available for diagnostics and older saved runs.

User-approved decisions. Natural contemporary Simplified Chinese (zh-CN), English fallback, stable machine identifiers, preserved user prompts and files, no translation of licenses or researcher/model names, no commit or publication.

- [x] Research current source ownership and primary localization guidance. Record findings in docs/research/2026-11-10-localization/REPORT.md.
- [x] Implement catalog validation/resolution, safe browser bindings, language preference and bootstrap integration. Test missing keys, parameters, fallback, unsupported locales, and state-preserving language switching.
- [x] Migrate the shell, common controls and each workflow to explicit messages, preserving internal routing IDs and user data. Include accessible labels, help, errors, progress, advanced choices and export explanations.
- [x] Reuse the shared catalogs for server-owned messages and generated package explanations. Preserve file paths, metadata schemas and retained upstream text.
- [x] Rewrite README.md and author README.zh-CN.md. Explain workflows, setup, hardware, limitations, agent benefits, MCP, skill, updates and contributions.
- [x] Add skill compatibility metadata and instructions for checking live capabilities, app and skill compatibility, update availability and explaining notices in the user's language.
- [x] Perform a separate Chinese editorial review, terminology and placeholder audit, then inspect real GUI screens and language switching at default and 200% text sizes.
- [x] Restore user work and record verification once. Complete only after local behavior and review pass.

Ownership. foundry/localization.py reads and validates catalogs. web/foundry/i18n.js resolves and binds messages. dom.js renders descriptors through the same binding API. preferences.py owns saved locale. Each web/foundry/<workflow>/locales directory owns its domain. Common catalogs and the language/domain manifest live in web/foundry/locales. Python and JavaScript consume the same JSON files. README.md is the documentation source and README.zh-CN.md is its localized companion.

Testing. Focused catalog and preference regressions, JavaScript resolver/binding tests, source coverage audit, existing release/installer checks, and proportional live Comfy Desktop proof. Do not regenerate every asset to test wording. Latest user direction. After translation review and live checks pass, commit and publish the reviewed update and README, then update GitHub repository description and topics. Announcements remain outside this release authorization. Develop only in canonical source and the existing Comfy Desktop installation.

Additional accepted UI detail: add a restrained globe icon beside the language picker, using the existing icon owner and header visual style.

Added user scope: localize all twelve CCORE preset names and complete populated descriptions. Explain the author-recommended English generation language in all locales. Add literal Translate to English using the existing local Qwen helper and the same GPU lifecycle/cancellation owner, separate from creative enhancement. Test actual Chinese translation fidelity and resource release in the live wizard before publication. Language switching never overwrites existing user edits.

Language discussion recorded for the next additions: French requested; Spanish should use Latin American Spanish (es-419), natural to Brian's Tampa background, rather than Spain-specific wording. English/Chinese verification continues.

Latest release scope confirmed by Brian: publish English/Simplified Chinese first. Do not implement other languages yet. Plan the remaining languages together after this release. French and Latin American Spanish preferences are recorded for that later discussion.

Final added scope before publication: expose Q4/Q8 precision for the local translation helper, with friendly size/precision explanations. Use GPU-only translation, preserve the prompt on inability to fit and offer the smaller choice. One backend default owner returns the default through capabilities so future memory profiles can change it without wizard-specific policy. Verify both choices live before release.
