# Licenses and acknowledgments

Original Mumblebox 3D Asset Foundry code is licensed under [Apache-2.0](LICENSE). This does not relicense any model, third-party source, dependency, or input/output artwork.

The resource inventory and retained notices are in:
- `comfyui_asset_workshop/finishing/package_resources.json`
- `comfyui_asset_workshop/licenses/`
- `comfyui_asset_workshop/models.lock.json`

Generated asset packages include the resources recorded for the stages actually used, their source/license links and relevant notices. Model choice can change those terms. The application's Apache license is not a statement that every selectable model permits commercial use.

Image ZIPs record the selected image model, checkpoint and LoRAs for each accepted image. Sending a pair to the 3D wizard carries those records into the mesh package's production record. An external resource with missing license metadata is identified by its source when available; Foundry does not infer permission from an absent record. Original uploads, private prompts and model weights are not included in the image ZIP.

Key dependencies include ComfyUI (GPL-3.0), Blender (GPL-3.0), Pixal3D (MIT), TRELLIS.2 (MIT), QuadriFlow (MIT), PyMeshLab (GPL-3.0), MeshLib (its own terms), DINOv3 (its own model terms), and Hi3D (Hi3D Open License 1). Qwen Image 2.1 uses the retained Qwen Research License; this application does not grant commercial authorization. Other Qwen/FLUX/Klein choices have their own displayed licenses.

The Hi3D client bridge is adapted from the T8 workbench. Its MIT notice is retained in `comfyui_asset_workshop/licenses/Hi3D-Workbench-MIT.txt`. Downloaded worker software remains upstream software with its own notices. The public package does not redistribute model weights.

The texture worker downloads DINOv3 from https://huggingface.co/visualbruno/dinov3-vitl16-pretrain-lvd1689m at revision `8463e34549282813c2cbf67241b27c6fe8fa6321`, following the existing ComfyUI-Trellis2 download source. The three files retain the original expected SHA-256 hashes in `models.lock.json`; only their acquisition source changed. Public download availability does not replace the DINOv3 license, retained in `licenses/pipeline/DINOv3-LICENSE.md` inside the custom-node package. Export metadata records the acquisition repository, revision and hashes.

Powered by Hi3D 1.0 - http://hi3d.ai/

Hair creation uses FengLairh/ComfyUI-HairDeck at `ad27f3433169ca6e1f61396525d30d6ca55428be`, which vendors HairDeck at `5f1c18a32e622cb8d1acec2a856694fb43375c1a`. Both declare Apache-2.0 for their own code. SAM 3 and DINOv3 retain their Meta licenses; BiRefNet and pyrender retain their own notices. The node pack keeps these notices. Hair asset packages copy them and record the actual selected model hashes. Model weights are not bundled. First workflow use acquires pinned public model files with SHA-256 verification; rigged output additionally prepares Blender 4.2.23 and VRM Add-on 4.10.2 in a separate tool directory. A static GLB is not a rig; VRM 0.x carries skinning and spring groups. HairDeck does not produce Alembic strand Groom.

Workflow illustrations and the approved product logo were generated/edited for this project. Their role and provenance are described in `comfyui_asset_workshop/web/assets/foundry/ARTWORK.md`. They are interface artwork, not examples proving model output quality.
## Splat & Solid additions

[Idol](https://huggingface.co/speridlabs/idol) is by Sperid Labs. This integration follows the native [Comfy-Org distribution and template](https://huggingface.co/Comfy-Org/Idol), pinned to `3d050f4bc705ca1202a0ae4d21d2d97987521307`. Idol declares Apache-2.0. Meta DINOv3 retains its own license; the FLUX.2 autoencoder is separately Apache-2.0. Model cards and component notices are retained with selected asset packages. ComfyUI contributors provide native splat rendering/extraction, remeshing, decimation and normals. PyMeshLab provides independent exported-file checks. Optional refinement credits Hi3D and its original terms. Public model acquisition does not replace upstream license obligations.

## 3D-Guided additions

The 3D-Guided method uses the same Qwen Image 2.1 resources as the existing method, with the separately pinned [Qwen Image 2.1 Fun ControlNet Union](https://huggingface.co/alibaba-pai/Qwen-Image-2.1-Fun-Controlnet-Union) branch for structural guidance and optional inpainting. Its upstream card identifies Qwen Research licensing; consult the linked terms and retained Qwen notices. [MoGe 2](https://github.com/microsoft/MoGe) estimates the source-image camera; its upstream license text is retained as `comfyui_asset_workshop/licenses/pipeline/MoGe-LICENSE.txt`. Shared model/resource catalogs record the exact selected revisions and hashes. These notices do not assign a license to user-supplied references or generated assets.


### CCORE prop generation

[CCORE GLB-3D-Coder](https://huggingface.co/ccore/Qwen3.5-4B-GLB-3D-Coder) releases the selected checkpoint under Apache-2.0 and credits [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B). Image + Text uses the [published BF16 vision projector](https://huggingface.co/ccore/Qwen3.5-4B-GLB-3D-Coder#weights-and-release-status), the original Qwen3.5-4B encoder and projector distributed by the LM Studio community under Apache-2.0. Foundry uses [llama.cpp b11160](https://github.com/ggml-org/llama.cpp/releases/tag/b11160) and the bundled [Three.js r165](https://github.com/mrdoob/three.js/tree/r165), both MIT. The isolated exporter runs [Playwright 1.64.1](https://github.com/microsoft/playwright-python/tree/v1.64.1) (Apache-2.0) and its managed Chromium shell, whose distribution retains its own notices. The workflow does not redistribute model weights. Foundry's ZIP retains the applicable workflow notices separately from the generated prop.
