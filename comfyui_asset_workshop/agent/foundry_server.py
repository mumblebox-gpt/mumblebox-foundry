"""Foundry-specific MCP. HTTP owns execution; stdio owns no models or jobs."""
import argparse
import json
from functools import wraps
from typing import Any
from urllib.error import URLError
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from client import APIError
from foundry_client import FoundryAPI
from connection import AgentConnection

def checked(function):
    @wraps(function)
    def call(*args,**kwargs):
        try:return function(*args,**kwargs)
        except APIError as error:raise ToolError(json.dumps({"status":error.status,**error.details})) from None
        except (ValueError,OSError,URLError) as error:raise ToolError(str(error)) from None
    return call

def create_server(client):
    connection = AgentConnection(client)
    server=MCPServer("Mumblebox 3D Asset Foundry",version="0.2.0",
        lifespan=connection.lifespan,middleware=[connection.observe],instructions=(
        "Foundry includes the general-purpose Mumblebox Assets companion skill for setup and workflow guidance. "
        "On each connection, read workspace.agent_connection for its local path and revision, the installed app version, and update status. "
        "If checking is true, check back once. Report available updates and refresh an older copied skill from the bundled version. "
        "List workflow groups with foundry_workflows and request one group's actions and capabilities before use. "
        "The catalog exposes Guided, Virtual Turntable, both CCORE modes, Garment, graph reads and shared workspace controls. "
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

    @server.tool(structured_output=True)
    @checked
    def foundry_capabilities()->dict[str,Any]:
        """Get exact model/category/profile/settings/export choices and defaults."""
        return client.capabilities()

    @server.tool(structured_output=True)
    @checked
    def foundry_import_reference(path:str,role:str="primary",description:str="",target:str="")->dict[str,Any]:
        """Upload an authorized image; returns its reference card. Set target='ccore' for Image + Text."""
        return client.import_reference(path,role,description,target)

    @server.tool(structured_output=True)
    @checked
    def foundry_create_run(configuration:dict[str,Any])->dict[str,Any]:
        """Save method (single-image or turnaround), name, references, category, profile, overrides and export selection. Single-image accepts exactly one reference; no turnaround model is used. Does not generate."""
        return client.create_run(configuration)

    @server.tool(structured_output=True)
    @checked
    def foundry_update_run(run_id:str,configuration:dict[str,Any])->dict[str,Any]:
        """Replace the idle run configuration with a full configuration; stale dependent checkpoints are invalidated."""
        return client.update_run(run_id,configuration)

    @server.tool(structured_output=True)
    @checked
    def foundry_run_status(run_id:str)->dict[str,Any]:
        """Read stage, progress, download state, completed checkpoints, errors and preview links."""
        return client.get_run(run_id)

    @server.tool(structured_output=True)
    @checked
    def foundry_start(run_id:str,operation:str,request_id:str)->dict[str,Any]:
        """Run turnaround, mesh, finish or rocket through the wizard's queue. Same request_id is retry-safe."""
        client.start(run_id,operation,request_id)
        return client.get_run(run_id)

    @server.tool(structured_output=True)
    @checked
    def foundry_cancel(run_id:str)->dict[str,Any]:
        """Cancel only this Foundry run while preserving completed files."""
        client.cancel(run_id)
        return client.get_run(run_id)

    @server.tool(structured_output=True)
    @checked
    def foundry_show_run(run_id:str)->dict[str,Any]:
        """Request display in the already-open Foundry interface, without changing desktop focus."""
        return client.show(run_id)

    @server.tool(structured_output=True)
    @checked
    def foundry_package(run_id:str)->dict[str,Any]:
        """Get completed package metadata and its local download URL, not a large binary response."""
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
