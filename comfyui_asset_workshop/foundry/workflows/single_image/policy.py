"""Single-image cache lineage and portable production credits."""
import json
from pathlib import Path
from ..image_to_3d.runs import signature
from ..image_to_3d.graph import STAGE_KEYS,DEPENDENCIES
from ...artifacts import digest,owned_path

def fingerprint(run,stage,input_root):
    if stage=='geometry':
        ref=run['references'][0]
        source=[ref['filename'],digest(owned_path(input_root,Path(input_root)/ref['filename']))]
        keys=['shape_resolution','shape_seed','geometry_model']
    else:
        source=run['selection'] if stage=='package' else [fingerprint(run,s,input_root) for s in DEPENDENCIES.get(stage,[]) if s!='turnaround']
        keys=['export_grounding'] if stage=='package' else STAGE_KEYS[stage]
    return signature(['single-image/1',stage,{k:run['settings'].get(k) for k in keys},source])

def metadata(run):
    resources=['pixal3d_single','moge2','dinov3','birefnet','hi3d','pymeshlab']
    keys={'detailed':'texture','game_balanced':'balanced','game_compact':'compact','print':'print','quad_light':'quad_manifest'}
    receipts=[]
    for variant in run['selection']['variants']:
        path=Path(run['checkpoints'][keys[variant]])
        if variant=='quad_light':path=path.parent/'editable-quads.blend'
        used=resources+(['trellis2','trellis_wrapper'] if variant!='print' else [])+(['quadriflow'] if variant=='quad_light' else [])
        if variant=='print' and run.get('print_report',{}).get('contact_repair'):used+=['meshlib']
        receipts.append({'variant_id':variant,'sha256':digest(path),'resources':list(dict.fromkeys(used)),
            'validation':[{'name':'Single Image production','status':'matched','note':'Bound to saved run '+run['id']}]})
    lock=json.loads(Path(__file__).resolve().parents[3].joinpath('models.lock.json').read_text(encoding='utf-8'))
    production={'method':'single-image','workflow_title':'Single Image or Text','run_id':run['id'],'settings':run['settings'],'selection':run['selection'],
        'source_sha256':run['references'][0]['sha256'],
        'models':{key:{k:v for k,v in lock['models'][key].items() if k in ('repo','file','revision','sha256','license','license_url')} for key in ('pixal_single','shape_vae','dino','moge2','birefnet')},
        'template':'Comfy-Org/workflow_templates@ea7faae6999fb31338f43408ff4a575bd3f7d9a0/3d_pixal3d_trellis2_image_to_model.json'}
    if run.get('image_creation'):production['image_creation']=run['image_creation']
    return {'workflow_version':'single-image/1','receipts':receipts,'production':production,'warnings':run.get('quad_report',{}).get('warnings',[])}
