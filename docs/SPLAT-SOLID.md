# Splat & Solid — powered by Idol

Idol by Sperid Labs turns one image into a Gaussian splat. This Foundry method combines its native ComfyUI integration with optional Hi3D refinement and ComfyUI mesh processing. It has its own branch in the shared graph, wizard, saved stages and History records. It does not depend on running Turnaround or 3D-Guided.

## Use it

Expand **Create a Mesh from an Image**, then choose **Splat & Solid**. Upload or drop a clear image with the entire subject visible, use the camera, or choose from Gallery. A three-quarter image can reveal more structure than a head-on view. Hidden surfaces are inferred.

The six pages cover the starting image, generation/output choices, original results, optional refinement and cleanup, paired review, and the finished package. **Rocket Mode** continues the remaining selected stages. Completed unchanged stages are reused; closing the wizard does not cancel processing. Resume returns to its saved asset. An interrupted native stage is recovered when possible; further inference requires an explicit continuation.

The default path uses 262,144 Gaussians, 20 sampling steps, 1024-pixel reference preparation and 512 mesh extraction. Optional Hi3D refinement uses 1536 detail, 25 steps per internal pass and CPU offload. These are the tested lander settings on a 16 GB RTX 4080 SUPER and 64 GB RAM, not a universal memory guarantee. Advanced exposes the actual seeds, sampling, extraction, refinement, cleanup, triangle target and orbit settings.

The detailed cleanup remeshes in a normalized frame at resolution 384, then makes a 20,000-triangle target derivative. A final solid rebuild at 56 can change that exact count. Both meshes return to the splat's frame. Exported canonical geometry is welded; separate crease-normal copies serve display. An independent PyMeshLab/trimesh audit checks closure, winding, finite coordinates, duplicate faces, nonmanifold geometry and self-intersections before publishing the package.

## Inspect and keep

The linked comparison rotates and zooms the master and companion together. Triangle counts, shell counts and recorded checks make the tradeoff visible. Turn linking off for independent inspection; toggle wireframe or reset both views. Smaller geometry can lose antennae, rails and other thin details.

Selected exports can include the SPZ splat, original extracted GLB, closed master, lightweight companion, presentation copies, MP4 orbit and PNG geometry previews. The ZIP includes one readable root README, a catalog, hashes, actual settings and component notices. History retains the saved package. The original splat and checkpoints remain locally preserved even when omitted from the shareable package.

SPZ stores visual appearance. The companion GLB is separate polygon geometry, not a splat/mesh hybrid file or reconstructed PBR texture set. Closed geometry does not certify physical printing or collision behavior in a game engine. No rigging or Hi3D texture generation is implied.

## Installation and model ownership

The pinned ComfyUI core provides Idol/TripoSplat, splat extraction, rendering, remeshing and decimation. The existing finishing worker provides the exported-file audit. No additional mesh-generation model is introduced for cleanup. The installer probes the real native modules and audit imports. Models download on selected-workflow first use, before processing, with pinned hashes; installation and opening the GUI do not download them.

Settings lists registered ComfyUI, Hi3D, TRELLIS, HairDeck and Hugging Face cache locations. Exact-file deletion requires a fresh confirmation and an idle, unloaded runtime. Other hard links may retain disk space. Deleting a cache symlink preserves its shared data. Unknown custom weights need their own retained source; supported workflow dependencies are acquired again before use.

## Original work

- [Idol — Sperid Labs](https://huggingface.co/speridlabs/idol)
- [Comfy-Org distribution and native template](https://huggingface.co/Comfy-Org/Idol), revision `3d050f4bc705ca1202a0ae4d21d2d97987521307`
- [Hi3D](https://github.com/hi3d-official/Hi3Dv1.0), optional image-guided refinement
- [ComfyUI and contributors](https://github.com/Comfy-Org/ComfyUI), native processing and presentation
- Meta DINOv3, Black Forest Labs' FLUX.2 autoencoder and BiRefNet, reference conditioning and preprocessing
- [PyMeshLab](https://github.com/cnr-isti-vclab/PyMeshLab) and trimesh, exported-geometry inspection

Idol declares Apache-2.0; DINOv3 and the other components retain their separate terms. Public model acquisition does not replace license obligations. See [third-party notices](../THIRD-PARTY.md).
