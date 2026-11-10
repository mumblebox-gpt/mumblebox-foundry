# Foundry in Pinokio

This Windows/NVIDIA beta installs an isolated copy of ComfyUI, Foundry, the Hi3D service, the texture/finishing worker, Blender and the companion MCP. It opens the Foundry interface inside Pinokio. Existing ComfyUI installations are not replaced.

## Community workflows and contributions

Foundry is a growing toolbox of local image and 3D workflows, shaped by practical use, learning and community contributions. The aim is to bring together the best practical local approaches and make them easier to use through guided wizards and automatic software setup. Credit stays with the researchers, model authors and workflow contributors whose work makes it possible.

Have a workflow that produces great results locally? Share it through [GitHub Issues](https://github.com/mumblebox-gpt/mumblebox-foundry/issues). [Pull requests](https://github.com/mumblebox-gpt/mumblebox-foundry/pulls) for workflow integrations, improvements and fixes are welcome. Include the workflow, example results, required models and hardware, and relevant license information so we can evaluate and credit it properly.

## Install and open

1. Install Pinokio from https://pinokio.co/ and complete its software prerequisites.
2. Use Pinokio's repository-URL installation option with `https://github.com/mumblebox-gpt/mumblebox-foundry`.
3. Select **Install**. The first software installation downloads several environments and native libraries; keep its log open if you want to follow progress.
4. Select **Start Foundry**. **Open Foundry** opens the interface in the Pinokio application pane. It does not require Chrome.
5. Choose an image workflow, or supply reference images in **Open Wizard**.

The reference system is Windows with an NVIDIA RTX 4080 SUPER, 16 GB VRAM and 64 GB system RAM. This is not an independently tested 8 GB compatibility claim. Keep the installation outside OneDrive and other synchronized directories. See `dependencies.json` for pinned software versions and `RELEASE-VALIDATION.md` for evidence and limitations.

## Models and access

Installation and startup do not download generation models. When a workflow is first run, Foundry prepares the missing model files needed for its selected stages before generation begins. Completed downloads are reused. Changing later choices checks any newly required dependencies before proceeding. This preparation downloads files to disk; models load into GPU/system memory only as their stages need them.

The texture worker obtains DINOv3 from the public distribution used by its upstream TRELLIS node, with an immutable revision and verified SHA-256 checksums. That path does not require Meta's Hugging Face repository approval. DINOv3's model license still applies. Other selectable models may require accepted access terms or a Hugging Face token in **Settings**; access errors include a direct model link. Model licenses remain separate from Foundry's Apache-2.0 code license.

Software comes from its published repositories and package hosts. Model weights come from their upstream providers. Neither downloads assets from the developer's PC.

Splat & Solid uses Idol by Sperid Labs through the pinned Comfy-Org native distribution. Its complete selected resources, including optional Hi3D dependencies, are prepared before generation. Settings → Installed models covers registered native and worker locations; deleting a supported model makes that workflow acquire it again before use. The export audit uses the existing finishing environment.

## Stop, restart, update and repair

- **Stop:** use Pinokio's stop control for the running startup script. It stops this installation's owned services. Cancel an active generation first if you want to retain a clean stage checkpoint.
- **Restart:** start Foundry again and select **Open Foundry**. Saved assets, settings, models and history remain in this installation.
- **Update:** select **Update** in the left sidebar, including while Foundry is running. It first checks that no generation is active or queued, stops Foundry, verifies the published GitHub release and installs its pinned software, then restarts. It refuses to overwrite modified launcher source. Saved assets, models and settings are retained.
- **Version checks:** Foundry checks published GitHub versions on startup with a five-minute cache. **Settings → Check for updates** requests a fresh result. An available version displays an update notice. Ordinary source commits become downloadable updates when a release is published; a source push alone is not a release.
- **Repair software:** stop the app and select **Repair software** to rerun dependency setup and reinstall the extension. It retains user assets, downloaded models and settings; it is not a data reset.

Updates save a checkpoint of the previous extension and private configuration. If a staged update fails, those files are restored and startup asks for Repair. Dependency changes are not promised to roll back automatically; do not describe that checkpoint as a full environment snapshot.

Preview.14 brings the complete supported HairDeck review into the wizard: variation cards, processing sheets, head/chain views, material maps, avatar/motion review and official per-card colors. The installer checks the real color entrypoint and explicitly installs its image-color dependency without downloading model weights. After Update, reload an already-open Foundry page to apply the new interface. Older saved graphs acquire only their missing isolated HairDeck branch; saved hair and mesh results remain reusable.

## Files and ownership

Paths below are relative to the Pinokio repository folder:

| Directory | Contents |
| --- | --- |
| `.pinokio/data/input` | Imported reference images and allowed agent inputs |
| `.pinokio/data/output` | Generated images, meshes and exported packages |
| `.pinokio/data/user` | Private settings, workflow state, history and installer backups |
| `.pinokio/software/comfyui/models` | Foundry-managed native image and geometry models; retained during software updates |
| `.pinokio/data/models` | Additional ComfyUI model search directory |
| `.pinokio/data/trellis-models` | Isolated finishing-model snapshots |
| `.pinokio/software/hi3d` | Hi3D's owned service workspace, including its persistent models and job data |
| `.pinokio/envs` and `.pinokio/software` | Managed Python environments and pinned software |
| `logs/pinokio` | ComfyUI and Hi3D service logs |

Do not remove `.pinokio` as a troubleshooting step: it contains your work and model downloads.

## Connect a coding agent

After startup, `.pinokio/mcp.json` contains a ready configuration entry for the installed companion MCP. Copy that entry into the agent client's MCP settings; keep any unrelated servers. See [Agent setup](AGENT-SETUP.md) for the available tools, reference-file permissions and how to add the bundled companion skill. The MCP uses the same workflow services and gallery as the interface.

## If something fails

- **Blank embedded pane:** use the launcher's **Open Foundry** entry. Its `localhost` address matches Pinokio's site and preserves ComfyUI's cross-site protection. Do not disable that protection to fix an address mismatch.
- **Installation interrupted:** retry **Install**. Successful steps are retained; the failed step is retried.
- **Service stopped:** inspect **Startup logs** and `logs/pinokio`, then restart. Foundry chooses available loopback ports on first start and keeps them in `.pinokio/ports.json` so existing pages reconnect after restarts. If another service later occupies a saved port, startup reports it instead of silently stranding the browser at a different address. Stop that conflicting service before restarting.
- **Model access denied:** check that the provider account has accepted the named model's terms, then add the token in Foundry Settings and retry.
- **Local code modified:** preserve those edits before Update. The launcher will not force-reset them.

Report problems at https://github.com/mumblebox-gpt/mumblebox-foundry/issues with the release version and relevant error. Remove private paths, prompts and credentials from any log you share.
