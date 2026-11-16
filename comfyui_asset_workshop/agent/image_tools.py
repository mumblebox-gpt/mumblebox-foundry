"""Image creator tools delegate to the same service as the visible creator."""
import json
from typing import Annotated, Any
from pydantic import Field
from urllib.parse import urlencode
from client import identifier
from tool_contracts import CreationId, InputPath, LOCAL, READ, REMOVE, RequestId, START, tool_registration


def register(server, client, checked):
    def path(ident, suffix=''):return '/images/'+identifier(ident)+suffix
    def compact(record):return {k:v for k,v in record.items() if k not in ('outputs','pending','last_stage','auxiliary_files')}
    tool = tool_registration(server, checked)

    @tool(READ)
    def foundry_image_capabilities()->dict[str,Any]:
        """Read image models, categories, references, defaults, licenses and edit support."""
        return client.request('/images/capabilities')

    @tool(LOCAL)
    def foundry_image_create(configuration:Annotated[dict[str,Any], Field(description="Image draft including category, supported model, description and optional authorized references.")])->dict[str,Any]:
        """Configure a single image or front/back pair without generating. Use imported references and installed LoRAs."""
        return compact(client.request('/images',configuration))

    @tool(LOCAL)
    def foundry_image_update(creation_id:CreationId,configuration:Annotated[dict[str,Any], Field(description="Image draft including category, supported model, description and optional authorized references.")])->dict[str,Any]:
        """Replace idle image settings. Completed revisions remain available; changed inputs invalidate the active set."""
        return compact(client.request(path(creation_id),configuration,method='PATCH'))

    @tool(LOCAL)
    def foundry_image_status(creation_id:CreationId)->dict[str,Any]:
        """Check progress, accepted images and errors with local image URLs. Can reconcile an interrupted local run."""
        return compact(client.request(path(creation_id)))

    @tool(START)
    def foundry_image_start(creation_id:CreationId,request_id:RequestId,operation:Annotated[str, Field(description="generate resumes matching stages, regenerate starts a variation, edit runs a prepared selection.")]='generate')->dict[str,Any]:
        """Queue image creation or a prepared edit. First use may download models. Check image status for downloadable results."""
        if operation not in ('generate','regenerate','edit'):raise ValueError('Choose generate, regenerate or edit.')
        return compact(client.request(path(creation_id,'/start'),dict(request_id=identifier(request_id),operation=operation,client_id='foundry-agent')))

    @tool(LOCAL)
    def foundry_image_cancel(creation_id:CreationId)->dict[str,Any]:
        """Cancel this image job, preserving completed images and revisions."""
        return compact(client.request(path(creation_id,'/cancel'),{}))

    @tool(LOCAL)
    def foundry_image_show(creation_id:CreationId)->dict[str,Any]:
        """Display this creation in the existing Foundry interface without raising the window."""
        return client.request(path(creation_id,'/show'),{})

    @tool(LOCAL)
    def foundry_image_prepare_edit(creation_id:CreationId,side:Annotated[str, Field(description="Side of the accepted image set to edit.")],source_id:Annotated[str, Field(description="Recorded source revision ID.")],mask_path:InputPath,prompt:Annotated[str, Field(description="Edit instructions for the selected region.")],feather:Annotated[int, Field(description="Mask edge feather amount.")]=0,replace_detail:Annotated[bool, Field(description="Use the replacement-detail path when supported by the model.")]=False)->dict[str,Any]:
        """Prepare a local edit using an authorized white-selected/black-preserved PNG mask. Start edit, inspect candidate, then accept explicitly."""
        source=client.allowed_input(mask_path)
        if source.stat().st_size>20*1024**2:raise ValueError('Use a mask below 20 MB.')
        options=dict(side=side,source_id=identifier(source_id),prompt=prompt,feather=feather,replace_detail=replace_detail)
        data,kind=client.multipart({'options':json.dumps(options)},'mask',source)
        return compact(client.request(path(creation_id,'/edit'),data,content_type=kind))

    @tool(LOCAL)
    def foundry_image_accept(creation_id:CreationId,revision_id:Annotated[str, Field(description="Reviewed revision to make current.")],expected_revision:Annotated[str, Field(description="Revision that is current now; rejects a stale update.")])->dict[str,Any]:
        """Accept a reviewed edit or restore a revision. expected_revision guards against overwriting newer choices."""
        return compact(client.request(path(creation_id,'/accept'),dict(revision_id=identifier(revision_id),expected=identifier(expected_revision))))

    @tool(LOCAL)
    def foundry_image_save(creation_id:CreationId)->dict[str,Any]:
        """Save the accepted set to Gallery and return its portable image package URL."""
        record=compact(client.request(path(creation_id,'/save'),{}))
        return {'creation':record,'download_url':client.base_url+path(creation_id,'/package')}

    @tool(LOCAL)
    def foundry_image_handoff(creation_id:CreationId,mode:Annotated[str, Field(description="pair copies an accepted pair; single copies one side.")]='pair',side:Annotated[str|None, Field(description="Selected side for single-image handoff.")]=None,revision_id:Annotated[str|None, Field(description="Optional chosen saved revision.")]=None)->dict[str,Any]:
        """Copy an accepted pair or one selected Gallery side into 3D inputs with provenance. Does not generate a mesh."""
        return client.request(path(creation_id,'/handoff'),dict(mode=mode,side=side,revision_id=revision_id))

    @tool(READ)
    def foundry_image_gallery(search:Annotated[str, Field(description="Text to match in the saved gallery.")]='',category:Annotated[str, Field(description="Optional supported image category.")]='',kind:Annotated[str, Field(description="all, single or pair.")]='all',sort:Annotated[str, Field(description="newest or oldest.")]='newest',cursor:Annotated[str, Field(description="Cursor from the preceding response; empty starts a new list.")]='',limit:Annotated[int, Field(description="Maximum saved creations requested per page.")]=24)->dict[str,Any]:
        """List saved image creations with bounded pagination. kind: all, single, pair; sort: newest, oldest."""
        return client.request('/images?'+urlencode(dict(search=search,category=category,kind=kind,sort=sort,cursor=cursor,limit=limit)))

    @tool(LOCAL)
    def foundry_image_removal_preview(creation_ids:Annotated[list[str], Field(description="Exact IDs of the Gallery entries selected for review.")],delete_files:Annotated[bool, Field(description="Include owned files only when the user explicitly requests file deletion.")]=False)->dict[str,Any]:
        """Review exact selected creations for removal. Default removes Gallery entries only; file deletion needs explicit user authorization."""
        return client.request('/images/removal-preview',dict(ids=[identifier(i) for i in creation_ids],delete_files=delete_files))

    @tool(REMOVE)
    def foundry_image_remove(confirmation_token:Annotated[str, Field(description="Token from the exact removal preview the user authorized.")])->dict[str,Any]:
        """Apply an explicitly approved removal preview. Do not use without user authorization for the listed scope."""
        return client.request('/images/remove',{'token':confirmation_token})
