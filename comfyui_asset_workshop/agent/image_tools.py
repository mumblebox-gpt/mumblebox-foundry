"""Image creator tools delegate to the same service as the visible creator."""
import json
from typing import Any
from urllib.parse import urlencode
from client import identifier


def register(server, client, checked):
    def path(ident, suffix=''):return '/images/'+identifier(ident)+suffix
    def compact(record):return {k:v for k,v in record.items() if k not in ('outputs','pending','last_stage','auxiliary_files')}
    def tool(function):return server.tool(structured_output=True)(checked(function))

    @tool
    def foundry_image_capabilities()->dict[str,Any]:
        """Read image models, categories, references, defaults, licenses and edit support."""
        return client.request('/images/capabilities')

    @tool
    def foundry_image_create(configuration:dict[str,Any])->dict[str,Any]:
        """Configure a single image or front/back pair without generating. Use imported references and installed LoRAs."""
        return compact(client.request('/images',configuration))

    @tool
    def foundry_image_update(creation_id:str,configuration:dict[str,Any])->dict[str,Any]:
        """Replace idle image settings. Completed revisions remain available; changed inputs invalidate the active set."""
        return compact(client.request(path(creation_id),configuration,method='PATCH'))

    @tool
    def foundry_image_status(creation_id:str)->dict[str,Any]:
        """Read progress, accepted images, revisions, download state and errors. Image URLs point to the local server."""
        return compact(client.request(path(creation_id)))

    @tool
    def foundry_image_start(creation_id:str,request_id:str,operation:str='generate')->dict[str,Any]:
        """Run generate, regenerate, or a prepared edit. Reuse request_id only for a retry of the same operation."""
        if operation not in ('generate','regenerate','edit'):raise ValueError('Choose generate, regenerate or edit.')
        return compact(client.request(path(creation_id,'/start'),dict(request_id=identifier(request_id),operation=operation,client_id='foundry-agent')))

    @tool
    def foundry_image_cancel(creation_id:str)->dict[str,Any]:
        """Cancel this image job, preserving completed images and revisions."""
        return compact(client.request(path(creation_id,'/cancel'),{}))

    @tool
    def foundry_image_show(creation_id:str)->dict[str,Any]:
        """Display this creation in the existing Foundry interface without raising the window."""
        return client.request(path(creation_id,'/show'),{})

    @tool
    def foundry_image_prepare_edit(creation_id:str,side:str,source_id:str,mask_path:str,prompt:str,feather:int=0,replace_detail:bool=False)->dict[str,Any]:
        """Prepare a local edit using an authorized white-selected/black-preserved PNG mask. Start edit, inspect candidate, then accept explicitly."""
        source=client.allowed_input(mask_path)
        if source.stat().st_size>20*1024**2:raise ValueError('Use a mask below 20 MB.')
        options=dict(side=side,source_id=identifier(source_id),prompt=prompt,feather=feather,replace_detail=replace_detail)
        data,kind=client.multipart({'options':json.dumps(options)},'mask',source)
        return compact(client.request(path(creation_id,'/edit'),data,content_type=kind))

    @tool
    def foundry_image_accept(creation_id:str,revision_id:str,expected_revision:str)->dict[str,Any]:
        """Accept a reviewed edit or restore a revision. expected_revision guards against overwriting newer choices."""
        return compact(client.request(path(creation_id,'/accept'),dict(revision_id=identifier(revision_id),expected=identifier(expected_revision))))

    @tool
    def foundry_image_save(creation_id:str)->dict[str,Any]:
        """Save the accepted set to Gallery and return its portable image package URL."""
        record=compact(client.request(path(creation_id,'/save'),{}))
        return {'creation':record,'download_url':client.base_url+path(creation_id,'/package')}

    @tool
    def foundry_image_handoff(creation_id:str,mode:str='pair',side:str|None=None,revision_id:str|None=None)->dict[str,Any]:
        """Copy an accepted pair or one selected Gallery side into 3D inputs with provenance. Does not generate a mesh."""
        return client.request(path(creation_id,'/handoff'),dict(mode=mode,side=side,revision_id=revision_id))

    @tool
    def foundry_image_gallery(search:str='',category:str='',kind:str='all',sort:str='newest',cursor:str='',limit:int=24)->dict[str,Any]:
        """List saved image creations with bounded pagination. kind: all, single, pair; sort: newest, oldest."""
        return client.request('/images?'+urlencode(dict(search=search,category=category,kind=kind,sort=sort,cursor=cursor,limit=limit)))

    @tool
    def foundry_image_removal_preview(creation_ids:list[str],delete_files:bool=False)->dict[str,Any]:
        """Review exact selected creations for removal. Default removes Gallery entries only; file deletion needs explicit user authorization."""
        return client.request('/images/removal-preview',dict(ids=[identifier(i) for i in creation_ids],delete_files=delete_files))

    @tool
    def foundry_image_remove(confirmation_token:str)->dict[str,Any]:
        """Apply an explicitly approved removal preview. Do not use without user authorization for the listed scope."""
        return client.request('/images/remove',{'token':confirmation_token})
