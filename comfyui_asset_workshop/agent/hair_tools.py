"""Agent controls for the independently owned visible HairDeck wizard."""
from typing import Any
from client import identifier

def register(server,client,checked):
    def path(ident,suffix=''):return '/hair/runs/'+identifier(ident)+suffix
    def compact(record):return {k:v for k,v in record.items() if k not in ('pending',)}
    def tool(function):return server.tool(structured_output=True)(checked(function))
    @tool
    def foundry_hair_capabilities()->dict[str,Any]:
        """Read supported HairDeck controls, checkpoints, head profiles, defaults and output limitations."""
        return client.request('/hair/capabilities')
    @tool
    def foundry_hair_create(configuration:dict[str,Any])->dict[str,Any]:
        """Configure hair from one uploaded image. Does not start downloads or inference. Use foundry_import_reference first."""
        return compact(client.request('/hair/runs',configuration))
    @tool
    def foundry_hair_update(creation_id:str,configuration:dict[str,Any])->dict[str,Any]:
        """Replace idle hair options. Export-only changes reuse the matching saved cards and chains."""
        return compact(client.request(path(creation_id),configuration,method='PATCH'))
    @tool
    def foundry_hair_status(creation_id:str)->dict[str,Any]:
        """Read progress, saved variations, preview paths, selected exports and package/History metadata."""
        return compact(client.request(path(creation_id)))
    @tool
    def foundry_hair_start(creation_id:str,request_id:str,operation:str='generate',selected:int=0)->dict[str,Any]:
        """Run generate, rig (add chains to saved cards), preview, avatar_preview, motion_preview or export through the visible wizard owner; retries are idempotent."""
        if operation not in ('generate','rig','preview','avatar_preview','motion_preview','export'):raise ValueError('Choose generate, rig, preview, avatar_preview, motion_preview or export.')
        return compact(client.request(path(creation_id,'/start'),dict(request_id=request_id,operation=operation,selected=selected,client_id='foundry-agent')))
    @tool
    def foundry_hair_cancel(creation_id:str)->dict[str,Any]:
        """Cancel this hair job only. Keep all completed generations and saved results."""
        return compact(client.request(path(creation_id,'/cancel'),{}))
    @tool
    def foundry_hair_show(creation_id:str)->dict[str,Any]:
        """Show the saved hair wizard in the existing Foundry window without raising or focusing it."""
        return client.request(path(creation_id,'/show'),{})
