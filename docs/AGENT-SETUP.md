# Foundry MCP

The companion MCP uses the same local HTTP services as the wizard. It does not load GPU models, implement another workflow engine, or require an agent to manipulate individual graph nodes.

## Agent quick start

In the Foundry header or Integrations, open **Connect your agent** and select any Blender skill repositories you want. Copy the setup prompt into your coding agent to register the local MCP and install the companion skill. After setup, ask your agent to use Foundry when you need it.

Install the bundled [Mumblebox Assets skill](../comfyui_asset_workshop/skills/mumblebox-assets/SKILL.md) by copying its folder into your agent's skills directory. It explains when to run local asset generation and how to bring an export into Blender.

1. Start Foundry and connect the MCP using the instructions below.
2. Call `foundry_workflows` for the available groups and again with a group to get its actions, accepted path/query parameters and body fields. Call `foundry_workflow_action` with action `capabilities` for current models, settings and export options.
3. Import only authorized inputs. For CCORE Image + Text set `target` to `ccore` when importing a local image. For Garment drape, use `foundry_garment_upload_character` on a sewn run and pass the returned ID into drape.
4. Save or start the run using its documented action. For 3D-Guided, call `show` on the saved run first and check `bound`. You can inspect its graph without starting generation.
5. Follow progress using the group's `status`. Use `show` to open the result in Foundry and the file or package actions to obtain local download URLs. For a saved PNG, JPEG or WebP, `foundry_read_image_preview` returns actual pixels for the agent to review.

The groups are `mesh` (Single Image and Turnaround), `guided`, `virtual_turntable`, `orbit_to_mesh`, `splat`, `hair`, `ccore` (Text and Image + Text), `garment`, `images`, and `workspace`. Workspace includes the packaged graph, History, preferences, model management, integration and maintenance controls. Model and file removal use the same preview tokens as the GUI and require the user's authorization for the listed items.

## Keep the app and companion skill aligned

At connection time, read `workspace.agent_connection` for the app version, bundled skill path and revision, and update status. Foundry runs the check through its normal release checker and update preference. Older installs expose `workspace.bootstrap` and `workspace.update_status`. The skill's compatibility.json records its reviewed app version and protocol. A copied skill can lag behind an app update, so refresh both when appropriate.

The agent should explain observed mismatches and available updates in the user's language, use live capabilities for current controls and avoid repeatedly interrupting an unchanged session. Interface language does not translate generation prompts.

## HairDeck workflow

Use `foundry_hair_capabilities` before configuring hair. Import an authorized local image with `foundry_import_reference`, then pass its `filename` as the hair configuration's `image`. `foundry_hair_create` saves options without downloading or generating. Start `generate`, inspect saved variations with `foundry_hair_status`, and select a variation for `preview`, `motion_preview` or `export` with `foundry_hair_start`. The material and export operations reuse saved card/chain data. Reuse a request ID only for retries of the same operation. Cancel/show tools use the same owner and existing visible Foundry wizard. Static GLB is unrigged; VRM 0.x contains skinning and spring groups. The motion output is a video preview, not an animation clip.

## Install

**Pinokio installation:** Start Foundry, then copy the `mumblebox-foundry` entry from `<Pinokio home>/api/mumblebox-foundry/.pinokio/mcp.json` into your agent's MCP configuration. The launcher installs the SDK and generates this entry with the actual local paths. Its `connect_agent.py` wrapper reads the current runtime address on each connection, so ports are not hard-coded. It permits local reference imports only from this installation's `.pinokio/data/input` folder. Add additional explicit input roots only when authorized. Keep Foundry open inside Pinokio so generated work is available for review.

**Existing ComfyUI installation:**

Create a small separate Python environment and install `comfyui_asset_workshop/agent/requirements.txt` (mcp==2.3.0). Start ComfyUI with the Foundry package and open the Foundry graph before using the tools.

Example MCP client configuration; replace every example path with your installation:

```json
{
  "mcpServers": {
    "mumblebox-foundry": {
      "command": "C:\\Tools\\foundry-agent\\Scripts\\python.exe",
      "args": [
        "C:\\Tools\\ComfyUI\\custom_nodes\\comfyui_asset_workshop\\agent\\foundry_server.py",
        "--comfy-url", "http://127.0.0.1:8188",
        "--input-root", "C:\\Assets\\References"
      ]
    }
  }
}
```

Repeat `--input-root` or use `--input-file` to authorize specific reference inputs. No local input paths are allowed by default. Keep the ComfyUI service local; this is not an internet-facing authenticated service.

## Tools

- `foundry_capabilities`: exact models, categories, defaults and export selections.
- `foundry_import_reference`: imports an allowed reference without modifying its source.
- `foundry_create_run` / `foundry_update_run`: configuration only.
- `foundry_start`: turnaround, mesh, finish or rocket.
- `foundry_run_status`: stage, progress, downloads, outputs and errors. The `progress` object lists selected stages, completed stages, the current stage and a fraction based on completed stages, not elapsed time. It includes packaging and final cleanup; only a completed run reaches 100%.
- `foundry_cancel`: cancels the selected job while retaining completed checkpoints.
- `foundry_show_run`: updates the already-open interface without taking OS focus.
- `foundry_package`: finished package metadata and local download URL.

Read capabilities first; do not invent identifiers or format combinations. Label the overall reference primary and describe extra images' purposes. Use a unique request_id for an intentional start; reuse the same request_id and payload when retrying an uncertain request. Poll at sensible intervals. A disconnected MCP client does not cancel a backend job.

Model licenses vary. A successful file export is not proof of animation suitability or physical printability. Inspection tools such as Blender remain useful for reviewing the actual result.

## Splat & Solid

`foundry_splat_capabilities`, `foundry_splat_create`, `foundry_splat_status`, `foundry_splat_start`, `foundry_splat_cancel` and `foundry_splat_show` use the same durable run owner as the wizard. Import a reference first; pass its returned filename as `image`. Start `generation`, `cleanup`, `export` or `rocket` with a unique `request_id`; reuse it only for the same retry. Cleanup reuses unchanged saved stages. Selected models are prepared before processing. Show opens the asset in the existing Foundry interface. SPZ stores appearance; GLB stores separate polygon geometry.

## Image creation and Gallery

The image tools use a separate workflow in the same open graph. They share the interface's job runner, revisions and resource management.

- `foundry_image_capabilities`: supported image models, categories, reference limits, defaults and license information.
- `foundry_image_create` / `foundry_image_update`: configure a creation with `name`, `category`, `model`, `description`, optional `front`, `back`, `references`, `settings`, `checkpoint` and `loras`.
- `foundry_image_start`: `generate` resumes unchanged completed stages; `regenerate` intentionally makes a new variation; `edit` runs a prepared selection. Use a unique request identity for each intentional operation.
- `foundry_image_status` / `foundry_image_cancel` / `foundry_image_show`: inspect, cancel or display the creation in the existing interface.
- `foundry_image_prepare_edit`: supply an authorized PNG mask (white selects, black preserves), source revision, side and description. The tool does not generate until `start` is called.
- `foundry_image_accept`: explicitly accept a reviewed candidate or restore a retained revision. Supply the expected current revision to prevent stale overwrites.
- `foundry_image_save`: add the accepted set to Gallery and obtain its image ZIP URL.
- `foundry_image_handoff`: copy accepted front/back images to 3D inputs. Merge the returned name, category, references and `image_creation` receipt into a new 3D configuration. The receipt preserves verified image-model provenance in its eventual export record.
- `foundry_image_gallery`: bounded search, category, single/pair filter and pagination.
- `foundry_image_removal_preview` / `foundry_image_remove`: review exact selected creations and apply a confirmation token only for the scope authorized by the user. Entry removal keeps files by default. Deleting files requires separate explicit authorization.

Asset categories generate the front first and use it as the rear reference. Background and General Image produce one standalone image and do not expose a 3D handoff. Accepting a local edit preserves pixels outside its mask and the other view; visually review consistency before continuing. The image ZIP includes accepted PNGs, a root README and sanitized generation metadata, without source uploads, private prompts or local paths.
