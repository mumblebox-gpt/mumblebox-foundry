"""Pinned official single-image sampling and original-reference finishing."""
import json
from pathlib import Path
from copy import deepcopy
from ..image_to_3d.graph import ancestor_prompt,STAGE_OUTPUTS,template as finishing_template
ROOT=Path(__file__).parent

def geometry(run):
    graph=json.loads((ROOT/'sources/official.api.json').read_text(encoding='utf-8'))
    lock=json.loads(Path(__file__).resolve().parents[3].joinpath('models.lock.json').read_text(encoding='utf-8'))['models']
    graph['319']['inputs']['unet_name']=lock['pixal_single']['name']
    graph['312']['inputs']['background']='#000000'
    graph['56']['inputs']['batch_size']=1
    settings=run['settings'];seed=settings.get('shape_seed',42)
    graph['122']['inputs']['image']=run['references'][0]['filename']
    graph['94']['inputs']['target_resolution']=settings['shape_resolution']
    for node,offset in [('3',14),('18',0),('23',0)]:graph[node]['inputs']['seed']=seed+offset
    finish=finishing_template()
    graph['381']={'class_type':'MeshToFile3D','inputs':{'mesh':['92',0]}}
    graph['382']=deepcopy(finish['382'])
    graph['382']['_meta']={'title':'Initial single-image geometry before Hi3D'}
    graph['382']['inputs']['filename_prefix']='foundry-single/'+run['id']+'/geometry'
    graph['340']={'class_type':'SaveImage','inputs':{'images':['122',0],'filename_prefix':'foundry-single/'+run['id']+'/reference'}}
    return ancestor_prompt(graph,['382','340'])

def compile_stage(stage,run):
    if stage=='geometry':return geometry(run)
    # Checkpoint-separated finishing intentionally shares the existing owner.
    from ..image_to_3d.graph import compile_stage as finishing
    graph=finishing(stage,{**run,'method':'single-finishing'})
    if stage=='package':
        graph.setdefault('9100',{'class_type':'Hi3DFinishingSource','inputs':{'use_saved_checkpoint':True,'saved_clean_mesh':run['checkpoints']['clean'],'saved_texture_mesh':run['checkpoints'].get('texture',run['checkpoints']['clean'])}})
        graph['3011']={'class_type':'Hi3DGroundingFrame','inputs':{'mesh':['9100',0],'mode':run['settings'].get('export_grounding','level')}}
        graph['3010']['inputs']['grounding_json']=['3011',0]
    return graph

def remap(graph,offset):
    result={}
    for key,node in graph.items():
        node=deepcopy(node)
        node['inputs']={k:[str(int(v[0])+offset),v[1]] if isinstance(v,list) and len(v)==2 and str(v[0]) in graph else v for k,v in node['inputs'].items()}
        result[str(int(key)+offset)]=node
    return result

def canvas_recipe():
    from .definition import DEFAULTS
    graph=finishing_template()
    graph.update(geometry(dict(id='template',references=[{'filename':''}],settings=DEFAULTS)))
    for ident in ('2020','2022'):graph[ident]['inputs']['image']=['122',0]
    graph['3011']={'class_type':'Hi3DGroundingFrame','inputs':{'mesh':['2015',0],'mode':DEFAULTS['export_grounding']},'_meta':{'title':'Level support plane for final exports'}}
    graph['3010']['inputs']['grounding_json']=['3011',0]
    endpoints=[n for stage,ids in STAGE_OUTPUTS.items() if stage!='turnaround' for n in ids]
    graph=ancestor_prompt(graph,endpoints+['340'])
    groups={ident:stage for stage,ids in STAGE_OUTPUTS.items() for ident in ids}
    for ident,node in graph.items():
        node['_meta']={'title':node.get('_meta',{}).get('title',node['class_type']),
                       'single_stage':groups.get(ident,'package' if ident=='3011' else 'geometry' if int(ident)<2000 else 'finishing')}
    return graph
