"""One bounded public configuration for the wizard, native graph and agents."""
from copy import deepcopy
import math
from ..image_creation.definition import filename

TITLE='Splat & Solid'
METHOD='splat-solid/v1'
TURBO_EXPERTS={
    'slow': 'idol_turbo_slow_comfy.safetensors',
    'fast': 'idol_turbo_fast_comfy.safetensors',
}
TURBO_MODELS=('idol_turbo_slow','idol_turbo_fast')
DEFAULTS=dict(name='Untitled splat asset',image='',generation_mode='standard',seed=46,steps=20,cfg=3.,image_size=1024,
    gaussians=262144,decoder_seed=790219963981395,mesh_resolution=512,refine=True,
    refine_resolution=1536,refine_steps=25,refine_seed=42,cpu_offload=True,
    master_resolution=384,master_smoothing=3,master_band=1.,drop_small_components=0.,
    companion_triangles=20000,repair_resolution=56,repair_mode='rebuild',crease_angle=45.,
    orbit_size=1536,orbit_frames=75,orbit_fps=25,
    outputs=dict(splat=True,raw=False,master=True,companion=True,presentation=True,orbit=True,previews=True,zip=True))
GROUPS=dict(generation=('image','seed','steps','cfg','image_size','gaussians','decoder_seed','mesh_resolution','orbit_size','orbit_frames','orbit_fps'),
    refinement=('refine','refine_resolution','refine_steps','refine_seed','cpu_offload'),
    cleanup=('master_resolution','master_smoothing','master_band','drop_small_components','companion_triangles','repair_resolution','repair_mode','crease_angle'))

def validate(data):
    if not isinstance(data,dict) or data.keys()-DEFAULTS.keys():raise ValueError('Unsupported Splat & Solid option.')
    c={**deepcopy(DEFAULTS),**deepcopy(data)}
    if not isinstance(c['name'],str) or not 1<=len(c['name'].strip())<=120:raise ValueError('Name the asset (up to 120 characters).')
    c['name']=c['name'].strip();c['image']=filename(c['image'])
    if c['generation_mode'] not in ('standard','turbo'):
        raise ValueError('Choose Standard or Turbo generation mode.')
    bounds=dict(seed=(0,2**53-16),decoder_seed=(0,2**53-16),refine_seed=(0,2**53-16),steps=(1,100),cfg=(.1,20),
        image_size=(256,2048),gaussians=(32768,1048576),mesh_resolution=(128,1024),refine_steps=(1,100),
        master_resolution=(64,1024),master_smoothing=(0,10),master_band=(.5,4),drop_small_components=(0,.1),
        companion_triangles=(1000,500000),repair_resolution=(32,256),crease_angle=(1,180),orbit_size=(256,2048),orbit_frames=(16,180),orbit_fps=(1,60))
    floats={'cfg','master_band','drop_small_components','crease_angle'}
    for key,(low,high) in bounds.items():
        value=c[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high or (key not in floats and int(value)!=value):
            raise ValueError(f'Choose a supported {key.replace("_"," ")} value between {low} and {high}.')
    if c['refine_resolution'] not in (512,1024,1536):raise ValueError('Choose refinement resolution 512, 1024 or 1536.')
    if c['gaussians']%32:raise ValueError('Gaussian count must be a multiple of 32.')
    if c['repair_mode'] not in ('auto','rebuild'):raise ValueError('Choose automatic or solid-rebuild companion repair.')
    if any(type(c[key]) is not bool for key in ('refine','cpu_offload')):raise ValueError('Use an on/off refinement option.')
    if not isinstance(c['outputs'],dict) or c['outputs'].keys()-DEFAULTS['outputs'].keys():raise ValueError('Unsupported export selection.')
    c['outputs']={**DEFAULTS['outputs'],**c['outputs']}
    if any(type(v) is not bool for v in c['outputs'].values()) or not any(v for k,v in c['outputs'].items() if k!='zip'):raise ValueError('Select at least one output.')
    return c

def needs_mesh(c):return any(c['outputs'][k] for k in ('master','companion','presentation','previews'))

def capabilities():
    from ..image_to_3d.readiness import viewer_module
    return dict(title=TITLE,method=METHOD,defaults=deepcopy(DEFAULTS),viewer_module=viewer_module(),
        models=[dict(name='Idol',creator='Sperid Labs',url='https://huggingface.co/speridlabs/idol',role='Single-image Gaussian splat generation and mesh extraction'),
                dict(name='Idol Turbo',creator='Sperid Labs and contributors',url='https://huggingface.co/speridlabs/idol-turbo',role='Optional phase adapters for five-step splat generation'),
                dict(name='Hi3D',creator='Hi3D researchers',url='https://github.com/hi3d-official/Hi3Dv1.0',role='Optional image-guided geometry refinement'),
                dict(name='ComfyUI',creator='Comfy-Org and contributors',url='https://github.com/Comfy-Org/ComfyUI',role='Mesh cleanup, simplification, previews and exports')])
