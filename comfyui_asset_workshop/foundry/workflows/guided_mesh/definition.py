"""Public contract for the independent, objects-only measured-view method."""
from copy import deepcopy
import re
from pathlib import PurePosixPath
from .fvb.contracts import repair_defaults, validate_spec

METHOD_ID='3d-guided/v1'
VERSION='2026-11-04.1'
GRAPH_OFFSET=100000
QUAD_RETOPOLOGY_ENABLED=False
VIEWS=('front','right','back','left')
CONTROLS=('asset_description','special_instructions','elevation_deg','horizontal_fov_deg',
    'selected_view_ids','reference_view_id','proxy_processing','proxy_resolution',
    'proxy_remesh_resolution','proxy_smooth_iterations','reconstruction_resolution',
    'turnaround_seed','proxy_seed','reconstruction_seed','enhancement_seed',
    'turnaround_steps','enhancement_steps','enhancement_cfg','control_strength',
    'refine_resolution','refine_steps','refine_seed','cpu_offload','texture_seed',
    'texture_steps','texture_size','texture_guidance','render_size','render_samples',
    'extra_references','enhancement_suffix')

def export_variants():
    return ('detailed','game_balanced','game_compact','print')+(('quad_light',) if QUAD_RETOPOLOGY_ENABLED else ())

def initial_spec():
    spec=repair_defaults()
    spec.update(asset_description='',special_instructions='',guided=True,
        texture_enabled=True,workflow_path='workflows/Mumblebox - Foundry GUI Review.json')
    return spec

def resolve_spec(overrides,original,client_id,workflow_path=None):
    if not isinstance(overrides,dict) or overrides.keys()-set(CONTROLS):
        raise ValueError('An unsupported 3D-Guided control was supplied.')
    spec={**initial_spec(),**deepcopy(overrides),'original':original,'client_id':client_id}
    if workflow_path:spec['workflow_path']=workflow_path
    if spec['elevation_deg']<0 or spec['elevation_deg']>30:
        raise ValueError('Object view elevation must be between 0 and 30 degrees.')
    if spec['render_size']!=1024:
        raise ValueError('This Objects preset uses four 1024-pixel panels.')
    return validate_spec(spec)

def reconnect_spec(spec,client_id,workflow_path):
    if not isinstance(client_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',client_id):
        raise ValueError('Wait for the current Comfy connection before continuing.')
    if (not isinstance(workflow_path,str) or len(workflow_path)>300 or '\\' in workflow_path
            or not workflow_path.startswith('workflows/') or not workflow_path.endswith('.json')
            or '..' in PurePosixPath(workflow_path).parts):
        raise ValueError('Save and select the Foundry workflow before continuing.')
    return {**deepcopy(spec),'client_id':client_id,'workflow_path':workflow_path}
