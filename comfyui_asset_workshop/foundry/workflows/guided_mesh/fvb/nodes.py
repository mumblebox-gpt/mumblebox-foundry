"""Stateless native Comfy adapters for the isolated, explicitly started lab job."""
import json
import copy
import time
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from . import runtime
from .camera_math import validate_camera, rig, resize_camera, canonical_anchor
from .contracts import defaults, sheet_defaults, view_records, selected_views
from .journal import atomic_json, digest, signature


def strings(**defaults_by_name):
    return {key:('STRING',{'default':value}) for key,value in defaults_by_name.items()}


def load_pixels(path):
    with Image.open(path) as im:
        rgba=np.asarray(im.convert('RGBA')).astype(np.float32)/255
    return torch.from_numpy(rgba.copy()).unsqueeze(0)


class LoadImage:
    @classmethod
    def INPUT_TYPES(cls):return {'required':strings(job_id='',artifact_key='original')}
    RETURN_TYPES=('IMAGE','MASK'); FUNCTION='load'; CATEGORY='Foundry View Bridge/Checkpoints'
    def load(self,job_id,artifact_key):
        path,_=runtime.artifact(job_id,artifact_key); value=load_pixels(path)
        return value,1-value[...,3]
    @classmethod
    def IS_CHANGED(cls,**kw):
        return signature(runtime.artifact(kw['job_id'],kw['artifact_key'])[1])


class ResizeReference:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'image':('IMAGE',),'size':('INT',{'default':1024,'min':256,'max':1024,'step':32})}}
    RETURN_TYPES=('IMAGE',); FUNCTION='resize'; CATEGORY='Foundry View Bridge/References'
    def resize(self,image,size):
        if image.shape[0]!=1:raise ValueError('One image per ordered reference slot.')
        pixels=image[0].detach().cpu().numpy()
        rgb=pixels[:,:,:3]*(pixels[:,:,3:4] if pixels.shape[-1]==4 else 1)
        im=Image.fromarray((rgb.clip(0,1)*255).round().astype('uint8'))
        im.thumbnail((size,size),Image.Resampling.LANCZOS)
        canvas=Image.new('RGB',(size,size)); canvas.paste(im,((size-im.width)//2,(size-im.height)//2))
        return (torch.from_numpy(np.asarray(canvas).copy().astype(np.float32)/255).unsqueeze(0),)


class PrepareImage:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'image':('IMAGE',),'bg_removal_model':('BACKGROUND_REMOVAL',),
        'mode':(['fit','preserve','pixal_fit'],),'padding':('FLOAT',{'default':1.1,'min':1,'max':2})}}
    RETURN_TYPES=('IMAGE','MASK'); FUNCTION='prepare'; CATEGORY='Foundry View Bridge/References'
    def prepare(self,image,bg_removal_model,mode,padding):
        from comfy_extras.nodes_bg_removal import RemoveBackground
        if image.shape[0]!=1:raise ValueError('Prepare one view at a time.')
        # Generated RGBA can be almost opaque everywhere. Camera frames require
        # an actual foreground matte; incidental alpha is not a ready cutout.
        alpha=image[...,3] if mode in ('fit','pixal_fit') and image.shape[-1]==4 and bool((image[...,3]<.999).any()) else RemoveBackground.execute(bg_removal_model,image[...,:3])[0]
        if alpha.shape!=image.shape[:3] or not bool((alpha>.01).any()):
            raise ValueError('Empty or mismatched foreground mask.')
        rgba=torch.cat([image[...,:3],alpha.unsqueeze(-1)],dim=-1)
        if mode=='preserve':
            if image.shape[1]!=image.shape[2] or image.shape[1] not in (1024,2048):raise ValueError('Keep the complete supported square camera frame.')
            return rgba,1-alpha
        im=Image.fromarray((rgba[0].detach().cpu().numpy().clip(0,1)*255).round().astype('uint8'),'RGBA')
        if mode=='pixal_fit':
            foreground=np.argwhere(np.asarray(im.getchannel('A'))>204)
            if not len(foreground):raise ValueError('No confident foreground for Pixal preprocessing.')
            x0,y0,x1,y1=foreground[:,1].min(),foreground[:,0].min(),foreground[:,1].max(),foreground[:,0].max()
            center=((x0+x1)/2,(y0+y1)/2);span=int(max(x1-x0,y1-y0)*padding)
            if span<2:raise ValueError('Foreground is too small for Pixal preprocessing.')
            im=im.crop((center[0]-span//2,center[1]-span//2,center[0]+span//2,center[1]+span//2)).resize((1024,1024),Image.Resampling.LANCZOS)
            result=torch.from_numpy(np.asarray(im).copy().astype(np.float32)/255).unsqueeze(0)
            return result,1-result[...,3]
        bbox=im.getchannel('A').getbbox()
        if bbox is None:raise ValueError('Empty source foreground.')
        cropped=im.crop(bbox); span=max(cropped.size)*padding
        dims=[max(1,round(v*1024/span)) for v in cropped.size]
        cropped=cropped.resize(dims,Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(1024,1024)); canvas.paste(cropped,((1024-dims[0])//2,(1024-dims[1])//2))
        result=torch.from_numpy(np.asarray(canvas).copy().astype(np.float32)/255).unsqueeze(0)
        return result,1-result[...,3]


class SaveImage:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'image':('IMAGE',),**strings(job_id='',artifact_key='')}}
    RETURN_TYPES=('IMAGE',); FUNCTION='save'; CATEGORY='Foundry View Bridge/Checkpoints'; OUTPUT_NODE=True
    def save(self,image,job_id,artifact_key):
        if image.shape[0]!=1 or not bool(torch.isfinite(image).all()):raise ValueError('Expected one finite image.')
        meta=dict(width=int(image.shape[2]),height=int(image.shape[1]))
        if artifact_key.startswith(('enhanced:','prepared:')) and artifact_key!='enhanced:sheet':
            view_id=artifact_key.split(':',1)[1]; cameras=json.loads(runtime.artifact(job_id,'cameras')[0].read_text(encoding='utf-8'))['frames']
            camera=next(c for c in cameras if c['id']==view_id)
            if meta['width']!=camera['width'] or meta['height']!=camera['height']:raise ValueError('Generated image dimensions no longer match the camera.')
            meta.update(camera_id=view_id,target_render_sha256=camera['render_sha256'],calibration_status='inherited_target_unverified',image_transforms=[])
        if artifact_key=='enhanced:sheet':
            layout=json.loads(runtime.artifact(job_id,'sheet:layout')[0].read_text(encoding='utf-8'))
            if (meta['width'],meta['height'])!=(layout['width'],layout['height']):
                raise ValueError('Enhanced sheet dimensions differ from the fixed layout; no automatic resize.')
            meta.update(calibration_status='inherited_target_unverified',layout_sha256=runtime.artifact(job_id,'sheet:layout')[1]['sha256'])
        path,relative=runtime.target(job_id,artifact_key,'.png')
        pixels=(image[0].detach().cpu().numpy().clip(0,1)*255).round().astype('uint8')
        Image.fromarray(pixels).save(path)
        receipt=runtime.record(path,relative,'image',**meta)
        return {'ui':{'images':[runtime.preview_image(path,job_id)],'fvb_artifacts':[{artifact_key:receipt}]},'result':(image,)}
    @classmethod
    def IS_CHANGED(cls,job_id,artifact_key,**kw):
        if artifact_key=='enhanced:sheet':
            return signature(runtime.artifact(job_id,'sheet:layout')[1])
        if artifact_key.startswith(('enhanced:','prepared:')):
            return signature(runtime.artifact(job_id,'cameras')[1])
        return None


class SaveMesh:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'mesh':('MESH',),**strings(job_id='',artifact_key='')}}
    RETURN_TYPES=('MESH','FILE_3D'); FUNCTION='save'; CATEGORY='Foundry View Bridge/Checkpoints'; OUTPUT_NODE=True
    def save(self,mesh,job_id,artifact_key):
        from comfy_api.latest._util.geometry_types import File3D
        from comfy_extras.nodes_mesh_postprocess import get_mesh_batch_item
        from comfy_extras.nodes_save_3d import mesh_item_to_glb_bytes
        if mesh.vertices.shape[0]!=1:raise ValueError('One asset per mesh checkpoint.')
        # Native valid-count helper avoids serializing batch padding as real geometry.
        vertices,faces,*_=get_mesh_batch_item(mesh,0)
        vertices=vertices.detach().cpu().numpy(); faces=faces.detach().cpu().numpy()
        if not np.isfinite(vertices).all() or not len(vertices) or not len(faces):raise ValueError('Invalid mesh checkpoint.')
        payload={'vertices':vertices,'faces':faces}
        if mesh.vertex_colors is not None:
            payload['vertex_colors']=mesh.vertex_colors[0,:len(vertices)].detach().cpu().numpy()
        if artifact_key=='proxy' and 'vertex_colors' not in payload and runtime.journal().read(job_id)['spec'].get('guide_material','source_color')!='neutral_clay':
            raise ValueError('The selected RGB-guide route requires a colored proxy.')
        path,relative=runtime.target(job_id,artifact_key,'.npz')
        np.savez(path,**payload)
        glb,glbrel=runtime.target(job_id,artifact_key,'.glb')
        glb.write_bytes(mesh_item_to_glb_bytes(mesh,0))
        runtime.preview_file(glb,job_id)
        receipts={artifact_key:runtime.record(path,relative,'mesh',vertex_count=len(vertices),face_count=len(faces),frame='glTF Y-up',physical_scale_known=False),
                  artifact_key+':glb':runtime.record(glb,glbrel,'glb',physical_scale_known=False)}
        return {'ui':{'fvb_artifacts':[receipts],'text':[f'{artifact_key}: {len(vertices)} vertices / {len(faces)} triangles; uncalibrated physical scale']},'result':(mesh,File3D(str(glb),'glb'))}


class LoadMesh:
    @classmethod
    def INPUT_TYPES(cls):return {'required':strings(job_id='',artifact_key='reconstruction')}
    RETURN_TYPES=('MESH',); FUNCTION='load'; CATEGORY='Foundry View Bridge/Checkpoints'
    def load(self,job_id,artifact_key):
        from comfy_api.latest._util.geometry_types import MESH
        data=np.load(runtime.artifact(job_id,artifact_key)[0],allow_pickle=False)
        kwargs=dict(vertices=torch.from_numpy(data['vertices'].copy()).unsqueeze(0),faces=torch.from_numpy(data['faces'].copy()).unsqueeze(0))
        if 'vertex_colors' in data:kwargs['vertex_colors']=torch.from_numpy(data['vertex_colors'].copy()).unsqueeze(0)
        return (MESH(**kwargs),)
    @classmethod
    def IS_CHANGED(cls,**kw):return runtime.artifact(kw['job_id'],kw['artifact_key'])[1]['sha256']


class ReadCameras:
    @classmethod
    def INPUT_TYPES(cls):return {'required':strings(job_id=''),'optional':{'selected_only':('BOOLEAN',{'default':False}),'source':(['render','enhanced'],)}}
    RETURN_TYPES=('STRING',); FUNCTION='read'; CATEGORY='Foundry View Bridge/Cameras'
    def read(self,job_id,selected_only=False,source='render'):
        cameras=json.loads(runtime.artifact(job_id,'enhanced:cameras' if source=='enhanced' else 'cameras')[0].read_text(encoding='utf-8'))['frames']
        spec=runtime.journal().read(job_id)['spec']
        expected=[v['id'] for v in view_records(spec)]
        if [c['id'] for c in cameras]!=expected:raise ValueError('Camera order changed relative to the selected views.')
        for camera in cameras:validate_camera(camera)
        if source=='enhanced':
            job=runtime.journal().read(job_id)
            from .contracts import effective_image_key
            for camera in cameras:
                key=effective_image_key(spec,camera['id'])
                if key in job['artifacts']:
                    _,record=runtime.artifact(job_id,key);camera['conditioning_image_sha256']=record['sha256']
                if camera['id'] in spec.get('repair_requests',{}):
                    _,report=runtime.artifact(job_id,'repair_report:'+camera['id']);camera['repair_report_sha256']=report['sha256']
        if selected_only:
            ids={v['id'] for v in selected_views(spec)};cameras=[c for c in cameras if c['id'] in ids]
        return (json.dumps(cameras),)
    @classmethod
    def IS_CHANGED(cls,job_id,selected_only=False,source='render'):
        from .journal import signature
        job=runtime.journal().read(job_id)
        return signature(dict(requests=job['spec'].get('repair_requests',{}),repairs={k:v for k,v in job['artifacts'].items() if k.startswith(('corrected:','repair_report:'))},camera=job['artifacts'].get('enhanced:cameras' if source=='enhanced' else 'cameras'),
            selection=job['spec'].get('selected_view_ids',[]) if selected_only else None))


class PixalViews:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'clip_vision_model':('CLIP_VISION',),'camera_manifest':('STRING',{'multiline':True})},
        'optional':{'frame_mode':(['legacy_absolute','canonical_anchor'],{'default':'legacy_absolute'}),
                    **{'view_'+str(i):('IMAGE',) for i in range(12)}}}
    RETURN_TYPES=('CONDITIONING','CONDITIONING'); FUNCTION='condition'; CATEGORY='Foundry View Bridge/Cameras'
    def condition(self,clip_vision_model,camera_manifest,frame_mode='legacy_absolute',**views):
        from comfy_extras.nodes_trellis2 import _build_pixal3d_conditioning
        cameras=json.loads(camera_manifest)
        if not cameras or set(views)!={'view_'+str(i) for i in range(len(cameras))}:
            raise ValueError('Every image needs exactly one ordered camera; no dropped views.')
        frame=None
        if frame_mode=='canonical_anchor':cameras,frame=canonical_anchor(cameras)
        elif frame_mode!='legacy_absolute':raise ValueError('Unknown camera frame convention.')
        images=[]
        conditioning_cameras=[]
        for i,camera in enumerate(cameras):
            validate_camera(camera); value=views['view_'+str(i)]
            if value.shape[0]!=1 or tuple(value.shape[1:3])!=(camera['height'],camera['width']):raise ValueError('Prepared input frame does not match its camera.')
            if camera['width']!=1024:
                value=torch.nn.functional.interpolate(value.movedim(-1,1),size=(1024,1024),mode='bilinear',align_corners=False).movedim(1,-1)
            conditioning_cameras.append(resize_camera(camera,1024))
            images.append(value[...,:3]*(value[...,3:4] if value.shape[-1]==4 else 1))
        # These exact tensors, not just an adjacent JSON, reach the projection builder.
        matrices=torch.tensor([c['c2w'] for c in cameras],dtype=torch.float32)
        fovs=torch.tensor([c['fov_x_rad'] for c in cameras],dtype=torch.float32)
        result=tuple(_build_pixal3d_conditioning(clip_vision_model,torch.cat(images),matrices,fovs,torch.ones(1),num_views=len(cameras)))
        for conditioning in result:
            conditioning[0][1]['fvb_conditioning_cameras']=conditioning_cameras
            if frame is not None:conditioning[0][1]['fvb_reconstruction_frame']=frame
        return result


class RestoreReconstructionFrame:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'mesh':('MESH',),'camera_manifest':('STRING',{'multiline':True}),**strings(job_id='')}}
    RETURN_TYPES=('MESH',);FUNCTION='restore';CATEGORY='Foundry View Bridge/Cameras'
    def restore(self,mesh,camera_manifest,job_id):
        _,frame=canonical_anchor(json.loads(camera_manifest))
        result=copy.copy(mesh)
        matrix=torch.as_tensor(frame['conditioning_mesh_to_world_mesh'],dtype=mesh.vertices.dtype,device=mesh.vertices.device)
        result.vertices=mesh.vertices@matrix[:3,:3].T+matrix[:3,3]
        for name in ('normals','tangents'):
            value=getattr(mesh,name,None)
            if value is not None:
                moved=value[...,:3]@matrix[:3,:3].to(value).T
                moved=torch.nn.functional.normalize(moved,dim=-1)
                setattr(result,name,torch.cat([moved,value[...,3:]],dim=-1) if value.shape[-1]>3 else moved)
        path,relative=runtime.target(job_id,'reconstruction:frame','.json');atomic_json(path,frame)
        receipt=runtime.record(path,relative,'json',anchor_id=frame['anchor_id'],mode=frame['mode'])
        return {'ui':{'fvb_artifacts':[{'reconstruction:frame':receipt}]},'result':(result,)}


class RecordValue:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'value':('FLOAT',),**strings(job_id='',artifact_key='')}}
    RETURN_TYPES=('FLOAT',); FUNCTION='save'; CATEGORY='Foundry View Bridge/Checkpoints'; OUTPUT_NODE=True
    def save(self,value,job_id,artifact_key):
        path,relative=runtime.target(job_id,artifact_key,'.json'); atomic_json(path,{'value':value,'kind':'estimated_source_horizontal_fov_deg'})
        return {'ui':{'fvb_artifacts':[{artifact_key:runtime.record(path,relative,'json')}]},'result':(value,)}


class SaveFile:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'model_3d':('FILE_3D',),**strings(job_id='',artifact_key='textured')}}
    RETURN_TYPES=('FILE_3D',); FUNCTION='save'; CATEGORY='Foundry View Bridge/Checkpoints'; OUTPUT_NODE=True
    def save(self,model_3d,job_id,artifact_key):
        path,relative=runtime.target(job_id,artifact_key,'.glb'); model_3d.save_to(str(path))
        runtime.preview_file(path,job_id)
        return {'ui':{'fvb_artifacts':[{artifact_key:runtime.record(path,relative,'glb')}]},'result':(model_3d,)}


class RenderProxy:
    @classmethod
    def INPUT_TYPES(cls):return {'required':strings(job_id='')}
    RETURN_TYPES=('STRING',); FUNCTION='render'; CATEGORY='Foundry View Bridge/Cameras'; OUTPUT_NODE=True
    def render(self,job_id):
        import comfy.model_management as mm
        from custom_nodes.comfyui_asset_workshop.pipeline_workers.worker_process import OwnedWorker
        store,job=runtime.context(job_id); spec=job['spec']; cfg=runtime.configuration()
        proxy,metadata=runtime.artifact(job_id,'proxy'); arrays=np.load(proxy,allow_pickle=False)
        cameras=rig([arrays['vertices'].min(0),arrays['vertices'].max(0)],views=view_records(spec),fov=spec['horizontal_fov_deg'],margin=spec['orbit_margin'],yaw=spec['proxy_yaw_deg'],pitch=spec.get('proxy_pitch_deg',0),roll=spec.get('proxy_roll_deg',0),size=spec['render_size'])
        output=store.folder(job_id)/'stages'/job['request_id']/'blender'
        output.mkdir(parents=True)
        render_request=dict(proxy=str(proxy),proxy_sha256=metadata['sha256'],original_sha256=job['artifacts']['original']['sha256'],
            guide_material=spec['guide_material'],proxy_cleanup=spec['proxy_cleanup'],
            guide_smooth_factor=spec['guide_smooth_factor'],guide_smooth_iterations=spec['guide_smooth_iterations'],
            cameras=cameras,output=str(output),samples=spec['render_samples'],threads=spec['render_threads'],
            radius=cameras[0]['distance']*np.sin(spec['horizontal_fov_deg']*np.pi/360)/spec['orbit_margin'])
        request_path=output/'request.json'; atomic_json(request_path,render_request)
        command=[cfg['blender'],'--background','--factory-startup','--disable-autoexec','--python',str(Path(__file__).with_name('blender_render.py')),'--',str(request_path)]
        with (output/'worker.log').open('w',encoding='utf-8') as log:
            worker=OwnedWorker(command,log)
            try:
                started=time.monotonic()
                while worker.process.poll() is None:
                    mm.throw_exception_if_processing_interrupted()
                    if time.monotonic()-started>1200:raise TimeoutError('Blender guide stage exceeded 20 minutes; saved partial diagnostics retained.')
                    time.sleep(.25)
                if worker.process.returncode!=0:raise RuntimeError('Blender renderer failed. See '+str(output/'worker.log'))
            except BaseException:
                if worker.process.poll() is None:worker.stop()
                raise
            finally:worker.close()
        manifest=output/'cameras.json'; data=json.loads(manifest.read_text(encoding='utf-8'))
        receipts={'cameras':runtime.record(manifest,manifest.relative_to(store.folder(job_id)).as_posix(),'cameras')}
        previews=[]
        for camera in data['frames']:
            validate_camera(camera); ident=camera['id']; path=output/camera['render_file']
            receipts['render:'+ident]=runtime.record(path,path.relative_to(store.folder(job_id)).as_posix(),'image',camera_id=ident,calibration_status='renderer_exact')
            previews.append(runtime.preview_image(path,job_id))
            for name,filename in camera['diagnostics'].items():
                path=output/filename; receipts['render:'+ident+':'+name]=runtime.record(path,path.relative_to(store.folder(job_id)).as_posix(),'image')
        return {'ui':{'fvb_artifacts':[receipts],'images':previews,'text':['Exact renderer cameras saved; enhancement has not run.']},'result':(str(manifest),)}


class ReviewControl:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{
        'operation':(['readiness','create','start','continue','resume','status','cancel','apply_views'],{'default':'readiness'}),
        'settings_json':('STRING',{'multiline':True,'default':json.dumps(sheet_defaults(),indent=2)}),
        'job_id':('STRING',{'default':''})},'optional':{'view_selection':('STRING',)}}
    RETURN_TYPES=('STRING',); FUNCTION='control'; CATEGORY='Foundry View Bridge'; OUTPUT_NODE=True
    def control(self,operation,settings_json,job_id,view_selection=None):
        from .service import service
        spec=json.loads(settings_json)
        if view_selection is not None:spec['selected_view_ids']=json.loads(view_selection)
        result=service().control_from_node(operation,spec,job_id)
        return {'ui':{'text':[json.dumps(result,ensure_ascii=False,indent=2)]},'result':(json.dumps(result),)}
    @classmethod
    def IS_CHANGED(cls,**kw):return float('nan')


NODE_CLASS_MAPPINGS={
    'G3D_LoadImage':LoadImage,'G3D_ResizeReference':ResizeReference,'G3D_PrepareImage':PrepareImage,
    'G3D_SaveImage':SaveImage,'G3D_SaveMesh':SaveMesh,'G3D_LoadMesh':LoadMesh,'G3D_ReadCameras':ReadCameras,
    'G3D_PixalViews':PixalViews,'G3D_RestoreReconstructionFrame':RestoreReconstructionFrame,'G3D_RecordValue':RecordValue,'G3D_SaveFile':SaveFile,
    'G3D_RenderProxy':RenderProxy,'G3D_ReviewControl':ReviewControl,
}
NODE_DISPLAY_NAME_MAPPINGS={key:'FVB · '+key.removeprefix('G3D_') for key in NODE_CLASS_MAPPINGS}

from .sheet_nodes import SHEET_NODES
NODE_CLASS_MAPPINGS.update(SHEET_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update({key:'FVB · '+key.removeprefix('G3D_') for key in SHEET_NODES})
from .repair_nodes import REPAIR_NODES
NODE_CLASS_MAPPINGS.update(REPAIR_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update({key:'FVB · '+key.removeprefix('G3D_') for key in REPAIR_NODES})
from .proxy_nodes import PROXY_NODES
NODE_CLASS_MAPPINGS.update(PROXY_NODES)
NODE_DISPLAY_NAME_MAPPINGS.update({key:'FVB · '+key.removeprefix('G3D_') for key in PROXY_NODES})
