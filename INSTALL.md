# Install Mumblebox 3D Asset Foundry

For an isolated installation managed by Pinokio, use [the Pinokio instructions](docs/PINOKIO.md). The steps below are for adding Foundry to an existing ComfyUI installation.

This preview runs locally on Windows with an NVIDIA GPU. It uses three Python environments: the existing ComfyUI host, an isolated texture/finishing worker, and a local Hi3D workbench. Keep their PyTorch installations separate. All example paths below are examples, not required machine paths.

Use a local directory outside OneDrive. Install Git, [uv](https://docs.astral.sh/uv/getting-started/installation/) (available on PATH), Python 3.13, Python 3.10, a current NVIDIA driver, and Blender 5.2.2 LTS. The validated system has 16 GB VRAM and 64 GB RAM; lower-memory machines are not yet qualified.

## 1. ComfyUI

Use a recent ComfyUI with native Qwen Image 2.1 and Pixal3D multiview support. The reference core revision is `483dae4326356b81de05d27aca3f433dd323cc25` (core 0.42.5), with frontend `1.59.0.dev2`. An older installation missing these nodes must be updated before loading the workflow. Comfy Desktop and a separately installed ComfyUI both work with the node package; use the actual core directory containing `folder_paths.py` and `custom_nodes`.

Extract this release into a separate folder, for example `C:\Tools\foundry-release`. Install the lightweight host dependencies using **ComfyUI's own Python**:

```powershell
& 'C:\Tools\ComfyUI\.venv\Scripts\python.exe' -m pip install -r 'C:\Tools\foundry-release\comfyui_asset_workshop\requirements.txt'
```

Do not install a second copy of old Foundry/Hi3D wrappers that register the same node names. This package owns its Hi3D bridge and finishing nodes. Native Qwen nodes are supplied by ComfyUI; QwenUnionT8 is not required.

## 2. Isolated texture and finishing worker

Clone the tested TRELLIS.2 wrapper and create a separate Python 3.13 environment:

```powershell
git clone https://github.com/visualbruno/ComfyUI-Trellis2.git C:\Tools\foundry-trellis
git -C C:\Tools\foundry-trellis checkout b0e84c0f29857a444e8bcb5b9be2ea218e96efd0
py -3.13 -m venv C:\Tools\foundry-worker
& 'C:\Tools\foundry-worker\Scripts\python.exe' -m pip install --upgrade pip
& 'C:\Tools\foundry-worker\Scripts\python.exe' -m pip install torch==2.10.0+cu130 torchvision==0.25.0+cu130 --index-url https://download.pytorch.org/whl/cu130
& 'C:\Tools\foundry-worker\Scripts\python.exe' -m pip install -r 'C:\Tools\foundry-release\requirements-worker-windows.txt'
```

Install the five **cp313 / win_amd64** wheels from the checked-out wrapper's `wheels/Windows/Torch2100/CUDA 13.1` directory: cumesh, flex_gemm, nvdiffrast, nvdiffrec_render and o_voxel. Use that directory's exact wheel filenames:

```powershell
$wheelFolder = 'C:\Tools\foundry-trellis\wheels\Windows\Torch2100\CUDA 13.1'
foreach ($package in @('cumesh','flex_gemm','nvdiffrast','nvdiffrec_render','o_voxel')) {
    $wheel = @(Get-ChildItem -LiteralPath $wheelFolder -Filter "$package-*-cp313-cp313-win_amd64.whl")
    if ($wheel.Count -ne 1) { throw "Expected one matching wheel for $package" }
    & 'C:\Tools\foundry-worker\Scripts\python.exe' -m pip install $wheel[0].FullName
    if ($LASTEXITCODE -ne 0) { throw 'Worker wheel installation failed' }
}
New-Item -ItemType Directory -Force C:\Tools\foundry-texture-models
```

The wrapper source is used by the isolated worker; do not install it as another active ComfyUI custom-node pack. No model weights need to be downloaded at this point. The texture stage obtains its pinned snapshots on first use. The default DINOv3 acquisition uses the documented public distribution with checksum verification; it does not depend on Meta's Hugging Face approval queue. Alternate resources can have separate access requirements.

## 3. Hi3D workbench

This preview integrates the local [T8 Hi3D workbench](https://github.com/T8mars/Comfyui-Hi3d-T8). It provides the service used by Foundry's bridge. Setup installs code/dependencies, not models unless explicitly requested.

```powershell
git clone https://github.com/T8mars/Comfyui-Hi3d-T8.git C:\Tools\foundry-hi3d
git -C C:\Tools\foundry-hi3d checkout dd5776d720974ca7a4b7a185415be4259da5a50d
& 'C:\Tools\foundry-hi3d\scripts\Setup.ps1' -Python 'C:\Path\To\Python310\python.exe'
```

**Omit `-DownloadModels`.** Foundry requests the workbench's pinned model download when refinement is first used. Start the service before running refinement:

```powershell
Set-Location C:\Tools\foundry-hi3d
& '.\.venv\Scripts\python.exe' -m hi3d_workbench --port 8378
```

Keep it running. It listens on the local computer. The pinned workbench has no model-download cancel endpoint: cancelling a Foundry job prevents refinement submission but an already-started Hi3D model download continues in that service. Completed model files are reused.

## 4. Install Foundry and configure paths

Run the release installer with your actual paths:

```powershell
py -3.13 C:\Tools\foundry-release\scripts\install_foundry.py `
  --comfy C:\Tools\ComfyUI `
  --worker-python C:\Tools\foundry-worker\Scripts\python.exe `
  --trellis-repo C:\Tools\foundry-trellis `
  --trellis-models C:\Tools\foundry-texture-models `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
```

If ComfyUI uses a custom `--user-directory`, pass the same directory to this installer. If its interpreter is not at `<core>/.venv/Scripts/python.exe`, also pass `--host-python` with ComfyUI's actual Python executable. The installer copies the node package, installs and probes the pinned HairDeck software in the host, and writes private paths to `user/asset-workshop.json`. Existing settings and changed installation files are backed up under `user/mumblebox-foundry/install-backups`. It does not remove models, user outputs or other custom nodes.

HairDeck weights download when its workflow is first run. Its separate Blender 4.2/VRM export tools download on first use of rigged output or motion; they do not replace Blender 5.2. See [HairDeck workflow and limitations](docs/HAIR-WORKFLOW.md).

Restart ComfyUI, then open:

`custom_nodes/comfyui_asset_workshop/workflows/Mumblebox 3D Asset Foundry.json`

The interface appears in the same graph as the pipeline. Expand **Create a Mesh from an Image** and choose **Turnaround** or **3D-Guided**. Each method has its own wizard and processing branch. The graph has empty input fields; no sample assets or saved production sessions are bundled.

3D-Guided uses Blender for measured views and requires the pinned core's native `LoadMoGeModel`, `MoGeInference`, `TextEncodeQwenImage21` and `ZImageFunControlnet` nodes. The Pinokio installer probes the MoGe model import and render-adapter dependencies. The method uses the same configured Blender, worker and Hi3D service as the existing workflow; no Blender MCP add-on or separate experimental repository is required.

## 5. First use and updates

Required resources for the selected workflow are prepared before generation. The interface shows first-use messages and transfer progress. Native models are stored in ComfyUI's model directories; isolated texture snapshots use the configured texture-model directory; Hi3D owns its own model directory. Models are loaded and released by stage. Model weights are downloaded from upstream providers, not from this project's GitHub archive or another user's PC.

Enter a Hugging Face token in Settings for gated resources. For Civitai downloads, the browser's API-key help links to the account settings and explains where to paste the key. Downloaded Civitai resources are for initial image creation only.

Foundry checks its GitHub Releases feed if automatic checking is enabled. **Check for updates** is also in Settings. Download a new release from GitHub and rerun the installer while ComfyUI is stopped. The checker does not execute downloaded code or overwrite a workflow.

For an update rollback, stop ComfyUI and restore the changed files/config listed in the corresponding install-backup directory. Keep your input/output/model directories.

## Troubleshooting

- **Missing native nodes:** compare your ComfyUI revision with dependencies.json; update ComfyUI rather than installing unrelated nodes.
- **Missing Interface:** verify this package loaded without import errors, then reload the ComfyUI frontend after restart.
- **Hi3D unavailable:** start its local service and check http://127.0.0.1:8378 before retrying.
- **Texture worker import failure:** check the isolated Python version, PyTorch build and matching cp313 wheels. Do not replace the host's PyTorch.
- **Model hash mismatch:** Foundry preserves the existing file and reports it. Resolve that specific file; do not delete the whole model directory.
- **Out of memory:** retry with lower detail/export choices. Only Default is configured; other memory profiles are not active yet.
