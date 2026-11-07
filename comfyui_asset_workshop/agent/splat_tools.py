"""Agent entry points share the same durable, visible splat wizard owner."""
from typing import Any
from client import identifier

def register(server,client,checked):
    def path(ident,suffix=''):return '/splat/runs/'+identifier(ident)+suffix
    def tool(fn):return server.tool(structured_output=True)(checked(fn))
    @tool
    def foundry_splat_capabilities()->dict[str,Any]:
        """Read Splat & Solid controls, defaults, outputs and original model credits."""
        return client.request('/splat/capabilities')
    @tool
    def foundry_splat_create(configuration:dict[str,Any])->dict[str,Any]:
        """Configure one uploaded image without downloading models or starting generation."""
        return client.request('/splat/runs',configuration)
    @tool
    def foundry_splat_status(creation_id:str)->dict[str,Any]:
        """Read overall progress, completed stages, geometry checks and saved output files."""
        return client.request(path(creation_id))
    @tool
    def foundry_splat_start(creation_id:str,request_id:str,operation:str='rocket')->dict[str,Any]:
        """Run generation, cleanup, export or Rocket using the same visible wizard; retries are idempotent."""
        client.request(path(creation_id,'/show'),{})
        return client.request(path(creation_id,'/start'),dict(operation=operation,request_id=request_id,client_id='foundry-agent'))
    @tool
    def foundry_splat_cancel(creation_id:str)->dict[str,Any]:
        """Cancel only this job and preserve completed stages and assets."""
        return client.request(path(creation_id,'/cancel'),{})
    @tool
    def foundry_splat_show(creation_id:str)->dict[str,Any]:
        """Show a saved splat wizard in the existing Foundry window without OS focus changes."""
        return client.request(path(creation_id,'/show'),{})
