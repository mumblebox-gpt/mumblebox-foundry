"""Compile native stages and one self-contained, independently owned graph."""
from copy import deepcopy
import json
from pathlib import Path
from .definition import TURBO_EXPERTS, needs_mesh

BASE=json.loads(Path(__file__).with_name('generation-template.json').read_text(encoding='utf-8'))
IDS={key:str(400000+i) for i,key in enumerate(sorted(set(BASE)|{'load_raw','load_refined','99','109','110','111','112','113','114','115','117','119','124','normalize','101','103','107','gate','select','restore_master','restore_companion','normal_master','normal_companion','120','121','143','150','camera','render_master','render_companion','image_master','image_companion'}))}
# Append the optional nodes so existing Splat & Solid node identities stay valid.
TURBO_NODES=('turbo_slow_model','turbo_fast_model','turbo_slow_sample','turbo_fast_sample')
IDS.update({key:str(400000+len(IDS)+i) for i,key in enumerate(TURBO_NODES)})
ROLES={name:IDS[key] for name,key in dict(splat='51',raw='67',orbit='42',refined_raw='117',refined='119',master='120',companion='121',master_presentation='143',companion_presentation='150',master_preview='image_master',companion_preview='image_companion').items()}

def node(kind,**inputs):return {'class_type':kind,'inputs':inputs}
def mesh_file(record,role):return record.get('artifacts',{}).get(role,{}).get('relative','')
def remesh(source,resolution,band,smooth,drop):
    return node('RemeshMesh',mesh=source,resolution=resolution,sign_mode='solid',**{'sign_mode.fill':20.,'sign_mode.qef':False},band=band,project_back=0.,fix_poles=True,smooth_iters=smooth,drop_small_components=drop,precluster_max_verts=20000000)

def apply_turbo(graph, seed):
    original=graph['88:6']['inputs']
    for phase, filename in TURBO_EXPERTS.items():
        graph['turbo_'+phase+'_model']=node(
            'LoraLoaderModelOnly', model=original['model'], lora_name=filename, strength_model=1.0)
    common={key:original[key] for key in ('positive','negative')}
    common.update(noise_seed=seed, steps=5, cfg=1.0, sampler_name='euler', scheduler='simple')
    # Native Idol uses shift 3. The first low-noise evaluation is index 4
    # (raw t=.2, shifted t=.429), so the first four use the slow expert.
    graph['turbo_slow_sample']=node(
        'KSamplerAdvanced', model=['turbo_slow_model',0], latent_image=original['latent_image'],
        add_noise='enable', start_at_step=0, end_at_step=4, return_with_leftover_noise='enable', **common)
    graph['turbo_fast_sample']=node(
        'KSamplerAdvanced', model=['turbo_fast_model',0], latent_image=['turbo_slow_sample',0],
        add_noise='disable', start_at_step=4, end_at_step=5, return_with_leftover_noise='disable', **common)
    graph['88:55']['inputs']['samples']=['turbo_fast_sample',0]
    graph.pop('88:6')

def compile_stage(record,stage,full=False):
    c=record['config'];prefix='foundry-splat/'+record['id']+'/'
    g={}
    if stage=='generation' or full:
        g=deepcopy(BASE)
        g['99']=node('FoundryLoadCreationImage',filename=c['image'],sha256=record['source_sha256'])
        if c.get('generation_mode')=='turbo':
            apply_turbo(g,c['seed'])
        else:
            g['88:6']['inputs'].update(seed=c['seed'],steps=c['steps'],cfg=c['cfg'])
        g['88:2']['inputs']['size']=c['image_size']
        g['88:55']['inputs'].update(num_gaussians=c['gaussians'],seed=c['decoder_seed'])
        g['76']['inputs']['resolution']=c['mesh_resolution']
        for key,role in [('51','splat'),('67','raw'),('42','orbit')]:g[key]['inputs']['filename_prefix']=prefix+role+'/asset'
        g['75']['inputs'].update(width=c['orbit_size'],height=c['orbit_size'],frames=c['orbit_frames'])
        g['41']['inputs']['fps']=c['orbit_fps']
        if not c['outputs']['orbit']:
            for key in ('42','41','75'):g.pop(key,None)
    if stage=='refinement' or (full and c['refine'] and needs_mesh(c)):
        g.update({'99':node('FoundryLoadCreationImage',filename=c['image'],sha256=record['source_sha256']),
            'load_raw':node('FoundrySplatLoadMesh',filename=mesh_file(record,'raw')),
            '109':node('DecimateMesh',mesh=['76',0] if full else ['load_raw',0],target_face_count=4500000,placement_mode='midpoint'),
            '110':node('LoadBackgroundRemovalModel',bg_removal_name='birefnet.safetensors'),
            '111':node('RemoveBackground',bg_removal_model=['110',0],image=['99',0]),
            '112':node('InvertMask',mask=['111',0]),'124':node('JoinImageWithAlpha',image=['99',0],alpha=['99',1]),
            '113':node('Hi3DBackend',url=''),
            '114':node('Hi3DRefine',backend=['113',0],image=['124',0],mesh=['109',0],mask=['112',0],resolution=c['refine_resolution'],steps=c['refine_steps'],seed=c['refine_seed'],cpu_offload=c['cpu_offload'],attention='sdpa'),
            '115':node('Hi3DAlignToSource',mesh=['114',0],source_mesh=['109',0]),
            '117':node('SaveGLB',mesh=['114',0],filename_prefix=prefix+'refined-raw/asset'),
            '119':node('SaveGLB',mesh=['115',0],filename_prefix=prefix+'refined/asset')})
        if full:g.pop('load_raw')
    if stage=='cleanup' or (full and needs_mesh(c)):
        source=['115',0] if full and c['refine'] else ['76',0] if full else ['load_refined',0]
        g.update({'load_refined':node('FoundrySplatLoadMesh',filename=mesh_file(record,'refined' if c['refine'] else 'raw')),
            'normalize':node('Hi3DNormalizeMesh',mesh=source,span=.96),
            '101':remesh(['normalize',0],c['master_resolution'],c['master_band'],c['master_smoothing'],c['drop_small_components']),
            '103':node('DecimateMesh',mesh=['101',0],target_face_count=c['companion_triangles'],placement_mode='midpoint'),
            '107':remesh(['103',0],c['repair_resolution'],.5,2,.001),
            'gate':node('Hi3DNeedsSolidRepair',mesh=['103',0]),
            'select':node('ComfySwitchNode',switch=True if c['repair_mode']=='rebuild' else ['gate',0],on_false=['103',0],on_true=['107',0]),
            'restore_master':node('Hi3DRestoreMeshFrame',mesh=['101',0],original_frame=['normalize',1]),
            'restore_companion':node('Hi3DRestoreMeshFrame',mesh=['select',0],original_frame=['normalize',1]),
            'normal_master':node('MeshSmoothNormals',mesh=['restore_master',0],crease_angle=c['crease_angle']),
            'normal_companion':node('MeshSmoothNormals',mesh=['restore_companion',0],crease_angle=c['crease_angle']),
            '120':node('SaveGLB',mesh=['restore_master',0],filename_prefix=prefix+'master/asset'),
            '121':node('SaveGLB',mesh=['restore_companion',0],filename_prefix=prefix+'companion/asset'),
            '143':node('SaveGLB',mesh=['normal_master',0],filename_prefix=prefix+'presentation/master'),
            '150':node('SaveGLB',mesh=['normal_companion',0],filename_prefix=prefix+'presentation/companion'),
            'camera':node('CreateCameraInfo',mode='orbit',**{'mode.yaw':35.,'mode.pitch':20.,'mode.distance':2.35},target_x=0.,target_y=0.,target_z=0.,roll=0.,fov=35.,zoom=1.,camera_type='perspective')})
        for role in ('master','companion'):
            g['render_'+role]=node('RenderMesh',mesh=['normal_'+role,0],camera_info=['camera',0],width=1536,height=1536,mode='solid',background='#50565c')
            g['image_'+role]=node('SaveImage',images=['render_'+role,0],filename_prefix=prefix+'previews/'+role)
        if full:g.pop('load_refined')
    result={}
    for key,value in g.items():
        item=deepcopy(value)
        for name,v in item['inputs'].items():
            if isinstance(v,list) and len(v)==2 and str(v[0]) in IDS:item['inputs'][name]=[IDS[str(v[0])],v[1]]
        item['_meta']={'title':'Splat & Solid · '+value['class_type'],'splat_stage':('generation' if key in BASE or key in TURBO_NODES or key=='99' else 'refinement' if key in {'109','110','111','112','113','114','115','117','119','124','load_raw'} else 'cleanup')}
        result[IDS[key]]=item
    return result
