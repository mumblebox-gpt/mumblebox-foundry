# Mumblebox 3D Asset Foundry

**Local AI tools for creating 3D assets—with guided steps, useful defaults and room to experiment.**

You don’t need to know ComfyUI or build a node graph. [Install with Pinokio](docs/PINOKIO.md), let the installer set up the software and dependencies, and work in Foundry’s interface. ComfyUI runs underneath; you can open the graphs whenever you want more control.

Foundry brings together work from talented researchers and the open-source community. Our contribution is a practical toolbox: connected workflows, clear choices, previews and saved results.

> **Windows / NVIDIA preview.** Preview **0.1.0-preview.17** includes the Single Image and grounding update. See the [changelog](CHANGELOG.md) and [published downloads](https://github.com/mumblebox-gpt/mumblebox-foundry/releases) for release availability.

## Choose your starting point

| Workflow | What it makes | When to choose it |
| --- | --- | --- |
| **Single Image or Text** | A refined, cleaned and textured mesh from one image. Create that image from text if you need one. Powered by **Pixal3D, Hi3D and TRELLIS.2**. | The simplest, most direct mesh workflow, with fewer stages and models. A clear three-quarter reference is a good start. |
| **Turnaround** | Four generated views, reviewed before reconstruction, refinement and texturing. Uses **Qwen or FLUX, Pixal3D, Hi3D and TRELLIS.2**. | A strong starting point for humanoids. Vehicle, prop and creature recipes are still being improved. |
| **3D-Guided** | A proxy mesh and measured camera views guide reconstruction, followed by refinement and texturing. Uses **Pixal3D, MoGe 2, Qwen, Hi3D and TRELLIS.2**. | Standalone objects where choosing and checking the views matters. More processing; comparative quality is still being evaluated. |
| **Splat & Solid** | An **Idol** Gaussian splat from **Sperid Labs**, plus cleaned companion geometry and optional Hi3D refinement. | Detailed splat appearance with separate lightweight geometry. Includes orbit previews and mesh comparisons. |
| **HairDeck Stylized Hair** | Editable stylized hair cards, materials and optional spring-bone VRM exports. Powered by **HairDeck**, with **FengLairh’s ComfyUI integration**. | Create and fit a hairstyle from a clear reference. Review variations, processing sheets, chains, materials and a head-turn preview. |
| **Create Images** | Single images or front/back reference pairs, with editing, compatible LoRAs and a saved Gallery. Uses supported **Qwen and Black Forest Labs** models. | Make a reference, experiment with an idea, or create images without continuing into 3D. |

Each method has its own wizard and independent graph section. Existing workflows remain available. Cards marked **Coming soon**—mesh repair, video, turntable capture and action figures—are future work.

## Get started

1. Install [Pinokio](https://pinokio.co/) and follow the [Foundry installation guide](docs/PINOKIO.md) to add [this repository](https://github.com/mumblebox-gpt/mumblebox-foundry).
2. Choose **Install**, then **Start Foundry**. **Open Foundry** opens the interface inside Pinokio.
3. Start with **Single Image or Text**. Upload or drop one image, take a webcam photo, choose from Gallery, or select **Create Image** to make a reference from a description.
4. Use the recommended defaults, review the mesh, and choose your exports. **Rocket Mode** runs the remaining selected stages without optional review stops.

Already use ComfyUI? Follow [manual installation](INSTALL.md) and open `Mumblebox 3D Asset Foundry.json`. The [agent setup guide](docs/AGENT-SETUP.md) covers the local MCP tools.

The installer prepares software. Missing model weights for your selected workflow are downloaded before processing on first use; opening Foundry alone does not download every model. Keep enough disk space for weights, working files and outputs.

## Review, refine and keep your results

- **Interactive previews:** inspect the initial, refined and finished meshes. Rotate and zoom, switch output versions, and return through History without regenerating.
- **Useful outputs:** detailed and reduced triangle meshes, textures, baking and selected GLB, FBX, OBJ, BLEND or STL formats where supported. The wizard shows the choices available for each method.
- **Floor placement:** Single Image can level a near-upright support pose, place the object on the floor without rotating it, or keep its original orientation. The measured rigid correction is applied after baking to the actual files and final preview. Source checkpoints stay unchanged; automatic placement does not reshape uneven feet or infer the intended pose of every object.
- **Optional editable quads:** Single Image and Turnaround can add quad-preserving authoring files. QuadriFlow runs on the **CPU**: high CPU use is normal and it can take several minutes. Turning quads off still produces textured triangle assets. GLB previews triangulate quads; they do not preserve editable quad faces.
- **Honest geometry checks:** cleanup and export reports describe the actual mesh. An editable quad result is a starting point, not a promise of animation-ready edge flow. When QuadriFlow opens an already closed component, a reported topology-preserving fallback can retain closure. Printing and collision still need checks for their intended use.
- **Saved packages:** selected files, measurements, a readable README, checksums and model/tool credits. Source images, prompts and private working files are kept out of the ordinary asset package.

HairDeck creates stylized volumetric hair cards—not strand Groom or a complete character rig. Static GLB and spring-bone VRM are separate export choices. Its head-turn video demonstrates hair motion; it does not animate a complete character. HairDeck software is installed with Foundry; its weights and selected export tools are prepared when that workflow needs them.

## Make the interface comfortable

Choose a light or dark **Theme**, or use **Font** beside it for **Default, 112%, 125%, 150%, 175% or 200%** text. Controls reflow as text grows. Advanced settings stay available without crowding the normal path.

**Settings → Purge Cache** first shows temporary files, unfinished downloads and their sizes. Choose categories and confirm before clearing. Saved assets, references, models and settings are protected; clearing waits until processing and downloads finish. Installed-model management is a separate control for deliberately removing weights. Required published models are prepared again when their workflow needs them.

The header shows **Up to date**, **Update available**, or an honest check status. It checks published releases, not unpublished Git changes. Open the update details for the supported installation route. In Pinokio, finish any work, stop Foundry, then choose **Update** in the sidebar. Updates preserve saved assets, settings and models.

## Hardware and model terms

The reference machine is **Windows, NVIDIA RTX 4080 SUPER with 16 GB VRAM, and 64 GB RAM**. This is not an 8 GB compatibility claim. Workflows can use CPU offloading and substantial system RAM; lower-memory profiles are still being evaluated.

Original Foundry code is **Apache-2.0**. Models, weights and third-party tools retain their own terms. Read [third-party notices](THIRD-PARTY.md), especially before commercial use. Public defaults use pinned acquisition sources; optional access-gated alternatives may require their own accounts, tokens and terms.

## Built with the community

Thank you to the researchers behind **Pixal3D, TRELLIS.2, Hi3D, Idol, HairDeck, Qwen, FLUX and MoGe**, and to **ComfyUI, Blender, Meta and the community integrations** that make these workflows possible. Powered by [Hi3D](http://hi3d.ai/).

Foundry’s **About** tab includes model credits and a growing contributor Thank You section. Useful workflow suggestions, clear bug reports and pull requests are welcome. We’re building a collection of practical local tools and learning together.

- [Report a problem or suggest a workflow](https://github.com/mumblebox-gpt/mumblebox-foundry/issues)
- The **Roadmap** tab in Foundry lists planned workflows and improvements
- [Install and update guide](docs/PINOKIO.md)
- [Dependencies and runtime ownership](dependencies.json)
- [Validation evidence and limits](docs/RELEASE-VALIDATION.md)
- [More Mumblebox projects](https://github.com/mumblebox-gpt?tab=repositories)
