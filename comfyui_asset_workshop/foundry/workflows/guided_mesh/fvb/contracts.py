"""Immutable request validation shared by graph compiler and job runner."""
import copy
import math
import re
from pathlib import PurePosixPath

DEFAULT_SUFFIX = ('The images describe one asset. Use the rendered second image for the target camera, '
    'framing, silhouette, proportions, attachment positions and occlusion. Use the first image for overall '
    'identity and appearance. Use the designated concept and supplementary references only for the described surfaces, '
    'materials, colors and details. Produce one finished image from the rendered camera. Keep the whole '
    'asset in the same image frame. Do not copy another reference viewpoint, create a sheet, repeat the '
    'asset, or add labels. Preserve the stated distinctive parts.')


def defaults():
    return dict(schema='fvb.run/1', job_id='', original='', category='props', asset_description='',
        special_instructions='', view_preset='general_quarters', azimuths_deg=[45,135,225,315],
        elevation_deg=20.0, include_top=False, custom_views=[], horizontal_fov_deg=20.0,
        render_size=1024, orbit_margin=1.05, render_samples=32, render_threads=8, proxy_yaw_deg=0.0,
        proxy_pitch_deg=0.0,proxy_roll_deg=0.0,proxy_processing='as_generated',
        proxy_remesh_resolution=512,proxy_smooth_iterations=2,hi3d_backend_url='http://127.0.0.1:8378',
        turnaround_seed=939810832464276, turnaround_steps=25, turnaround_cfg=1.0,
        proxy_seed=42, proxy_resolution=1024, reconstruction_seed=42, reconstruction_resolution=1024,
        structure_steps=12, shape_steps=20, upscale_steps=12, mesh_cfg=7.5,
        proxy_color_steps=12, proxy_color_cfg=1.0, enhancement_seed=42, enhancement_steps=25,
        enhancement_cfg=3.0, adapter_strength=1.0, supplementary_resolution=512,
        enhancement_suffix=DEFAULT_SUFFIX, extra_references=[], view_overrides={}, reference_view_id='front_right',
        refine_resolution=1536, refine_steps=25, refine_seed=42, cpu_offload=True, attention='sdpa',
        texture_enabled=False, texture_seed=42, texture_steps=20, texture_size=4096,
        texture_guidance=3.0, cache_device='cpu', cache_dtype='default', tiled_vae=True,
        extra_vram_headroom_gb=1.0, min_ram_free_gb=8.0, guided=True, technical_retry_limit=0,
        enhancement_mode='individual', sheet_gutter=32, selected_view_ids=[],
        structure_control='off', control_strength=1.0, control_start_percent=0.0, control_end_percent=1.0,
        controlled_cache_device='off', mask_mode='foreground', mask_threshold=0.5, mask_dilation_px=0,
        restore_black_gutters=True, canny_low_threshold=0.4, canny_high_threshold=0.8,
        repair_enabled=False,repair_requests={},guide_material='source_color',proxy_cleanup='off',
        guide_smooth_factor=.25,guide_smooth_iterations=2,camera_convention='legacy_absolute',
        client_id='', workflow_path='workflows/Foundry View Bridge — proxy guided reconstruction.json')


def sheet_defaults():
    spec=defaults()
    spec.update(enhancement_mode='sheet',view_preset='cardinal',azimuths_deg=[0,90,180,270],
        elevation_deg=10.0,selected_view_ids=['front','right','back','left'],reference_view_id='front',
        enhancement_cfg=1.0,enhancement_suffix='Preserve the distinctive parts and their attachment positions across all views.',
        workflow_path='workflows/Foundry View Bridge — sheet enhancement.json')
    return spec


def selected_views(spec):
    views=view_records(spec)
    selected=spec.get('selected_view_ids',[])
    if not selected and spec.get('enhancement_mode','individual')=='individual':return views
    if not selected or len(selected)!=len(set(selected)) or set(selected)-{v['id'] for v in views}:
        raise ValueError('Choose at least one unique enabled camera view.')
    return [v for v in views if v['id'] in selected]


def controlled_defaults():
    return {**sheet_defaults(), 'structure_control':'depth', 'enhancement_steps':40,
            'workflow_path':'workflows/Foundry View Bridge — controlled sheet.json'}


def effective_reference(spec):
    ids=[v['id'] for v in selected_views(spec)]
    return spec['reference_view_id'] if spec['reference_view_id'] in ids else ids[0]


def repair_defaults():
    return {**controlled_defaults(),'repair_enabled':True,'guide_material':'neutral_clay','texture_enabled':True,'camera_convention':'canonical_anchor','proxy_processing':'upright_solid_box',
        'asset_description':'A chunky freestanding fantasy treasure chest with a rounded wooden lid, deep red painted wood, dark iron bands and an attached brass front latch.',
        'special_instructions':'One closed solid chest. Front: a single brass latch. Back: plain red wooden panels with two attached iron hinges, no grille or holes. Keep the same body, lid, bands and materials in every view. No detached pieces, handles, transparency, text or display stand.',
        'workflow_path':'workflows/Foundry View Bridge — repair and texture.json'}


def effective_image_key(spec,view_id):
    return ('corrected:' if view_id in spec.get('repair_requests',{}) else 'prepared:')+view_id


def view_records(spec):
    if spec.get('custom_views'):
        result = copy.deepcopy(spec['custom_views'])
    else:
        names = {45:'front_right', 135:'rear_right', 225:'rear_left', 315:'front_left', 0:'front', 180:'back', 90:'right', 270:'left'}
        result = [dict(id=names.get(float(a)%360, 'view_'+str(i)), azimuth_deg=float(a)%360,
                       elevation_deg=float(spec['elevation_deg'])) for i,a in enumerate(spec['azimuths_deg'])]
    if (spec.get('include_top') or spec.get('view_preset') == 'aircraft') and not any(v['id']=='top' for v in result):
        result.append(dict(id='top', azimuth_deg=0.0, elevation_deg=90.0))
    return result


def input_name(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Choose a Comfy input filename, without absolute paths or traversal.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Input filename escaped the Comfy input folder.')
    return value


def validate_spec(candidate, require_input=True):
    if not isinstance(candidate, dict):
        raise ValueError('Run settings must be an object.')
    base = defaults()
    unknown = candidate.keys() - base.keys()
    if unknown:
        raise ValueError('Unknown controls: '+', '.join(sorted(unknown)))
    spec = {**base, **copy.deepcopy(candidate)}
    for key, default in base.items():
        value = spec[key]
        if isinstance(default, bool):
            valid = isinstance(value, bool)
        elif isinstance(default, (float,int)):
            valid = isinstance(value, (float,int)) and not isinstance(value,bool) and math.isfinite(value)
            if isinstance(default,int):
                valid = valid and isinstance(value,int)
        else:
            valid = isinstance(value,type(default))
        if not valid:
            raise ValueError('Invalid control: '+key)
    if spec['schema'] != 'fvb.run/1' or spec['category'] not in ('characters','creatures','vehicles','props','environment'):
        raise ValueError('Unsupported run schema or category.')
    if spec['camera_convention'] not in ('legacy_absolute','canonical_anchor'):
        raise ValueError('Unsupported reconstruction camera convention.')
    if spec['job_id'] and not re.fullmatch('[a-f0-9]{32}',spec['job_id']):
        raise ValueError('Invalid job identifier.')
    if require_input:
        input_name(spec['original'])
        if not spec['asset_description'].strip():
            raise ValueError('Describe the asset before creating its run.')
    if spec['original']:
        input_name(spec['original'])
    if len(spec['asset_description']) > 800 or len(spec['special_instructions']) > 800:
        raise ValueError('Keep asset description and preservation notes each under 800 characters.')
    if spec['enhancement_mode'] not in ('individual','sheet'):
        raise ValueError('Unsupported enhancement mode.')
    if spec['guide_material'] not in ('source_color','neutral_clay') or spec['proxy_cleanup'] not in ('off','smooth_surface'):
        raise ValueError('Choose source_color/neutral_clay and off/smooth_surface guide processing.')
    if spec['proxy_processing'] not in ('as_generated','upright_solid_box'):
        raise ValueError('Choose an explicit working-proxy policy.')
    if spec['proxy_processing']!='as_generated' and (any(spec[k]!=0 for k in ('proxy_yaw_deg','proxy_pitch_deg','proxy_roll_deg')) or spec['proxy_cleanup']!='off'):
        raise ValueError('Automatic working-proxy processing cannot be combined with manual or guide-only correction.')
    if spec['proxy_remesh_resolution'] not in (128,256,384,512) or not 0<=spec['proxy_smooth_iterations']<=3:
        raise ValueError('Use bounded proxy topology controls.')
    from urllib.parse import urlparse
    endpoint=urlparse(spec['hi3d_backend_url'])
    if endpoint.scheme!='http' or endpoint.hostname not in ('127.0.0.1','localhost') or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in ('','/'):
        raise ValueError('Hi3D needs an explicit local HTTP backend endpoint.')
    if not 0<=spec['guide_smooth_factor']<=1 or not 1<=spec['guide_smooth_iterations']<=20:
        raise ValueError('Guide smoothing needs factor0..1 and iterations1..20.')
    if spec['repair_enabled'] and spec['enhancement_mode']!='sheet':
        raise ValueError('Masked repair belongs to the controlled sheet profile.')
    requests=spec['repair_requests']
    if requests and not spec['repair_enabled']:raise ValueError('Enable the repair profile before requesting a correction.')
    if len(requests)>4 or set(requests)-{'front','right','back','left'}:raise ValueError('Repair only named sheet views.')
    required={'source_sha256','camera_sha256','prompt','seed','steps','cfg','margin_px','feather_px'}
    for ident,r in requests.items():
        if not isinstance(r,dict) or set(r)!=required:raise ValueError('Incomplete or unknown repair settings: '+ident)
        if any(not isinstance(r[k],str) or not re.fullmatch('[a-f0-9]{64}',r[k]) for k in ('source_sha256','camera_sha256')):
            raise ValueError('Repair needs immutable source/camera digests.')
        if not isinstance(r['prompt'],str) or not r['prompt'].strip() or len(r['prompt'])>2000:raise ValueError('Describe the repaired target in1..2000 characters.')
        for k,low,high in [('seed',0,2**53-16),('steps',20,100),('cfg',.1,20),('margin_px',0,32),('feather_px',0,16)]:
            v=r[k]
            if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not low<=v<=high or (k!='cfg' and not isinstance(v,int)):
                raise ValueError('Invalid repair '+k)
    if spec['structure_control'] not in ('off','depth','canny') or (spec['structure_control']!='off' and spec['enhancement_mode']!='sheet'):
        raise ValueError('Structural control supports depth/canny sheet editing only.')
    if spec['mask_mode'] not in ('foreground','none') or spec['controlled_cache_device']!='off':
        raise ValueError('Controlled sheet uses explicit foreground/none masking and cache off.')
    if not 0 <= spec['control_start_percent'] < spec['control_end_percent'] <= 1:
        raise ValueError('Control schedule requires 0 <= start < end <= 1.')
    if not .01 <= spec['canny_low_threshold'] < spec['canny_high_threshold'] <= .99:
        raise ValueError('Canny thresholds require low < high within .01–.99.')
    if spec['render_size'] not in ((1024,2048) if spec['enhancement_mode']=='sheet' else (1024,)):
        raise ValueError('Choose a supported square camera frame size.')
    if spec['sheet_gutter'] not in (0,32,64):
        raise ValueError('Sheet gutter must be 0, 32 or 64 pixels.')
    if spec['view_preset'] not in ('general_quarters','road_vehicle','aircraft','custom','cardinal'):
        raise ValueError('Unsupported view preset.')
    if not 2 <= spec['horizontal_fov_deg'] <= 120 or not 1 <= spec['orbit_margin'] <= 2:
        raise ValueError('Invalid camera FOV or framing margin.')
    views = view_records(spec)
    if not 1 <= len(views) <= 12:
        raise ValueError('Choose one to twelve explicit camera views.')
    ids=set()
    for v in views:
        if set(v) != {'id','azimuth_deg','elevation_deg'} or not re.fullmatch('[a-z][a-z0-9_]{0,31}',v['id']) or v['id'] in ids:
            raise ValueError('Camera IDs must be unique, simple names with explicit angles.')
        ids.add(v['id'])
        if not all(isinstance(v[k],(int,float)) and math.isfinite(v[k]) for k in ('azimuth_deg','elevation_deg')) or not -90 <= v['elevation_deg'] <=90:
            raise ValueError('Invalid camera angle.')
    if spec['reference_view_id'] not in ids:
        raise ValueError('Selected refinement reference must name an enabled view.')
    if not all(isinstance(v,str) for v in spec['selected_view_ids']):
        raise ValueError('Selected camera IDs must be strings.')
    selected=selected_views(spec)
    if spec['selected_view_ids']:spec['selected_view_ids']=[v['id'] for v in selected]
    if spec['enhancement_mode']=='sheet' and [v['id'] for v in views]!=['front','right','back','left']:
        raise ValueError('Sheet mode needs front/right/back/left cameras and no top view.')
    if spec['enhancement_mode']=='sheet' and spec['view_overrides']:
        raise ValueError('A shared sheet uses shared enhancement settings; per-view inference overrides belong to individual mode.')
    for ident,override in spec['view_overrides'].items():
        if ident not in ids or not isinstance(override,dict) or set(override)-{'seed','steps','cfg','special_instructions','enhancement_suffix'}:
            raise ValueError('Per-view overrides must name an enabled view and supported enhancement controls.')
        for key,value in override.items():
            if key in ('special_instructions','enhancement_suffix'):
                if not isinstance(value,str) or len(value)>3000:raise ValueError('Invalid per-view instruction.')
            elif key=='seed':
                if not isinstance(value,int) or isinstance(value,bool) or not 0<=value<=2**53-16:raise ValueError('Invalid per-view seed.')
            elif key=='steps':
                if not isinstance(value,int) or isinstance(value,bool) or not 20<=value<=100:raise ValueError('Invalid per-view step count.')
            elif not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or not .1<=value<=20:
                raise ValueError('Invalid per-view CFG.')
    refs=spec['extra_references']
    if len(refs)>6:
        raise ValueError('At most ten total enhancement images: original, guide, two concepts and six optional references.')
    for ref in refs:
        if not isinstance(ref,dict) or not ref.get('description','').strip() or len(ref['description'])>800:
            raise ValueError('Every optional reference needs a purpose and target description.')
        input_name(ref.get('filename',''))
    ranges = {'turnaround_steps':(1,100),'turnaround_cfg':(.1,20),'structure_steps':(1,100),
              'shape_steps':(1,100),'upscale_steps':(1,100),'mesh_cfg':(.1,20),
              'proxy_color_steps':(1,100),'proxy_color_cfg':(.1,20),'enhancement_steps':(20,100),
              'enhancement_cfg':(.1,20),'adapter_strength':(0,2),'supplementary_resolution':(256,1024),
              'refine_steps':(1,100),'texture_steps':(1,100),'texture_guidance':(0,20),
              'render_samples':(1,256),'render_threads':(1,16),'extra_vram_headroom_gb':(0,12),
              'min_ram_free_gb':(1,32),'control_strength':(0,2),'mask_threshold':(.01,.99),'mask_dilation_px':(0,16)}
    ranges['proxy_yaw_deg']=(-360,360)
    ranges['proxy_pitch_deg']=(-180,180)
    ranges['proxy_roll_deg']=(-180,180)
    for key,(low,high) in ranges.items():
        if not low <= spec[key] <= high:
            raise ValueError('Out of range control: '+key)
    for key in ('proxy_resolution','reconstruction_resolution'):
        if spec[key] not in (1024,1536,2048):
            raise ValueError('Unsupported '+key)
    if spec['refine_resolution'] not in (512,1024,1536) or spec['texture_size'] not in (1024,2048,4096):
        raise ValueError('Unsupported finishing resolution.')
    if spec['cache_device'] not in ('cpu','auto','gpu','off') or spec['cache_dtype'] not in ('default','int8','int4') or spec['attention']!='sdpa':
        raise ValueError('Unsupported cache/attention setting.')
    if spec['technical_retry_limit'] != 0:
        raise ValueError('Technical errors require diagnosis and explicit retry; automatic retries are disabled.')
    for key in base:
        if key.endswith('_seed') and not 0 <= spec[key] <= 2**53-16:
            raise ValueError('Seed out of range: '+key)
    return spec


def stages(spec):
    ids=[v['id'] for v in view_records(spec)]
    if spec.get('enhancement_mode')=='sheet':
        return ['concept','proxy','render','sheet','enhance_sheet','split','prepare',
                *['repair:'+v for v in ids if v in spec.get('repair_requests',{})],'reconstruct','refine',
                *(['texture'] if spec['texture_enabled'] else [])]
    return ['concept','proxy','render', *['enhance:'+v for v in ids], 'prepare', 'reconstruct','refine',
            *(['texture'] if spec['texture_enabled'] else [])]
