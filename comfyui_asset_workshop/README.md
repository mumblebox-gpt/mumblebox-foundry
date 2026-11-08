# Mumblebox 3D Asset Foundry — ComfyUI node pack

This folder contains the Foundry interface, independent workflow branches and shared runtime services. For current features and installation, read the [product README](../README.md), [installation guide](../INSTALL.md) and [validation notes](../docs/RELEASE-VALIDATION.md).

Open **Mumblebox 3D Asset Foundry.json** for the current GUI. Single Image or Text is the direct one-image route; Turnaround, 3D-Guided, Splat & Solid and HairDeck retain separate owners. The older Asset Workshop graph and the technical notes below describe the original node interface.

---

# Asset Workshop for ComfyUI

A staged workflow inside the existing ComfyUI canvas:
design → review individual views → prepare → reconstruct → textured master → game export.

**Build status:** installed files and graph contracts checked; live model execution,
memory behavior and export quality still require verification after Comfy restarts.
Do not present this build as a proven one-click release yet.

## Install / open

Copy this entire folder into `ComfyUI/custom_nodes/comfyui_asset_workshop`, restart
ComfyUI, then open `workflows/Asset Workshop.json`. Use a recent ComfyUI version
with the native Qwen 2.1, FLUX 3, Pixal3D and TRELLIS.2 nodes. The exact development
host is recorded in `compatibility.json`; other hosts still need verification.
No other local custom-node pack is required by these recipes.

Use the buttons inside the Asset Workshop node. The ordinary Comfy Run button
runs only the native stage currently displayed beside the controls. An image
stage never contains a mesh output. View sequences submit one image job at a
time and stop on failure; they never accept images or start a mesh automatically.

Model choices are additive: Qwen Image 2.1, Qwen Image Edit 2511, FLUX.2 Klein 9B
base/distilled/KV, and FLUX 3 Image Klein base/distilled. Each retains its own
encoder, VAE and sampling recipe. Qwen Edit 2511 requires an image.

Use **Download missing models** for the selected image profile and **Download
missing 3D models** under Mesh. Models download only when requested. The dialog
shows sizes and source/license links. Files are pinned by revision and SHA-256
in `models.lock.json`; existing conflicting files are never overwritten. Gated
models require the user's own Hugging Face access. No tokens are saved in the
workflow or asset manifest. Download partials are owned by this extension and
resume from `.asset-workshop-downloads` inside the destination model folder.

## References and camera views

Add ingredient images and describe each one's role. Generate or import a design,
then accept it. **Generate missing views** fills enabled empty cards sequentially.
Each card also supports its own correction, upload, acceptance and revision revert.
Corrections use the selected model and preserve the other cards' saved images.

Use the camera LoRA checkbox and **Adapt angles** before generation. Qwen 2.1 has
30-degree orbit labels and no trained negative-elevation view. Its lower-rear
card becomes upper-rear coverage. Qwen 2511 uses 45-degree orbit labels and
supports a low-angle view. The FLUX 3 camera adapter targets base only; the Klein
camera adapter follows the published KV graph. Their results require review.
Generated camera positions are always recorded as estimates.

Qwen 2.1 and FLUX 3 recipes have ten reference slots; native Qwen 2511 has three.
The Klein graph supports up to 100 connections, **not a promise of useful quality
with 100 references**. Edit source and approved design count against the limit.
Nothing is silently dropped. All enabled accepted Pixal views reach one multiview
conditioning call. The single-image Pixal and TRELLIS routes use the design only.

## Saved assets

The default library is `<Comfy output>/AssetWorkshop`. Resources allows another
absolute local library path. Changing that path does not move or delete assets.

```
AssetWorkshop/
  assets/<asset-id>/
    asset.json
    references/
    images/design/<revision>.png
    images/view_01/<revision>.png
    prepared/
    jobs/                         # small saved stage settings for resume
    masters/<master-id>/           # mesh fields + native voxel data, safetensors
    exports/master/<export-id>/   # detailed GLB + separate PBR maps
    exports/game/<export-id>/     # reduced GLB + separate PBR maps
  work-cache/<job-id>/            # owned disposable stage files
```

The native checkpoint is saved before optional cleanup. Build the textured master,
review it, and accept it before game export. Each export has its own folder and
hash manifest. GLB uses Y-up, meters, a ground-center pivot and OpenGL normal maps.
For Unreal, configure/convert the normal-map green channel as appropriate to its
import settings. A reduced mesh is not automatically rigged or deformation-ready.

## Memory and cleanup

One Comfy execution at a time. Qwen 2.1 prefix cache defaults to CPU with original
precision. Image VAE decoding is tiled by default. Selected-stage graphs avoid
loading image and reconstruction models together. Native Comfy offloading remains
responsible for model residency.

The extra-headroom control raises the selected diffusion model clone's sampler
memory estimate. It is not a strict process cap and does not change text-encoder,
VAE or host startup memory policy. Resources displays the host's existing reserve.
It also displays active versus requested `--vram-headroom`; a recorded request
must be applied in the launcher's settings and activated by a deliberate restart.
BF16 image-model options are explicit; precision is never lowered automatically.

Cancellation targets only the asset's recorded prompt ID. Completed job-owned
temporary files are cleaned automatically. Failed/cancelled jobs can be resumed
with saved settings. Cleanup never deletes source images, revisions, native
masters, exports, shared caches, model files or another app's data.

Optional geometry-guided cameras (AnyAngle), UltraTex/retexturing and other
research candidates remain future integrations pending compatibility and memory
verification. This package does not install Pinokio, rig a character, modify
SwarmUI, restart a backend, or redistribute model weights.
