"""Optional masked concept-sheet editing; original pixels remain immutable."""
import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from .fvb import runtime
from .fvb.journal import atomic_json,signature
from .fvb.repair import composite
from .fvb.sheet_nodes import save_pixels,QwenSheetEncode,TiledReferenceVAE
from .fvb.recipes import model,remap

def source(job_id):
    job=runtime.journal().read(job_id);edit=job['concept_editor']
    root=runtime.journal().folder(job_id)
    image=np.asarray(Image.open(root/edit['source']).convert('RGBA'))
    mask=np.asarray(Image.open(root/edit['mask']).convert('L'))>=128
    return image,mask,edit

class ConceptCanvasEncode(QwenSheetEncode):
    """Keep the wide concept's pixel frame; measured sheets stay square-only."""
    CATEGORY='Foundry/3D-Guided'
    def encode(self,clip,vae,prompt,negative_prompt,tiled_encode,**images):
        from comfy_extras.nodes_qwen import TextEncodeQwenImage21
        canvas=images['image_1']
        if canvas.shape[0]!=1 or any(size<32 or size%32 for size in canvas.shape[1:3]):
            raise ValueError('Keep the complete concept canvas in multiples of 32 pixels.')
        wrapped=TiledReferenceVAE(vae) if tiled_encode and not isinstance(vae,TiledReferenceVAE) else vae
        result=tuple(TextEncodeQwenImage21.execute(clip=clip,vae=wrapped,prompt=prompt,
            negative_prompt=negative_prompt,resolution=0,images=images))
        if tuple(result[2]['samples'].shape[-2:])!=(canvas.shape[1]//16,canvas.shape[2]//16):
            raise ValueError('The native encoder changed the concept canvas dimensions.')
        return result

class ConceptEditInput:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'job_id':('STRING',{'default':''})}}
    RETURN_TYPES=('IMAGE','IMAGE','MASK');FUNCTION='load';CATEGORY='Foundry/3D-Guided'
    @classmethod
    def IS_CHANGED(cls,job_id):return signature(runtime.journal().read(job_id).get('concept_editor',{}))
    def load(self,job_id):
        pixels,mask,edit=source(job_id);context=pixels[:,:,:3].copy()
        if edit.get('replace_detail',True):context[mask]=128
        return (torch.from_numpy(context.astype('float32')/255).unsqueeze(0),torch.from_numpy(pixels.astype('float32')/255).unsqueeze(0),torch.from_numpy(mask.astype('float32')).unsqueeze(0))

class CommitConceptEdit:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'job_id':('STRING',{'default':''}),'image':('IMAGE',)}}
    RETURN_TYPES=('IMAGE',);FUNCTION='save';CATEGORY='Foundry/3D-Guided';OUTPUT_NODE=True
    def save(self,job_id,image):
        original,mask,edit=source(job_id)
        if image.shape[0]!=1 or not bool(torch.isfinite(image).all()):raise ValueError('The concept edit must produce one finite image.')
        candidate=(image[0].detach().cpu().numpy().clip(0,1)*255).round().astype('uint8')
        corrected=composite(original,candidate,mask,edit['feather'])
        path,record=save_pixels(job_id,'concept:edit_candidate',corrected.astype('float32')/255,source_sha256=edit['source_sha256'],unmasked_bytes_identical=bool(np.array_equal(original[~mask],corrected[~mask])))
        return {'ui':{'images':[runtime.preview_image(path,job_id)],'fvb_artifacts':[{'concept:edit_candidate':record}]},'result':(torch.from_numpy(corrected.astype('float32')/255).unsqueeze(0),)}

NODES={'G3D_ConceptEditInput':ConceptEditInput,'G3D_CommitConceptEdit':CommitConceptEdit,'G3D_ConceptCanvasEncode':ConceptCanvasEncode}

def graph(job):
    spec=job['spec'];edit=job['concept_editor'];g={}
    def add(i,t,**kw):g[str(i)]={'class_type':t,'inputs':kw,'_meta':{'fvb_stage':'concept_edit'}};return [str(i),0]
    src=add(1,'G3D_ConceptEditInput',job_id=job['id'])
    q=add(2,'UNETLoader',unet_name=model('qwen21'),weight_dtype='default')
    q=add(3,'QwenImage21Cache',model=q,device='off',dtype='default')
    q=add(4,'AW_ModelBudget',model=q,extra_gb=spec['extra_vram_headroom_gb'])
    clip=add(5,'CLIPLoader',clip_name=model('qwen21_clip'),type='qwen_image',device='default')
    vae=add(6,'VAELoader',vae_name=model('qwen21_vae'))
    vae=add(7,'G3D_ControlVAE',vae=vae,tiled_encode=True)
    patch=add(8,'ModelPatchLoader',name=model('qwen21_union'))
    q=add(9,'ZImageFunControlnet',model=q,model_patch=patch,vae=vae,inpaint_image=['1',1],mask=['1',2],strength=1.,start_percent=0.,end_percent=1.)
    appearance=add(14,'G3D_LoadImage',job_id=job['id'],artifact_key='appearance')
    appearance=add(15,'G3D_ResizeReference',image=appearance,size=1024)
    prompt='Edit the selected area of this concept turnaround sheet. Preserve the same object identity, four horizontal panels, viewpoints, scale, positions and all unselected details. Apply this correction to the selected surface: '+edit['prompt']
    cond=add(10,'G3D_ConceptCanvasEncode',clip=clip,vae=vae,image_1=src,image_2=['1',1],image_3=appearance,prompt=prompt,negative_prompt='',tiled_encode=True)
    sample=add(11,'KSampler',model=q,positive=cond,negative=['10',1],latent_image=['10',2],seed=edit['seed'],steps=edit['steps'],cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.)
    decoded=add(12,'VAEDecodeTiled',samples=sample,vae=vae,tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8)
    add(13,'G3D_CommitConceptEdit',job_id=job['id'],image=decoded)
    return g

def start(owner,ident,data):
    from .runs import busy
    from ...artifacts import owned_path
    import folder_paths
    if busy() or owner.other_busy():raise ValueError('Wait for the active stage before editing the concept sheet.')
    job=owner.get(ident)
    if 'concept:sheet' not in job['artifacts']:raise ValueError('Generate the concept sheet first.')
    prompt=data.get('prompt','').strip()
    if not prompt or len(prompt)>4000:raise ValueError('Describe the selected-area correction in 1–4000 characters.')
    maskpath=owned_path(folder_paths.get_input_directory(),Path(folder_paths.get_input_directory())/data.get('mask_filename',''))
    if not maskpath.is_file():raise ValueError('Upload the editor selection mask.')
    original,record=runtime.artifact(ident,'concept:sheet')
    with Image.open(original) as im:shape=im.size
    with Image.open(maskpath) as im:
        if im.size!=shape:raise ValueError('The selection must match the complete concept sheet dimensions.')
        painted=im.convert('L');a=np.asarray(painted)
        if not bool((a>=128).any()):raise ValueError('Select an area before generating an edit.')
    edit_id=uuid.uuid4().hex;root=owner.engine.store.folder(ident);folder=root/'concept-edits'/edit_id;folder.mkdir(parents=True)
    shutil.copy2(original,folder/'source.png');painted.save(folder/'mask.png')
    edit={'id':edit_id,'source':(folder/'source.png').relative_to(root).as_posix(),'mask':(folder/'mask.png').relative_to(root).as_posix(),
        'source_sha256':record['sha256'],'prompt':prompt,'feather':max(0,min(32,int(data.get('feather',4)))),'seed':int(data.get('seed',job['spec']['enhancement_seed'])),
        'steps':job['spec']['enhancement_steps'],
        'replace_detail':bool(data.get('replace_detail',True)),
        'status':'running','previous_status':job['status'] if job['status'] not in ('failed','cancelled','interrupted') else 'awaiting_review',
        'previous_awaiting':job.get('awaiting_stage') or 'concept'}
    if not 0<=edit['seed']<=2**53-16:raise ValueError('Use a valid nonnegative seed.')
    owner.engine.store.update(ident,concept_editor=edit,status='running',cancelled=False,current_stage='concept_edit',request_id='concept_edit-'+edit_id,error='')
    owner.tasks[ident]=asyncio.create_task(execute(owner,ident))
    return owner.public(owner.get(ident))

async def execute(owner,ident):
    prompt_id=str(uuid.uuid4());job=owner.get(ident);edit=job['concept_editor'];folder=owner.engine.store.folder(ident)/'concept-edits'/edit['id']
    try:
        await owner.engine.guard(job['spec']['workflow_path'])
        await owner.engine.lifecycle.release('before concept area edit')
        recipe=graph(job);await owner.bind_finishing(recipe,job['spec']['client_id'],offset=300000)
        recipe=remap(recipe,300000);atomic_json(folder/'prompt.json',recipe)
        owner.engine.owned_prompts[ident]=prompt_id
        await owner.native.submit(recipe,prompt_id,job['spec']['client_id'])
        history=await owner.native.wait(prompt_id,7200,lambda:owner.get(ident)['cancelled'])
        atomic_json(folder/'history.json',history)
        if history.get('status',{}).get('status_str')!='success':
            errors=[m[1].get('exception_message','') for m in history.get('status',{}).get('messages',[]) if m[0]=='execution_error']
            raise ValueError('Concept edit failed: '+('; '.join(errors).strip() or history.get('status',{}).get('status_str','interrupted'))[:900]+'. The original sheet is unchanged.')
        artifacts={}
        for output in history.get('outputs',{}).values():
            for item in output.get('fvb_artifacts',[]):artifacts.update(item)
        if 'concept:edit_candidate' not in artifacts:raise ValueError('The edit completed without a saved candidate.')
        current=owner.get(ident)
        owner.engine.store.update(ident,artifacts={**current['artifacts'],**artifacts},concept_editor={**edit,'status':'candidate'},status=edit['previous_status'],current_stage='',awaiting_stage=edit['previous_awaiting'])
    except Exception as error:
        owner.engine.store.update(ident,status='failed',current_stage='',error=str(error),concept_editor={**edit,'status':'failed'})
    finally:
        owner.engine.owned_prompts.pop(ident,None);owner.tasks.pop(ident,None)
        if not owner.native.active_ids():await owner.engine.lifecycle.release('after concept area edit')

def accept(owner,ident):
    job=owner.get(ident);edit=job.get('concept_editor',{})
    if edit.get('status')!='candidate':raise ValueError('Generate and review a concept-edit candidate first.')
    if job['artifacts']['concept:sheet']['sha256']!=edit['source_sha256']:raise ValueError('The concept sheet changed. Prepare a fresh editor selection.')
    candidate,record=runtime.artifact(ident,'concept:edit_candidate');root=owner.engine.store.folder(ident)
    artifacts=dict(job['artifacts']);artifacts['concept:sheet']=record
    with Image.open(candidate) as image:
        if image.size!=(4096,1024):raise ValueError('The accepted concept must retain the four original panel frames.')
        for index,side in enumerate(('front','left','back','right')):
            path=candidate.parent/('accepted-'+side+'.png');image.crop((index*1024,0,(index+1)*1024,1024)).save(path)
            artifacts['concept:'+side]=runtime.record(path,path.relative_to(root).as_posix(),'image',width=1024,height=1024)
    atomic_json(root/'concept-edits'/edit['id']/'accepted-before.json',job)
    keep={'concept','proxy','render','sheet'}
    for key in list(artifacts):
        if key.startswith(('enhanced:','prepared:','corrected:','reconstruction','refined','refine:','textured')):artifacts.pop(key)
    updated=owner.engine.store.update(ident,artifacts=artifacts,completed={k:v for k,v in job['completed'].items() if k in keep},
        status='awaiting_review',awaiting_stage='concept',concept_editor={**edit,'status':'accepted'},export_run_id=None,error='')
    return owner.public(updated)
