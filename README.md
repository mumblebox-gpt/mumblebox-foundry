# Mumblebox 3D Asset Foundry

A local ComfyUI interface for turning reference images into textured 3D assets. A guided workflow connects four-view image generation, Pixal3D/TRELLIS.2 geometry, Hi3D refinement, measured cleanup, texturing and selected exports.

**Preview 0.1.0-preview.14 — Windows / NVIDIA.** Install through [Pinokio](docs/PINOKIO.md) for automated software setup, or use the [manual installation](INSTALL.md). Pinokio opens the Foundry interface directly. Original Foundry code is Apache-2.0; models and third-party tools retain their own terms. Read [third-party notices](THIRD-PARTY.md), particularly before commercial use.

## Included

- Three independent mesh methods and wizards, selected under **Create a Mesh from an Image**: **Turnaround**, **3D-Guided** and **Splat & Solid**.
- A separate image creator: front/back pairs for assets, or single background/general images. References, compatible installed LoRAs and model defaults are available on one scrolling page.
- Side-by-side image editing with rectangle, ellipse, brush, erase, polygon and magnetic selections. Edits are previews until accepted; original revisions remain available.
- Image Gallery with grouped pairs, filters, revision restore, download and confirmed removal. Deleting entries and deleting their files are separate choices.
- Save an accepted pair and send it into the 3D wizard, retaining reference roles and generation provenance.
- Supported Qwen, FLUX and Klein turnaround choices with model-specific settings and license information.
- Four-view review, mesh/refinement controls, final mesh preview, export choices and a downloadable package.
- Detailed and reduced triangle meshes, UVs and detail baking. Turnaround retains optional quad retopology and its authoring formats. 3D-Guided exports detailed/reduced GLB or FBX and print STL; its retained quad branch is disabled for this release.
- Rocket Mode runs remaining stages and selected exports without optional review stops. Use the manual wizard when you want to inspect stages and deselect inconsistent views.
- A package README, file catalog, measurements and resources/licensing record that reflect the selected outputs.
- Asset history, light/dark themes, system telemetry, model unloading and first-use model downloads.
- A Civitai browser for installing image models and LoRAs. These are initial-image resources; downloads do not expand the supported turnaround models.
- Installed-model management covers registered ComfyUI, Hi3D, TRELLIS and model-cache locations. Review the exact file before deleting; required published resources are prepared again when their workflow needs them.
- A [local MCP server](docs/AGENT-SETUP.md) for agents using the same workflow services as the interface.

Future workflow cards are labeled Coming soon. Standalone mesh repair, video reconstruction, turntable capture and action figures are not shipped as completed workflows.

### Create Rigged Hair with HairDeck

Powered by HairDeck from hyz317 and its researchers, with FengLairh's ComfyUI integration. Supply a clear hairstyle image, generate sequential variations, inspect hair and predicted chains, adjust head alignment and materials, then export static GLB or a skinned VRM 0.x avatar. Optional outputs include a head-turn MP4, preprocessing images and editable card/chain data. Results use shared History and catalog-driven README/ZIP services. These are stylized hair cards, not strand Groom or a complete character rigger.

Hair software is installed with Foundry. Approximately 6.4 GB of weights and selected VRM export tools are prepared on first workflow use. They are not downloaded simply by installing or opening Foundry. The MCP includes matching `foundry_hair_*` tools.

## Workflow

**Turnaround:** supply references → generate/review four views → build the fully decoded mesh → refine with Hi3D → clean geometry → texture and bake selected versions → export.

**3D-Guided (Objects):** supply one original image and a description → generate an appearance concept sheet → build a rough mesh from the original image alone → prepare the actual working proxy → render four measured Blender views → enhance a depth-guided sheet using the concept for appearance → split and select usable views → reconstruct using the matching numerical cameras → refine, clean, texture and export. This method currently targets solid standalone props readable from front, back and both sides; people and vehicles need separately qualified presets. It does not promise better quality for every object.

**Splat & Solid (Idol):** one reference → Gaussian splat and extracted mesh → optional Hi3D refinement → closed master and lightweight companion → linked geometry comparison → selected SPZ/GLB/MP4/PNG package. Appearance lives in the splat; the meshes are separate geometry in its coordinate frame. See [Splat & Solid](docs/SPLAT-SOLID.md) for controls and limits.

The manual 3D-Guided wizard includes selected-area concept editing and four image checkboxes before reconstruction. Selected images retain their camera identity. Asset packages include numerical camera records; the separate private production archive contains original images, prompts and intermediate files. Review that private archive before sharing it.

The detailed master is retained. Turnaround's optional quad retopology provides an editing starting point, not a rig or an animation-ready guarantee. GLB uses triangles; Turnaround's quad-preserving authoring formats remain available. A print export includes geometry checks, but physical printability still depends on dimensions, material and printer.

## Get started

1. In Pinokio, install this repository: https://github.com/mumblebox-gpt/mumblebox-foundry
2. Choose **Install**, then **Start Foundry**. **Open Foundry** shows the interface inside Pinokio.
3. Expand **Create a Mesh from an Image**, choose a method and supply your image. Each wizard also offers **Create an image** when you need a starting reference.

The [Pinokio guide](docs/PINOKIO.md) covers installation, updates, repair and MCP setup. Existing ComfyUI users can follow [INSTALL.md](INSTALL.md) and open the packaged `Mumblebox 3D Asset Foundry.json` workflow instead.

The public workflow contains no saved test images, meshes, textures, project history or credentials. Model weights are not included. Required files for the selected workflow are prepared from pinned upstream sources before generation; opening the interface does not download models. Access-gated alternatives may require an account/token and acceptance of their upstream terms.

## Compatibility and validation

The reference system uses an NVIDIA RTX 4080 SUPER (16 GB VRAM), 64 GB system RAM and Windows. This is not an 8 GB compatibility claim. Additional memory profiles remain placeholders; Default uses the tested settings.

See [dependencies.json](dependencies.json) for pinned reference versions and [release validation](docs/RELEASE-VALIDATION.md) for the exact evidence and remaining limits. New asset categories and alternate turnaround models are enabled; their generation quality has not been exhaustively qualified.

## Project

- [Public releases and downloads](https://github.com/mumblebox-gpt/mumblebox-foundry/releases)
- [Issues](https://github.com/mumblebox-gpt/mumblebox-foundry/issues)
- [Mumblebox projects](https://github.com/mumblebox-gpt?tab=repositories)

Settings offers **Check for updates** and an automatic startup check. In Pinokio, stop Foundry and choose **Update** to install an eligible published release. Updates are deliberate and preserve saved assets, settings and model weights; a GitHub push does not silently change your installation.

Powered by Hi3D 1.0 - http://hi3d.ai/ . Foundry brings together research from Sperid Labs (Idol), HairDeck, Pixal3D, TRELLIS.2, Hi3D, Qwen, Black Forest Labs and Meta, with ComfyUI, Blender and community integrations. Our contribution is connecting these tools into practical, shareable workflows with useful defaults and saved results.
