"""Foundry-specific MCP. HTTP owns execution; stdio owns no models or jobs."""
import argparse
import json
from functools import wraps
from typing import Annotated, Any
from urllib.error import URLError
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from client import APIError
from foundry_client import FoundryAPI
from connection import AgentConnection
from tool_contracts import InputPath, LOCAL, READ, RequestId, RunId, START, tool_registration

def checked(function):
    @wraps(function)
    def call(*args,**kwargs):
        try:return function(*args,**kwargs)
        except APIError as error:raise ToolError(json.dumps({"status":error.status,**error.details})) from None
        except URLError:raise ToolError("Could not reach the local Foundry service. Start Foundry and retry.") from None
        except (ValueError,OSError) as error:raise ToolError(str(error)) from None
    return call

def create_server(client):
    connection = AgentConnection(client)
    server=MCPServer("Mumblebox 3D Asset Foundry",version="0.2.0",
        lifespan=connection.lifespan,middleware=[connection.observe],instructions=(
        "Foundry includes the general-purpose Mumblebox Assets companion skill for setup and workflow guidance. "
        "On each connection, read workspace.agent_connection for its local path and revision, the installed app version, and update status. "
        "If checking is true, check back once. Report available updates and refresh an older copied skill from the bundled version. "
        "List workflow groups with foundry_workflows and request one group's actions and capabilities before use. "
        "The catalog exposes Guided, Virtual Turntable, Orbit to Mesh, Orbit with Splats, both CCORE modes, Garment, graph reads and shared workspace controls. "
        "Use current capability defaults unless the user specifies otherwise. "
        "Use the existing ComfyUI Foundry workflow. Read capabilities first. Upload only authorized references, "
        "label the first primary and describe each additional reference's purpose. Select the model, category, "
        "settings and export formats explicitly or use returned defaults. Model licenses vary. "
        "For the simplest path create a run with method=single-image and exactly one reference; start mesh, finish or rocket. Single Image uses the official Comfy Pixal3D single-image recipe, original-reference Hi3D, cleanup and final TRELLIS.2 texturing. For the separate Turnaround method start turnaround, mesh, finish or rocket. "
        "Reuse request_id for retries of the same start; use a new ID for an intentional new operation. "
        "Poll status at sensible intervals; completed checkpoints survive cancellation. "
        "The backend continues if this client disconnects. show_run updates the existing Foundry UI without OS focus. "
        "For initial images use foundry_image_capabilities, create, then start generate. Asset categories produce a front/back pair; general/background produce one image. "
        "Review edits before accepting. Save accepted images; handoff copies a pair and its provenance into 3D inputs. Gallery removal is separate from explicit file deletion. "
        "For hair use foundry_hair_capabilities/create/start/status. HairDeck is a separate hair-card workflow: generate, preview, motion_preview and export. "
        "Static GLB is not rigged; VRM includes skinning and spring data. Inspect previews and package metadata; do not claim animation/print suitability solely from file format."))

    tool = tool_registration(server, checked)

    @tool(READ)
    def foundry_capabilities()->dict[str,Any]:
        """Read supported Single Image and Turnaround inputs, defaults and export choices before saving a mesh run."""
        return client.capabilities()

    @tool(LOCAL)
    def foundry_import_reference(
        path: InputPath,
        role: Annotated[str, Field(description="Reference purpose: primary, back, face, component, style or detail.")] = "primary",
        description: Annotated[str, Field(description="Optional role or detail to preserve in the reference card (up to 800 characters).")] = "",
        target: Annotated[str, Field(description="Empty for the default input folder; ccore for CCORE Image + Text.")] = "",
    )->dict[str,Any]:
        """Copy a PNG, JPEG or WebP into Foundry's local inputs and return its reference card."""
        return client.import_reference(path,role,description,target)

    @tool(LOCAL)
    def foundry_create_run(configuration: Annotated[dict[str,Any], Field(description="Mesh draft with method, name, imported reference cards, category, profile, overrides and export selection.")])->dict[str,Any]:
        """Save a draft and return its run ID. Choose single-image for exactly one reference or turnaround for four-view generation."""
        return client.create_run(configuration)

    @tool(LOCAL)
    def foundry_update_run(run_id: RunId, configuration: Annotated[dict[str,Any], Field(description="Full replacement draft in the same shape as create_run; retain the original workflow method.")])->dict[str,Any]:
        """Replace an idle mesh draft. Changed settings invalidate dependent checkpoints and keep previously saved files."""
        return client.update_run(run_id,configuration)

    @tool(LOCAL)
    def foundry_run_status(run_id: RunId)->dict[str,Any]:
        """Check mesh progress, errors, saved checkpoints and preview URLs. Checking an interrupted run reconciles its saved status."""
        return client.get_run(run_id)

    @tool(START)
    def foundry_start(
        run_id: RunId,
        operation: Annotated[str, Field(description="mesh builds and refines; finish exports; rocket runs all stages. turnaround is available for the Turnaround method.")],
        request_id: RequestId,
    )->dict[str,Any]:
        """Queue the selected stage on the local GPU. First use can download models. Check status for progress and result links."""
        client.start(run_id,operation,request_id)
        return client.get_run(run_id)

    @tool(LOCAL)
    def foundry_cancel(run_id: RunId)->dict[str,Any]:
        """Request cancellation and keep completed checkpoints. An independent Hi3D download can continue."""
        client.cancel(run_id)
        return client.get_run(run_id)

    @tool(LOCAL)
    def foundry_show_run(run_id: RunId)->dict[str,Any]:
        """Ask the existing Foundry interface to display the saved mesh run without taking desktop focus."""
        return client.show(run_id)

    @tool(LOCAL)
    def foundry_package(run_id: RunId)->dict[str,Any]:
        """Get metadata and a local ZIP download URL for a completed mesh run. Use status until packaging finishes."""
        return client.package(run_id)

    from image_tools import register as register_images
    register_images(server,client,checked)
    from hair_tools import register as register_hair
    register_hair(server,client,checked)
    from splat_tools import register as register_splat
    register_splat(server,client,checked)
    from workspace import register as register_workspace
    register_workspace(server,client,checked)
    return server

def main():
    parser=argparse.ArgumentParser(description="Local Foundry MCP server")
    parser.add_argument("--comfy-url",default="http://127.0.0.1:8188")
    parser.add_argument("--input-root",action="append",default=[])
    parser.add_argument("--input-file",action="append",default=[])
    args=parser.parse_args()
    create_server(FoundryAPI(args.comfy_url,input_roots=args.input_root,input_files=args.input_file)).run(transport="stdio")

if __name__=="__main__":main()
