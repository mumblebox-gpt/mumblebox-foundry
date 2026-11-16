"""Agent entry points share the same durable, visible splat wizard owner."""
from typing import Annotated, Any
from pydantic import Field
from client import identifier
from tool_contracts import CreationId, LOCAL, READ, RequestId, START, tool_registration

def register(server,client,checked):
    def path(ident,suffix=''):return '/splat/runs/'+identifier(ident)+suffix
    tool = tool_registration(server, checked)
    @tool(READ)
    def foundry_splat_capabilities()->dict[str,Any]:
        """Read Splat & Solid controls, defaults, outputs and original model credits."""
        return client.request('/splat/capabilities')
    @tool(LOCAL)
    def foundry_splat_create(configuration:Annotated[dict[str,Any], Field(description="Splat & Solid options and one uploaded image filename from the reference tool.")])->dict[str,Any]:
        """Configure one uploaded image without downloading models or starting generation."""
        return client.request('/splat/runs',configuration)
    @tool(LOCAL)
    def foundry_splat_status(creation_id:CreationId)->dict[str,Any]:
        """Check overall progress, geometry checks and output paths. Can reconcile an interrupted local run."""
        return client.request(path(creation_id))
    @tool(START)
    def foundry_splat_start(creation_id:CreationId,request_id:RequestId,operation:Annotated[str, Field(description="Choose generation, cleanup, export or rocket (remaining stages).")]='rocket')->dict[str,Any]:
        """Queue the chosen Splat & Solid stage. First use may download models. Poll splat status for geometry and artifact links."""
        return client.request(path(creation_id,'/start'),dict(operation=operation,request_id=request_id,client_id='foundry-agent'))
    @tool(LOCAL)
    def foundry_splat_cancel(creation_id:CreationId)->dict[str,Any]:
        """Cancel only this job and preserve completed stages and assets."""
        return client.request(path(creation_id,'/cancel'),{})
    @tool(LOCAL)
    def foundry_splat_show(creation_id:CreationId)->dict[str,Any]:
        """Show a saved splat wizard in the existing Foundry window without OS focus changes."""
        return client.request(path(creation_id,'/show'),{})
