"""Native adapters for exact sheet editing. Heavy inference stays in native Comfy."""
import copy
import json
import numpy as np
import torch
from PIL import Image
from . import runtime
from .journal import atomic_json, signature
from .sheet import ORDER, pack_arrays, split_array


def save_pixels(job_id,key,pixels,**metadata):
    path,relative=runtime.target(job_id,key,'.png')
    value=(np.asarray(pixels).clip(0,1)*255).round().astype('uint8')
    Image.fromarray(value).save(path)
    return path,runtime.record(path,relative,'image',width=value.shape[1],height=value.shape[0],**metadata)


class PackSheet:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{**{v:('IMAGE',) for v in ORDER},
        'camera_manifest':('STRING',{'multiline':True}),'job_id':('STRING',{'default':''}),
        'gutter':('INT',{'default':32,'min':0,'max':64,'step':32})}}
    RETURN_TYPES=('IMAGE','STRING');FUNCTION='pack';CATEGORY='Foundry View Bridge/Sheet';OUTPUT_NODE=True
    def pack(self,job_id,camera_manifest,gutter,**images):
        arrays={}
        for key,image in images.items():
            if image.shape[0]!=1:raise ValueError('One Blender image per sheet panel.')
            arrays[key]=image[0].detach().cpu().numpy()
        pixels,layout=pack_arrays(arrays,json.loads(camera_manifest),gutter)
        # The layout preserves original evaluated cameras plus their sheet-space K.
        path,receipt=save_pixels(job_id,'guide:sheet',pixels,calibration_status='packed_renderer_targets')
        target,relative=runtime.target(job_id,'sheet:layout','.json');atomic_json(target,layout)
        return {'ui':{'images':[runtime.preview_image(path,job_id)],'fvb_artifacts':[{
            'guide:sheet':receipt,'sheet:layout':runtime.record(target,relative,'sheet_layout')}],
            'text':[f"{layout['width']} × {layout['height']}; four {layout['panel_size']}-square camera frames, {gutter}px black gutters"]},
            'result':(torch.from_numpy(pixels).unsqueeze(0),json.dumps(layout))}


class SplitSheet:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'image':('IMAGE',),'job_id':('STRING',{'default':''})}}
    RETURN_TYPES=('IMAGE','IMAGE','IMAGE','IMAGE');RETURN_NAMES=ORDER
    FUNCTION='split';CATEGORY='Foundry View Bridge/Sheet';OUTPUT_NODE=True
    @classmethod
    def IS_CHANGED(cls,job_id,**kw):return signature(runtime.artifact(job_id,'sheet:layout')[1])
    def split(self,image,job_id):
        if image.shape[0]!=1:raise ValueError('One complete enhanced sheet is required.')
        path,layout_record=runtime.artifact(job_id,'sheet:layout')
        layout=json.loads(path.read_text(encoding='utf-8'))
        crops=split_array(image[0].detach().cpu().numpy(),layout)
        _,sheet_receipt=runtime.artifact(job_id,'enhanced:sheet')
        provenance={k:sheet_receipt[k] for k in ('raw_sheet_sha256','control_meta_sha256','control_sha256','mask_sha256','pixel_operation') if k in sheet_receipt}
        frames=[];receipts={};previews=[];outputs=[]
        for panel in layout['panels']:
            ident=panel['id'];camera=copy.deepcopy(panel['camera'])
            camera.update(calibration_status='inherited_target_unverified',sheet_crop=panel['rect'],
                layout_sha256=layout_record['sha256'],sheet_pixel_transform=[[1,0,-panel['rect'][0]],[0,1,-panel['rect'][1]],[0,0,1]])
            camera.update(enhanced_sheet_sha256=sheet_receipt['sha256'],**provenance)
            frames.append(camera)
            target,receipt=save_pixels(job_id,'enhanced:'+ident,crops[ident],camera_id=ident,
                target_render_sha256=camera['render_sha256'],calibration_status='inherited_target_unverified',
                sheet_crop=panel['rect'],layout_sha256=layout_record['sha256'],image_transforms=[],**provenance)
            receipts['enhanced:'+ident]=receipt;previews.append(runtime.preview_image(target,job_id))
            outputs.append(torch.from_numpy(crops[ident]).unsqueeze(0))
        target,relative=runtime.target(job_id,'enhanced:cameras','.json')
        atomic_json(target,{'schema':'fvb.cameras/1','frames':frames,'layout_sha256':layout_record['sha256']})
        receipts['enhanced:cameras']=runtime.record(target,relative,'cameras',calibration_status='inherited_target_unverified')
        return {'ui':{'images':previews,'fvb_artifacts':[receipts],
            'text':['All four crops saved. Review the images and Include toggles, then apply_views / Continue. Inherited cameras remain unverified.']},
            'result':tuple(outputs)}


class TiledReferenceVAE:
    """Delegate actual encoding to the installed VAE; preserve native tokenizer/latent semantics."""
    def __init__(self,vae):self.vae=vae
    def __getattr__(self,name):return getattr(self.vae,name)
    def encode(self,pixels):return self.vae.encode_tiled(pixels,tile_x=512,tile_y=512,overlap=64)


class QwenSheetEncode:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{
        'clip':('CLIP',),'vae':('VAE',),'image_1':('IMAGE',),'image_2':('IMAGE',),'image_3':('IMAGE',),
        'prompt':('STRING',{'multiline':True}),'negative_prompt':('STRING',{'multiline':True,'default':''}),
        'tiled_encode':('BOOLEAN',{'default':True})},'optional':{'image_'+str(i):('IMAGE',) for i in range(4,10)}}
    RETURN_TYPES=('CONDITIONING','CONDITIONING','LATENT');FUNCTION='encode';CATEGORY='Foundry View Bridge/Sheet'
    def encode(self,clip,vae,prompt,negative_prompt,tiled_encode,**images):
        from comfy_extras.nodes_qwen import TextEncodeQwenImage21
        canvas=images['image_1']
        if canvas.shape[0]!=1 or canvas.shape[1]!=canvas.shape[2] or canvas.shape[1]%32:
            raise ValueError('The first image must be the complete square sheet, in multiples of 32.')
        wrapped=TiledReferenceVAE(vae) if tiled_encode and not isinstance(vae,TiledReferenceVAE) else vae
        result=tuple(TextEncodeQwenImage21.execute(clip=clip,vae=wrapped,
            prompt=prompt,negative_prompt=negative_prompt,resolution=0,images=images))
        if tuple(result[2]['samples'].shape[-2:])!=(canvas.shape[1]//16,canvas.shape[2]//16):
            raise ValueError('The native encoder changed the sheet latent dimensions.')
        return result


class ViewSelection:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'include_'+v:('BOOLEAN',{'default':True}) for v in ORDER}}
    RETURN_TYPES=('STRING',);FUNCTION='select';CATEGORY='Foundry View Bridge/Sheet'
    def select(self,**flags):
        ids=[v for v in ORDER if flags['include_'+v]]
        if not ids:raise ValueError('Select at least one view; two views are supported.')
        return (json.dumps(ids),)


SHEET_NODES={'G3D_PackSheet':PackSheet,'G3D_SplitSheet':SplitSheet,'G3D_QwenSheetEncode':QwenSheetEncode,'G3D_ViewSelection':ViewSelection}


class ControlVAE:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'vae':('VAE',),'tiled_encode':('BOOLEAN',{'default':True})}}
    RETURN_TYPES=('VAE',);FUNCTION='wrap';CATEGORY='Foundry View Bridge/Sheet'
    def wrap(self,vae,tiled_encode):return (TiledReferenceVAE(vae) if tiled_encode and not isinstance(vae,TiledReferenceVAE) else vae,)


class ControlSheet:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'job_id':('STRING',{'default':''}),
        'layout_json':('STRING',),'control_mode':(['depth','canny'],),
        'mask_threshold':('FLOAT',{'default':.5,'min':.01,'max':.99}),
        'mask_dilation_px':('INT',{'default':0,'min':0,'max':16}),
        'canny_low_threshold':('FLOAT',{'default':.4,'min':.01,'max':.99}),
        'canny_high_threshold':('FLOAT',{'default':.8,'min':.01,'max':.99})},
        'optional':{v:('IMAGE',) for v in ORDER}}
    RETURN_TYPES=('IMAGE','MASK');FUNCTION='pack';CATEGORY='Foundry View Bridge/Sheet';OUTPUT_NODE=True
    @classmethod
    def IS_CHANGED(cls,job_id,control_mode,**kw):
        keys=['cameras']+['render:'+v+':'+kind for v in ORDER for kind in (('depth','alpha') if control_mode=='depth' else ('alpha',))]
        return signature({k:runtime.artifact(job_id,k)[1] for k in keys})
    def pack(self,job_id,layout_json,control_mode,mask_threshold,mask_dilation_px,canny_low_threshold,canny_high_threshold,**edges):
        from .control import control_arrays
        layout=json.loads(layout_json);camera_path,camera_receipt=runtime.artifact(job_id,'cameras')
        registered={c['id']:c for c in json.loads(camera_path.read_text())['frames']}
        sources={};maps={};alphas={}
        for panel in layout['panels']:
            ident=panel['id']
            if panel['camera']!=registered[ident]:raise ValueError('Control layout camera differs from registered render: '+ident)
            for kind in (('depth','alpha') if control_mode=='depth' else ('alpha',)):
                key='render:'+ident+':'+kind;path,receipt=runtime.artifact(job_id,key);sources[key]=receipt
                with Image.open(path) as im:value=np.asarray(im.convert('RGB'),np.float32)/255
                (maps if kind=='depth' else alphas)[ident]=value
            if control_mode=='depth':
                if registered[ident].get('diagnostic_encoding',{}).get('depth')!='blender_linear_near_white_v1':
                    raise ValueError('Controlled depth needs a registered render with explicit depth encoding; preserve legacy checkpoints.')
            else:
                if ident not in edges or edges[ident].shape[0]!=1:raise ValueError('One native Canny result per camera is required.')
                maps[ident]=edges[ident][0].detach().cpu().numpy()
        image,mask=control_arrays(maps,alphas,layout,mask_threshold,mask_dilation_px)
        receipts={};previews=[]
        for key,pixels in [('control:sheet',image),('control:mask',np.repeat(mask[:,:,None],3,axis=2))]:
            path,receipt=save_pixels(job_id,key,pixels,encoding='prepared_rgb8',camera_ids=list(ORDER));receipts[key]=receipt;previews.append(runtime.preview_image(path,job_id))
        metadata=dict(schema='fvb.control/1',mode=control_mode,depth_encoding='blender_linear_near_white_v1' if control_mode=='depth' else None,
            mask_polarity='white_regenerate',mask_threshold=mask_threshold,mask_dilation_px=mask_dilation_px,
            canny_thresholds=[canny_low_threshold,canny_high_threshold] if control_mode=='canny' else None,
            camera_manifest_sha256=camera_receipt['sha256'],layout=layout,sources=sources,
            control_sha256=receipts['control:sheet']['sha256'],mask_sha256=receipts['control:mask']['sha256'])
        path,relative=runtime.target(job_id,'control:metadata','.json');atomic_json(path,metadata)
        receipts['control:metadata']=runtime.record(path,relative,'control_metadata')
        return {'ui':{'images':previews,'fvb_artifacts':[receipts],'text':['Structural map and RGB-channel foreground mask registered to all four cameras.']},
                'result':(torch.from_numpy(image).unsqueeze(0),torch.from_numpy(mask).unsqueeze(0))}


class LoadControl:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'job_id':('STRING',{'default':''}),'canvas':('IMAGE',)}}
    RETURN_TYPES=('IMAGE','MASK');FUNCTION='load';CATEGORY='Foundry View Bridge/Sheet'
    @classmethod
    def IS_CHANGED(cls,job_id,**kw):
        records={k:runtime.artifact(job_id,k)[1] for k in ('control:sheet','control:mask','control:metadata','sheet:layout','cameras')}
        meta=json.loads(runtime.artifact(job_id,'control:metadata')[0].read_text())
        records.update({k:runtime.artifact(job_id,k)[1] for k in meta['sources']})
        return signature(records)
    def load(self,job_id,canvas):
        meta=json.loads(runtime.artifact(job_id,'control:metadata')[0].read_text())
        layout=json.loads(runtime.artifact(job_id,'sheet:layout')[0].read_text())
        if runtime.artifact(job_id,'cameras')[1]['sha256']!=meta['camera_manifest_sha256']:
            raise ValueError('Control camera registration is stale; rebuild the sheet from the registered cameras.')
        for key,source in meta['sources'].items():
            if runtime.artifact(job_id,key)[1]['sha256']!=source['sha256']:
                raise ValueError('Control source registration is stale: '+key)
        if meta['layout']!=layout or canvas.shape[0]!=1 or tuple(canvas.shape[1:3])!=(layout['height'],layout['width']):
            raise ValueError('Control and first reference canvas/layout do not match.')
        values=[]
        for key,expected in [('control:sheet',meta['control_sha256']),('control:mask',meta['mask_sha256'])]:
            path,receipt=runtime.artifact(job_id,key)
            if receipt['sha256']!=expected:raise ValueError('Control metadata hash mismatch: '+key)
            with Image.open(path) as im:value=np.asarray(im.convert('RGB'),np.float32)/255
            if value.shape!=(layout['height'],layout['width'],3):raise ValueError('Control dimensions differ from canvas.')
            values.append(value)
        return torch.from_numpy(values[0]).unsqueeze(0),torch.from_numpy(values[1][:,:,0]).unsqueeze(0)


class FinalizeSheet:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'job_id':('STRING',{'default':''}),'image':('IMAGE',),
        'restore_black_gutters':('BOOLEAN',{'default':True})}}
    RETURN_TYPES=('IMAGE',);FUNCTION='save';CATEGORY='Foundry View Bridge/Sheet';OUTPUT_NODE=True
    @classmethod
    def IS_CHANGED(cls,job_id,**kw):return LoadControl.IS_CHANGED(job_id)
    def save(self,job_id,image,restore_black_gutters):
        from .control import restore_gutters
        if image.shape[0]!=1:raise ValueError('One generated sheet is required.')
        layout_path,layout_receipt=runtime.artifact(job_id,'sheet:layout');layout=json.loads(layout_path.read_text())
        raw=image[0].detach().cpu().numpy();split_array(raw,layout)
        meta_path,meta_receipt=runtime.artifact(job_id,'control:metadata');meta=json.loads(meta_path.read_text())
        raw_path,raw_receipt=save_pixels(job_id,'enhanced:sheet_raw',raw,calibration_status='inherited_target_unverified')
        final=restore_gutters(raw,layout) if restore_black_gutters else raw
        path,receipt=save_pixels(job_id,'enhanced:sheet',final,calibration_status='inherited_target_unverified',
            layout_sha256=layout_receipt['sha256'],control_meta_sha256=meta_receipt['sha256'],
            control_sha256=meta['control_sha256'],mask_sha256=meta['mask_sha256'],raw_sheet_sha256=raw_receipt['sha256'],
            pixel_operation='restore_fixed_gutters_only' if restore_black_gutters else 'identity')
        return {'ui':{'images':[runtime.preview_image(path,job_id)],'fvb_artifacts':[{'enhanced:sheet_raw':raw_receipt,'enhanced:sheet':receipt}],
            'text':['Raw sheet preserved; only fixed separator pixels restored. Enhanced camera fidelity remains unverified.']},
            'result':(torch.from_numpy(final).unsqueeze(0),)}


SHEET_NODES.update(G3D_ControlVAE=ControlVAE,G3D_ControlSheet=ControlSheet,G3D_LoadControl=LoadControl,G3D_FinalizeSheet=FinalizeSheet)
