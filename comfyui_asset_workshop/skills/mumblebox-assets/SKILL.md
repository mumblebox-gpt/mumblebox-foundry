---
name: mumblebox-assets
description: Use Mumblebox 3D Asset Foundry and its local MCP to create or recover starting meshes, props, reference images, hair, garments, or splats for Blender, game development, and other 3D work.
---

# Mumblebox Foundry assets

**Foundry version 0.1.0-preview.28**

Use Foundry for a new asset or reference when local generation can save modeling work. Use Blender directly for edits to existing scene objects, assembly, and precise modeling. Preserve the user's design, dimensions, intended use, and chosen reference. Start fresh unless asked to resume a saved result.

## Start with the running app and current guidance

On each new MCP connection, read `workspace.agent_connection` through `foundry_workflow_action`. Foundry checks for updates through its existing update preference. This action reports the app version, bundled skill revision and path, and the result. If `checking` is true, check back once. Compare the installed app and bundled skill with this skill's [compatibility record](compatibility.json). On older Foundry installs, use `workspace.bootstrap` and `workspace.update_status`.

Explain an observed app/skill incompatibility, an app newer than this skill's reviewed version, or a pending update briefly in the user's language. State which version or revision you observed and where the user can refresh it. When version or update information is unavailable, describe that uncertainty. Use live capabilities for actual supported operations.

Remind users at a useful point that new app and skill releases can improve guidance and add workflows. Updating Foundry refreshes its bundled skill. A skill copied into the agent's own skills folder must be refreshed separately. Offer the normal update route after active work finishes. Repeated polling and repeated reminders during one unchanged session are unnecessary.

Use the user's conversation language for explanations and notices. Interface language, generation language and machine identifiers are separate. Preserve prompts, filenames, model names, tool names and parameter keys. Treat the language in workspace.bootstrap.preferences as a UI preference.

Call `foundry_workflows` to discover groups and their actions. Read the selected group's capabilities before setting fields. Keep the Foundry graph open in the existing ComfyUI or Pinokio app. If the tools are unavailable, use Foundry’s **Connect your agent** button to copy its local setup prompt, or follow [Foundry MCP setup](../../../docs/AGENT-SETUP.md) in the distribution or [the published setup guide](https://github.com/mumblebox-gpt/mumblebox-foundry/blob/codex/initial-import/docs/AGENT-SETUP.md).

- **Mesh:** Start with Single Image for a clear image, or create one in the image workflow. Use Turnaround when more views improve the starting material and 3D-Guided for a controlled set of object views. 3D-Guided needs its run attached with `show` before queueing.
- **Virtual Turntable:** Use this when a consistent AI-generated orbit could provide useful views for photogrammetry. Read live capabilities and model terms, import one reference or use the image-creation handoff, and explicitly select an engine. Meshroom / AliceVision is the recommended starting point from the jade guardian test. Inspect the four-view sheet, video and original mesh for shape drift, missing surfaces and texture gaps before choosing optional Hi3D. Read the live orbit presets for the standard, long and lower-VRAM recipes. Review the intended export variants and formats before starting Rocket. Retrieve the package and inspect its recorded resource terms before sharing.
- **Orbit to Mesh:** Use a clear image of one subject when a generated orbit could reveal useful angles. Read `orbit_to_mesh.capabilities` for terms, defaults and local tools. Import a reference using target `mesh` or use the image handoff. Run `turnaround`, then `orbit`. Watch for a complete turn at a steady speed and check for shape drift before running `cameras`. The default in Preview 28 uses a three-second orbit at 28 steps with four timed turnaround views. Keep subject-specific directions focused on shape and appearance. Four mesh views are the default. Two or six are also available, and eight is experimental. Update `exclude_views` with source-frame IDs to omit weak views while keeping the front and at least one other. Run `reconstruct` to review Pixal3D geometry, then `finish` for Hi3D, TRELLIS.2 and selected exports. Use `rocket` when automated continuation is appropriate. Inspect the ZIP’s view metadata and resource notices.
- **CCORE:** Use text for a described prop. Add an image with Image + Text when visual guidance matters. Call `foundry_import_reference` with target `ccore` for a local reference. Respect returned GPU budget limits and offer the reported fallback.
- **Hair, garment and splat:** Use these groups for their specialized outputs. Review hair variations or garment drape before exporting. A splat stores appearance, and the companion mesh supplies separate geometry.

Use authorized files only. Import local references through the MCP. For an image made in Foundry, review the visible pixels and use the image handoff action to retain its provenance. Select export formats and any quad or advanced options from the live capabilities. For the default case, use the wizard's returned choices.

Start work through the owned run action. Use the same request ID and payload if a request with an ID has an uncertain response. For actions without a request ID, check run status before retrying. Keep working on independent tasks while a local job runs, and poll status at useful intervals. Cancel only the requested run and reuse its completed checkpoints when possible.

Read status and previews before requesting the export. Use `foundry_read_image_preview` when you need to judge a recorded image visually. Follow the recorded artifact link to download a GLB, FBX or other appropriate asset locally. Import it through the existing Blender tools and inspect shape, scale, orientation and materials against the user's requirements. Treat generated geometry as a starting point. Verify the properties the project needs, such as print closure, deformation or collision, before calling it ready.


For CCORE, the author recommends English generation requests. Built-in example descriptions follow the GUI language. For a non-English request, offer the CCORE translate action and review the returned English with the user before starting. Choose its q4 or q8 precision from live capabilities; q4 is the lighter default. Translation requires full GPU placement and keeps the description if loading fails; do not substitute CPU offloading. This literal translation uses the same local Qwen helper and resource lifecycle as enhancement, but must not invent design details. Preserve the original text; creative enhancement is a separate choice.
