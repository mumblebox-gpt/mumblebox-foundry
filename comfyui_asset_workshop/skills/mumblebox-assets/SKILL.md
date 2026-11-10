---
name: mumblebox-assets
description: Use Mumblebox 3D Asset Foundry and its local MCP to create or recover starting meshes, props, reference images, hair, garments, or splats for Blender, game development, and other 3D work.
---

# Mumblebox Foundry assets

Use Foundry for a new asset or reference when local generation can save modeling work. Use Blender directly for edits to existing scene objects, assembly, and precise modeling. Preserve the user's design, dimensions, intended use, and chosen reference. Start fresh unless asked to resume a saved result.

Call `foundry_workflows` to discover groups and their actions. Read the selected group's capabilities before setting fields. Keep the Foundry graph open in the existing ComfyUI or Pinokio app. If the tools are unavailable, follow [Foundry MCP setup](../../../docs/AGENT-SETUP.md) in the distribution or [the published setup guide](https://github.com/mumblebox-gpt/mumblebox-foundry/blob/codex/initial-import/docs/AGENT-SETUP.md).

- **Mesh:** Start with Single Image for a clear image, or create one in the image workflow. Use Turnaround when more views improve the starting material and 3D-Guided for a controlled set of object views. 3D-Guided needs its run attached with `show` before queueing.
- **CCORE:** Use text for a described prop. Add an image with Image + Text when visual guidance matters. Call `foundry_import_reference` with target `ccore` for a local reference. Respect returned GPU budget limits and offer the reported fallback.
- **Hair, garment and splat:** Use these groups for their specialized outputs. Review hair variations or garment drape before exporting. A splat stores appearance, and the companion mesh supplies separate geometry.

Use authorized files only. Import local references through the MCP. For an image made in Foundry, review the visible pixels and use the image handoff action to retain its provenance. Select export formats and any quad or advanced options from the live capabilities. For the default case, use the wizard's returned choices.

Start work through the owned run action. Use the same request ID and payload if a request with an ID has an uncertain response. For actions without a request ID, check run status before retrying. Keep working on independent tasks while a local job runs, and poll status at useful intervals. Cancel only the requested run and reuse its completed checkpoints when possible.

Read status and previews before requesting the export. Use `foundry_read_image_preview` when you need to judge a recorded image visually. Follow the recorded artifact link to download a GLB, FBX or other appropriate asset locally. Import it through the existing Blender tools and inspect shape, scale, orientation and materials against the user's requirements. Treat generated geometry as a starting point. Verify the properties the project needs, such as print closure, deformation or collision, before calling it ready.

