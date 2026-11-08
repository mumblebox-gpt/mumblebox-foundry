"""Single Image method policy and bounded options."""
from ..image_to_3d.definition import DEFAULTS as BASE,resolve_settings as base_settings
METHOD='single-image'
OFFSET=500000
DEFAULTS={**BASE,'shape_resolution':1024,'shape_seed':42,'geometry_model':'pixal3d','export_grounding':'level'}

def validate_references(refs):
    if not isinstance(refs,list) or len(refs)!=1 or not isinstance(refs[0],dict) or not isinstance(refs[0].get('filename'),str):
        raise ValueError('Single Image needs exactly one image. Upload, create, photograph or choose one reference.')

def resolve_settings(profile,overrides):
    copy=dict(overrides)
    grounding=copy.pop('export_grounding','level')
    if grounding not in ('level','place','original'):raise ValueError('Choose a supported floor placement mode.')
    seed=copy.pop('shape_seed',42);model=copy.pop('geometry_model','pixal3d')
    if not isinstance(seed,int) or isinstance(seed,bool) or not 0<=seed<=2**53-15:raise ValueError('Choose a valid geometry seed.')
    if model!='pixal3d':raise ValueError('The qualified geometry model is Pixal3D.')
    return {**base_settings(profile,copy),'shape_seed':seed,'geometry_model':model,'export_grounding':grounding}

def required_stages(operation,selection):
    stages=[] if operation=='finish' else ['single_geometry','refinement']
    if any(k!='print' for k in selection['variants']):stages.append('texture')
    return stages
