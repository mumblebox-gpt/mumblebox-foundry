# Single Image: official recipe and integration

## Sources checked
- [Comfy official guide](https://github.com/Comfy-Org/docs/blob/main/tutorials/3d/pixal3d.mdx).
- [Official template](https://github.com/Comfy-Org/workflow_templates/blob/ea7faae6999fb31338f43408ff4a575bd3f7d9a0/templates/3d_pixal3d_trellis2_image_to_model.json), archived unchanged in `foundry/workflows/single_image/sources/official.json`.
- Installed Comfy object_info and core at the revision in dependencies.json; our existing image_to_3d stage compiler, runner, cleanup and export catalog.
- [Tencent ARC Pixal3D](https://github.com/TencentARC/Pixal3D), [Comfy model conversion](https://huggingface.co/Comfy-Org/Pixal3D). Model access/license/revision/hash are governed by the existing root models.lock.json, not a second download list.

## Exact path
Official default false switch selects pixal3d_int8_convrot, Pixal3DConditioning, DINOv3 L, per-image horizontal FoV from MoGe 2. BiRefNet mask feeds ImageCropToMask at 1024 square, 1.1 padding, black background. Structure (12 steps), low-res shape (20), high-res shape (12) use the published CFG override/rescale/SD3 shift. Save the VaeDecodeShapeTrellis mesh before any texture ancestry. The alternative TRELLIS.2 conditioning/diffusion branch is unused and must not download/load by default. The template default 1536 upsample is exposed; local starting default 1024 reduces memory, with the official 1536 choice available. MoGe batch 1 is equivalent for one input and bounds memory.

## Local precision qualification
The installed runtime and existing signed model catalog use the pinned original `pixal3d_bf16.safetensors`, not the newer template INT8 conversion. The single-image model is the correct architecture (not multiview). Preserve this already-qualified precision/checkpoint, official conditioning/sampler recipe and core memory offloading; do not introduce an unpinned conversion just for the UI feature. The reference template remains archived unchanged.

## Finishing and dependencies
Our pinned Hi3D service accepts an untextured mesh and original reference; retain its 4.5M-face intake limit and current measured cleanup. Texture final cleaned geometry using the already qualified TRELLIS.2 worker, then UV/rebake reduced/quad versions and package selected formats. This deliberately moves template texturing after refinement so its texture is not discarded. Existing acquisition owner verifies pixal_single, shape_vae, dino, moge2, birefnet, Hi3D and selected texture worker models before inference. No Qwen/FLUX, multiview diffusion or guided-camera rendering is part of this method.

## UI decisions already approved
Separate grouped branch and wizard; one reference, upload/camera/Gallery/Create Image; three-quarter recommended, no text prompt passed to Pixal3D. First/default method with brief honest simplest/direct wording, existing output selections and Rocket continuation. Shared runner/finishing services, independent recipe/state/IDs. Preserve all existing methods and saved results.

## Qualification
Source/schema proof is research only. Completion still requires a new end-to-end GUI run, actual visible initial/refined/final previews, selected exports and resume, followed by the agreed full-app typography/layout/artwork audit and one additional improvement. Local only; no Git writes or installed Pinokio changes.
