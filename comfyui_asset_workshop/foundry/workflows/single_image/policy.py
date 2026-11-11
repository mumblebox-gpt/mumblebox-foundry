"""Single-image cache lineage and portable production credits."""
import json
from pathlib import Path
from ..image_to_3d.runs import signature
from ..image_to_3d.graph import STAGE_KEYS,DEPENDENCIES
from ..image_to_3d.definition import texture_sampling_settings
from ...artifacts import digest,owned_path
from ...quad_policy import fingerprint_fields, manifest_resources
from .definition import MOGE_MODEL_KEY

def fingerprint(run,stage,input_root):
    if stage=='geometry':
        ref=run['references'][0]
        source=[ref['filename'],digest(owned_path(input_root,Path(input_root)/ref['filename']))]
        keys=['shape_resolution','shape_seed','geometry_model']
    else:
        source=run['selection'] if stage=='package' else [fingerprint(run,s,input_root) for s in DEPENDENCIES.get(stage,[]) if s!='turnaround']
        keys=['export_grounding'] if stage=='package' else STAGE_KEYS[stage]
    settings={k:run['settings'].get(k) for k in keys if k!='quad_method'}
    if stage=='quads':
        settings.update(fingerprint_fields(run['settings']))
    if stage=='texture':
        settings=texture_sampling_settings(run['settings'],settings)
    return signature(['single-image/1',stage,settings,source])

def metadata(run):
    texture_mode=run['settings'].get('texture_mode','standard')
    resources=['pixal3d_single',MOGE_MODEL_KEY,'dinov3','birefnet','hi3d','pymeshlab']
    keys={'detailed':'texture','game_balanced':'balanced','game_compact':'compact','print':'print','quad_light':'quad_manifest'}
    receipts=[]
    for variant in run['selection']['variants']:
        path=Path(run['checkpoints'][keys[variant]])
        if variant=='quad_light':path=path.parent/'editable-quads.blend'
        used=resources+(['trellis2','trellis_wrapper'] if variant!='print' else [])
        if variant=='quad_light':used+=manifest_resources(run['checkpoints']['quad_manifest'])
        if variant!='print' and texture_mode=='smd':used+=['trellis_smd_texture']
        if variant=='print' and run.get('print_report',{}).get('contact_repair'):used+=['meshlib']
        receipts.append({'variant_id':variant,'sha256':digest(path),'resources':list(dict.fromkeys(used)),
            'validation':[{'name':'Single Image production','status':'matched','note':'Bound to saved run '+run['id']}]})
    lock=json.loads(Path(__file__).resolve().parents[3].joinpath('models.lock.json').read_text(encoding='utf-8'))
    production={'method':'single-image','workflow_title':'Single Image or Text','run_id':run['id'],'settings':run['settings'],'selection':run['selection'],
        'source_sha256':run['references'][0]['sha256'],
        'models':{key:{k:v for k,v in lock['models'][key].items() if k in ('repo','file','revision','sha256','license','license_url')} for key in ('pixal_single','shape_vae','dino',MOGE_MODEL_KEY,'birefnet')},
        'template':'Comfy-Org/workflow_templates@ea7faae6999fb31338f43408ff4a575bd3f7d9a0/3d_pixal3d_trellis2_image_to_model.json'}
    if any(variant!='print' for variant in run['selection']['variants']):
        from ..image_to_3d.worker_models import texture_dependencies
        production['texture_models']=texture_dependencies(lock,texture_mode)
    if run.get('image_creation'):production['image_creation']=run['image_creation']
    if 'quad_light' in run['selection']['variants']:production['quad_retopology']=run.get('quad_report',{})
    return {'workflow_version':'single-image/1','receipts':receipts,'production':production,'warnings':run.get('quad_report',{}).get('warnings',[])}
