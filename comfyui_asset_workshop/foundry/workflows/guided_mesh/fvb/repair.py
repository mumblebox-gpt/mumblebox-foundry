"""Protected pixel compositing and immutable native-mask-editor inputs. No inference."""
import copy
import json
import shutil
import uuid
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
from .journal import atomic_json, digest
from .contracts import input_name, validate_spec


def allowed_mask(source,painted,margin_px):
    source=np.asarray(source);painted=np.asarray(painted)
    if source.ndim!=3 or source.shape[-1]!=4 or painted.shape!=source.shape or source.dtype!=np.uint8 or painted.dtype!=np.uint8:
        raise ValueError('The native painted PNG must match the complete RGBA camera frame.')
    if not np.array_equal(source[:,:,:3],painted[:,:,:3]):raise ValueError('Painted image RGB differs from its immutable editor source.')
    foreground=Image.fromarray((source[:,:,3]>=128).astype('uint8')*255)
    if margin_px:foreground=foreground.filter(ImageFilter.MinFilter(2*margin_px+1))
    mask=(painted[:,:,3]<128)&(np.asarray(foreground)>0)
    if not mask.any():raise ValueError('Paint a nonempty region inside the protected object outline.')
    return mask


def composite(source,candidate,mask,feather_px):
    source=np.asarray(source);candidate=np.asarray(candidate)
    if candidate.shape[:2]!=source.shape[:2] or candidate.ndim!=3 or candidate.shape[-1] not in (3,4):
        raise ValueError('Repair candidate changed the camera frame; no crop or resize is permitted.')
    weights=Image.fromarray(mask.astype('uint8')*255)
    if feather_px:weights=weights.filter(ImageFilter.GaussianBlur(feather_px))
    weights=np.asarray(weights,np.float32)/255*mask
    out=source.copy()
    rgb=np.round(source[:,:,:3]*(1-weights[:,:,None])+candidate[:,:,:3]*weights[:,:,None]).clip(0,255).astype('uint8')
    out[mask,:3]=rgb[mask]
    return out


def image(path):
    with Image.open(path) as im:return np.asarray(im.convert('RGBA')).copy()


def checked_artifact(store,job,key):
    record=job['artifacts'].get(key)
    if not record:raise ValueError('Checkpoint not available: '+key)
    path=store.artifact_path(job['id'],record['path'])
    if not path.is_file() or digest(path)!=record['sha256']:raise ValueError('Checkpoint changed: '+key)
    return path,record


def prepare_editor(store,job,input_root,view_id):
    input_root=Path(input_root).resolve()
    if not job['spec'].get('repair_enabled') or job['status']=='running':raise ValueError('Use a stopped repair workflow at a prepared checkpoint.')
    if view_id not in ('front','right','back','left'):raise ValueError('Choose a sheet view.')
    key='corrected:'+view_id if view_id in job['spec']['repair_requests'] and 'repair:'+view_id in job['completed'] else 'prepared:'+view_id
    source,record=checked_artifact(store,job,key);_,camera=checked_artifact(store,job,'enhanced:cameras')
    token=uuid.uuid4().hex;relative='repair-editor/'+token+'/source.png';dest=store.artifact_path(job['id'],relative);dest.parent.mkdir(parents=True)
    shutil.copy2(source,dest)
    pixels=image(dest);pixels[:,:,3]=255
    name='FoundryViewBridgeRepair/'+job['id']+'/'+token+'.png';editor=(Path(input_root)/name).resolve();editor.parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(pixels).save(editor)
    ticket=dict(id=token,view_id=view_id,source_key=key,source={'path':relative,'sha256':record['sha256'],'kind':'image','status':'complete'},
        camera_sha256=camera['sha256'],input_name=name,editor_sha256=digest(editor))
    atomic_json(dest.parent/'ticket.json',ticket)
    return dict(ticket_id=token,view_id=view_id,input_name=name,source_ref=dict(filename=editor.name,subfolder=editor.parent.relative_to(Path(input_root)).as_posix(),type='input'),
        message='Open this native LoadImage in Mask Editor, paint, Save to Node, copy its filename, then apply_repair. No inference was scheduled.')


def apply_request(store,job,input_root,ticket_id,mask_filename,controls):
    if job['status']=='running':raise ValueError('Finish or stop the owned stage before applying a correction.')
    if len(ticket_id)!=32 or any(c not in '0123456789abcdef' for c in ticket_id):raise ValueError('Prepare a native editor source first.')
    p=store.artifact_path(job['id'],'repair-editor/'+ticket_id+'/ticket.json');ticket=json.loads(p.read_text(encoding='utf-8'))
    view=ticket['view_id'];source,record=checked_artifact(store,job,ticket['source_key'])
    _,cam=checked_artifact(store,job,'enhanced:cameras')
    current_key='corrected:'+view if view in job['spec']['repair_requests'] and 'repair:'+view in job['completed'] else 'prepared:'+view
    if current_key!=ticket['source_key']:raise ValueError('A newer correction exists; prepare its current editor source.')
    if cam['sha256']!=ticket['camera_sha256'] or record['sha256']!=ticket['source']['sha256']:
        raise ValueError('Editor source or camera is stale; prepare the current view again.')
    if mask_filename.endswith(' [input]'):mask_filename=mask_filename[:-8]
    name=input_name(mask_filename);root=Path(input_root).resolve();painted_path=(root/name).resolve()
    if not painted_path.is_relative_to(root) or not painted_path.is_file():raise ValueError('Painted file must be inside Comfy input.')
    source_path=store.artifact_path(job['id'],ticket['source']['path'])
    if digest(source_path)!=record['sha256']:raise ValueError('Immutable editor source changed.')
    settings={**controls,'source_sha256':record['sha256'],'camera_sha256':cam['sha256']}
    requests={**job['spec']['repair_requests'],view:settings}
    validate_spec({**job['spec'],'repair_requests':requests},require_input=False)
    pixels=image(painted_path);allowed_mask(image(source_path),pixels,settings['margin_px'])
    # Capture new inputs under a unique revision, never reference a mutable editor file.
    relative='repair-inputs/'+uuid.uuid4().hex+'/mask.png';dest=store.artifact_path(job['id'],relative);dest.parent.mkdir(parents=True)
    Image.fromarray(pixels).save(dest)
    artifacts=copy.deepcopy(job['artifacts'])
    artifacts['repair_source:'+view]=ticket['source']
    artifacts['repair_mask:'+view]=dict(path=relative,sha256=digest(dest),kind='image',status='complete')
    return requests,artifacts
