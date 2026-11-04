"""Native adapters for explicitly requested view repairs; inference stays in Comfy nodes."""
import hashlib
import json
import numpy as np
import torch
from . import runtime
from .journal import atomic_json,signature
from .repair import image as read_image,allowed_mask,composite
from .sheet_nodes import save_pixels


def inputs(job_id,view_id):
    job=runtime.journal().read(job_id);r=job['spec']['repair_requests'].get(view_id)
    if r is None:raise ValueError('No explicit repair request for this view.')
    source,source_record=runtime.artifact(job_id,'repair_source:'+view_id)
    mask,_=runtime.artifact(job_id,'repair_mask:'+view_id)
    _,camera=runtime.artifact(job_id,'enhanced:cameras')
    if source_record['sha256']!=r['source_sha256'] or camera['sha256']!=r['camera_sha256']:
        raise ValueError('Repair source/camera changed; prepare a current editor source.')
    pixels=read_image(source);painted=read_image(mask)
    return pixels,allowed_mask(pixels,painted,r['margin_px']),r


class RepairInput:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'job_id':('STRING',{'default':''}),'view_id':(['front','right','back','left'],)}}
    RETURN_TYPES=('IMAGE','IMAGE','MASK');RETURN_NAMES=('masked_reference','source','regenerate_mask')
    FUNCTION='load';CATEGORY='Foundry View Bridge/Repair'
    @classmethod
    def IS_CHANGED(cls,job_id,view_id):
        job=runtime.journal().read(job_id)
        return signature({k:job['artifacts'].get(k) for k in ('repair_source:'+view_id,'repair_mask:'+view_id,'enhanced:cameras')}|{'request':job['spec']['repair_requests'].get(view_id)})
    def load(self,job_id,view_id):
        source,mask,_=inputs(job_id,view_id);context=source[:,:,:3].copy();context[mask]=128
        return (torch.from_numpy(context.astype('float32')/255).unsqueeze(0),
                torch.from_numpy(source.astype('float32')/255).unsqueeze(0),torch.from_numpy(mask.astype('float32')).unsqueeze(0))


class CommitRepair:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'job_id':('STRING',{'default':''}),'view_id':(['front','right','back','left'],),'image':('IMAGE',)}}
    RETURN_TYPES=('IMAGE',);FUNCTION='save';CATEGORY='Foundry View Bridge/Repair';OUTPUT_NODE=True
    def save(self,job_id,view_id,image):
        if image.shape[0]!=1 or not bool(torch.isfinite(image).all()):raise ValueError('Repair needs one finite image.')
        source,mask,settings=inputs(job_id,view_id)
        candidate=(image[0].detach().cpu().numpy().clip(0,1)*255).round().astype('uint8')
        corrected=composite(source,candidate,mask,settings['feather_px'])
        receipts={};previews=[]
        for key,pixels in [('repair_raw:'+view_id,candidate),('repair_applied_mask:'+view_id,np.repeat(mask[:,:,None],3,axis=2).astype('uint8')*255),('corrected:'+view_id,corrected)]:
            p,receipt=save_pixels(job_id,key,pixels.astype('float32')/255,camera_id=view_id,
                calibration_status='inherited_target_unverified',image_transforms=[],source_sha256=settings['source_sha256'],camera_manifest_sha256=settings['camera_sha256'])
            receipts[key]=receipt;previews.append(runtime.preview_image(p,job_id))
        _,camera_record=runtime.artifact(job_id,'enhanced:cameras')
        camera_path,_=runtime.artifact(job_id,'enhanced:cameras')
        camera=next(c for c in json.loads(camera_path.read_text(encoding='utf-8'))['frames'] if c['id']==view_id)
        outside_original=hashlib.sha256(source[~mask].tobytes()).hexdigest();outside_result=hashlib.sha256(corrected[~mask].tobytes()).hexdigest()
        report=dict(schema='fvb.repair/1',view_id=view_id,camera=camera,camera_manifest_sha256=camera_record['sha256'],settings=settings,
            source_sha256=settings['source_sha256'],corrected_sha256=receipts['corrected:'+view_id]['sha256'],
            requested_mask_sha256=runtime.artifact(job_id,'repair_mask:'+view_id)[1]['sha256'],
            applied_pixels=int(mask.sum()),unmasked_bytes_identical=outside_original==outside_result,
            original_alpha_identical=bool(np.array_equal(source[:,:,3],corrected[:,:,3])),
            unmasked_sha256=outside_result,calibration_status='inherited_target_unverified',image_transforms=[])
        path,relative=runtime.target(job_id,'repair_report:'+view_id,'.json');atomic_json(path,report)
        receipts['repair_report:'+view_id]=runtime.record(path,relative,'repair_report')
        return {'ui':{'images':[previews[-1]],'fvb_artifacts':[receipts],'text':['Repair saved. Inspect it before Continue; original frame, alpha and unmasked pixels retained.']},
                'result':(torch.from_numpy(corrected.astype('float32')/255).unsqueeze(0),)}


class RepairControl:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{
        'operation':(['status','prepare_editor','apply_repair','clear_repair'],{'default':'status'}),
        'job_id':('STRING',{'default':''}),'view_id':(['front','right','back','left'],),
        'ticket_id':('STRING',{'default':''}),'mask_filename':('STRING',{'default':''}),
        'prompt':('STRING',{'multiline':True,'default':''}),
        'seed':('INT',{'default':42,'min':0,'max':2**53-16}),
        'steps':('INT',{'default':40,'min':20,'max':100}),
        'cfg':('FLOAT',{'default':1,'min':.1,'max':20}),
        'margin_px':('INT',{'default':8,'min':0,'max':32}),
        'feather_px':('INT',{'default':4,'min':0,'max':16})}}
    RETURN_TYPES=('STRING',);FUNCTION='control';CATEGORY='Foundry View Bridge/Repair';OUTPUT_NODE=True
    def control(self,operation,job_id,view_id,ticket_id,mask_filename,**controls):
        from .service import service
        import asyncio
        svc=service();future=asyncio.run_coroutine_threadsafe(svc.repair_control(operation,job_id,view_id,ticket_id,mask_filename,controls),svc.server.loop)
        result=future.result(timeout=90)
        return {'ui':{'text':[json.dumps(result,indent=2)]},'result':(json.dumps(result),)}
    @classmethod
    def IS_CHANGED(cls,**kw):return float('nan')


REPAIR_NODES={'G3D_RepairInput':RepairInput,'G3D_CommitRepair':CommitRepair,'G3D_RepairControl':RepairControl}
