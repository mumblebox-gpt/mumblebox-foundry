# Mumblebox 3D Asset Foundry

[English](README.md) · [简体中文](docs/README.zh-CN.md) · [Español (Latinoamérica)](docs/README.es-419.md)

**Make images and 3D assets locally, on your own or alongside your coding agent.**

Foundry brings practical AI workflows into guided wizards with useful defaults, previews and saved results. You can start without knowing ComfyUI. The Pinokio installer configures the software and dependencies. The underlying graphs stay available when you want more control.

Explore game props, character parts, hair, splats and assets for creative projects or 3D printing. Inspect each result for its intended use. Generated geometry can still need editing, retopology, fitting or print preparation.

[Install with Pinokio](docs/PINOKIO.md) · [Published downloads](https://github.com/mumblebox-gpt/mumblebox-foundry/releases) · [Agent setup](docs/AGENT-SETUP.md) · [Changelog](CHANGELOG.md)

## Give your coding agent a head start

Ask an agent to use Foundry to generate a starting asset, then continue together in Blender or another 3D editor.

- **The MCP gives the agent tools.** Discover workflows and settings, submit jobs, follow progress, inspect previews and retrieve exports through the same services as the GUI.
- **The companion skill provides guidance.** It helps the agent choose a workflow, respect inputs and memory limits, review results and bring an asset into the next tool.
- **Generation runs locally.** The agent can work on independent tasks while Foundry processes a job. People can review results in the wizard and continue from the same saved work.

Our aim is to reduce repetitive modeling and save time and agent tokens. Actual savings depend on the asset, workflow and amount of finishing required. Start with the [MCP and companion skill guide](docs/AGENT-SETUP.md). The skill is a growing foundation, informed by real projects and community feedback.

## Choose a workflow

| Workflow | What you get | When to choose it |
| --- | --- | --- |
| **Single Image or Text** | One image through Pixal3D geometry, Hi3D refinement, cleanup, TRELLIS.2 texturing and selected exports. Create the image from text inside the wizard if needed. | The most direct mesh workflow, with fewer stages and models. Try a clear three-quarter reference. |
| **Turnaround** | Generate and review four views with supported Qwen or FLUX models, then reconstruct with Pixal3D and finish with Hi3D and TRELLIS.2. | Humanoids are a strong starting point. Vehicle, prop and creature recipes are still being improved. |
| **3D-Guided** | A Pixal3D proxy, measured Blender views, MoGe 2 estimates and Qwen guidance before reconstruction and finishing. | Objects where choosing and checking camera views matters. More processing is involved. |
| **Splat & Solid** | An Idol Gaussian splat from Sperid Labs, plus separate cleaned companion geometry and optional Hi3D refinement. | Rich appearance alongside lighter geometry, with orbit previews and mesh comparisons. |
| **CCORE Text** | A procedural stylized prop described in words, 12 editable examples, optional local Qwen description enhancement, a 3D preview and GLB export. | Tools, furniture and individual game props. |
| **CCORE Image + Text** | One image and a description through CCORE's vision projector and generation path. Create a reference inside the wizard if needed. | Keep or change features from a photo, sketch or render. |
| **HairDeck** | Hair cards, variations, processing sheets, fitting, materials, optional spring chains, motion preview and selected GLB/VRM exports. | Clear hairstyle references. Powered by HairDeck and FengLairh's ComfyUI integration. |
| **Garment Particles — experimental** | Clothing generation, author-supported editing, sewing patterns, mesh preparation, experimental Blender draping and character handoff. | Explore clothing designs. Fit and deformation require careful inspection and further work. |
| **Create Images** | Single images or front/back pairs, editing, compatible LoRAs and a saved Gallery. | Prepare a reference for another wizard or keep the image itself. |

Each workflow has its own wizard and independently owned graph section. Cards marked Coming soon describe future work.

## Start creating

1. Install [Pinokio](https://pinokio.co/) and follow the [Foundry install guide](docs/PINOKIO.md) to add this repository.
2. Choose **Install**, then **Start Foundry** and **Open Foundry**.
3. Open **Single Image or Text**. Upload or drop an image, use your webcam, choose from Gallery, or create an image from a description.
4. Review previews and choose outputs. **Rocket Mode** can run the remaining selected stages without optional review stops.

For an existing ComfyUI installation, follow [INSTALL.md](INSTALL.md), then open Mumblebox 3D Asset Foundry.json. Installation prepares software. The selected workflow prepares missing weights before processing on first use. Opening Foundry does not download the whole library. Allow disk space for weights, working files and outputs.

## Review and export

Available outputs depend on the workflow. Wizards expose supported choices such as GLB, FBX, OBJ, BLEND, STL, SPZ, textures, previews and ZIP packages. Detailed and reduced meshes can include UVs and baked maps.

**Editable quads are optional.** Single Image and Turnaround offer QuadriFlow and Instant Meshes on the CPU, or CyberRemesher on NVIDIA CUDA. Their advanced controls and guidance are available in the wizard. CPU spikes during QuadriFlow are normal, and processing can take time. Turning quads off still produces textured triangle assets. GLB previews use triangles, while authoring exports preserve supported quad faces.

Review topology for deformation, geometry for printing and collision, and materials in the target editor or engine. HairDeck's static GLB and spring-bone VRM are different outputs. Its head-turn preview demonstrates hair motion. Garment Particles remains experimental, especially character fitting and draping.

Packages include selected files, a README, measurements, checksums, provenance and applicable notices. Ordinary packages exclude private source images, prompts and working files. History keeps saved results available for review and resuming supported operations.

## Language and accessibility

Choose your interface language in the header or Settings. Switching language updates interface text in place using local catalogs. It preserves entered text, references, previews and running jobs.

Interface language is separate from generation language. Foundry preserves your prompts and model instructions. Check the selected model's guidance when choosing a generation prompt's language.

CCORE’s author recommends English generation prompts. Its built-in examples follow the selected interface language. Use **Translate to English** to translate a description with the local Qwen helper, review it, then generate. Choose Q4 for lower GPU memory use or Q8 for higher numerical precision. Q4 is the recommended starting point; Q8 does not guarantee a better translation. Translation requires the chosen model to fit on the GPU and keeps your text if it cannot. Translation preserves the design; **Enhance description** is a separate creative choice.

Use **Theme** for light or dark appearance. **Font** offers Default, 112%, 125%, 150%, 175% and 200%. Advanced controls stay available as you need them.

## Keep Foundry and the skill current

New versions can bring workflows, repairs and improved agent guidance. Check for updates regularly, especially when returning after a while.

The header reports update status. In Pinokio, let active work finish and use the normal **Update** action. Standalone ComfyUI users follow [INSTALL.md](INSTALL.md).

Updating Foundry updates its bundled skill. **If you copied the skill into your agent's skills directory, refresh that copy too.** App and copied-skill updates are separate steps.

The companion skill tells the agent to read the running app's version and capabilities, check its compatibility record and look for an available update. It should explain observed mismatches or pending updates in your language. Live capabilities remain the authority for the controls actually available.

## Hardware, storage and model terms

This is a **Windows / NVIDIA preview**. The reference machine has an RTX 4080 SUPER with 16 GB VRAM and 64 GB RAM. Requirements vary by workflow. That setup is not a minimum-hardware guarantee. CCORE checks GPU memory and offers supported smaller settings when a requested combination will not fit.

Settings includes installed-model management and a reviewed cache purge. Required published models are prepared again when a workflow needs them. Review listed files before clearing cache or removing weights.

Original Foundry code is **Apache-2.0**. Models, weights and other tools retain their own terms. Read [THIRD-PARTY.md](THIRD-PARTY.md), particularly before commercial use.

## Built together

Foundry gathers and connects useful work from researchers, model authors and workflow creators. Thank you to the people behind Pixal3D, TRELLIS.2, Hi3D, Idol, HairDeck, CCORE, Garment Particles, Qwen, FLUX, MoGe, ComfyUI, Blender and the community integrations.

About includes model credits and a growing contributor Thank You section. Workflow suggestions, bug reports, translation corrections and pull requests are welcome. Help us make useful local workflows easier for others to use.

- [Report a problem or suggest a workflow](https://github.com/mumblebox-gpt/mumblebox-foundry/issues)
- [Agent setup](docs/AGENT-SETUP.md)
- [Localization ownership and contribution guide](docs/LOCALIZATION.md)
- [Dependencies and runtime ownership](dependencies.json)
- [Validation evidence and limits](docs/RELEASE-VALIDATION.md)
- [More Mumblebox projects](https://github.com/mumblebox-gpt?tab=repositories)

The in-app Roadmap lists planned features. Published releases identify the builds available to install.
