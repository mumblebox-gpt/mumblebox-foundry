"""Agent controls for the independently owned visible HairDeck wizard."""
from typing import Annotated, Any
from pydantic import Field
from client import identifier
from tool_contracts import CreationId, LOCAL, READ, RequestId, START, tool_registration

def register(server,client,checked):
    def path(ident,suffix=''):return '/hair/runs/'+identifier(ident)+suffix
    def compact(record):return {k:v for k,v in record.items() if k not in ('pending',)}
    tool = tool_registration(server, checked)
    @tool(READ)
    def foundry_hair_capabilities()->dict[str,Any]:
        """Read supported HairDeck controls, checkpoints, head profiles, defaults and output limitations."""
        return client.request('/hair/capabilities')
    @tool(LOCAL)
    def foundry_hair_create(configuration:Annotated[dict[str,Any], Field(description="HairDeck options from capabilities, including the uploaded image filename.")])->dict[str,Any]:
        """Configure hair from one uploaded image. Does not start downloads or inference. Use foundry_import_reference first."""
        return compact(client.request('/hair/runs',configuration))
    @tool(LOCAL)
    def foundry_hair_update(creation_id:CreationId,configuration:Annotated[dict[str,Any], Field(description="HairDeck options from capabilities, including the uploaded image filename.")])->dict[str,Any]:
        """Replace idle hair options. Export-only changes reuse the matching saved cards and chains."""
        return compact(client.request(path(creation_id),configuration,method='PATCH'))
    @tool(LOCAL)
    def foundry_hair_status(creation_id:CreationId)->dict[str,Any]:
        """Check progress, variations, preview paths and package metadata. Can reconcile an interrupted local run."""
        return compact(client.request(path(creation_id)))
    @tool(START)
    def foundry_hair_start(creation_id:CreationId,request_id:RequestId,operation:Annotated[str, Field(description="One of generate, rig, preview, avatar_preview, motion_preview or export.")]='generate',selected:Annotated[int, Field(description="Zero-based saved variation to inspect or export.")]=0)->dict[str,Any]:
        """Queue the selected HairDeck stage. First use may download models. Poll hair status for saved variations and output links."""
        if operation not in ('generate','rig','preview','avatar_preview','motion_preview','export'):raise ValueError('Choose generate, rig, preview, avatar_preview, motion_preview or export.')
        return compact(client.request(path(creation_id,'/start'),dict(request_id=request_id,operation=operation,selected=selected,client_id='foundry-agent')))
    @tool(LOCAL)
    def foundry_hair_cancel(creation_id:CreationId)->dict[str,Any]:
        """Cancel this hair job only. Keep all completed generations and saved results."""
        return compact(client.request(path(creation_id,'/cancel'),{}))
    @tool(LOCAL)
    def foundry_hair_show(creation_id:CreationId)->dict[str,Any]:
        """Show the saved hair wizard in the existing Foundry window without raising or focusing it."""
        return client.request(path(creation_id,'/show'),{})
