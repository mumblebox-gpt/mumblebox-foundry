"""Public, bounded HairDeck controls shared by the wizard, queue and MCP."""
import math
import re
from ...artifacts import relative_name

TITLE = 'Create Rigged Hair with HairDeck'
REVISION = 'ad27f3433169ca6e1f61396525d30d6ca55428be'
WEIGHTS = {key: ('sam3.pt' if key == 'sam3' else 'model.safetensors')
           for key in ('image_model', 'card_vae', 'chain_model', 'sam3', 'dinov3', 'birefnet')}
DEFAULTS = dict(name='Stylized hair', image='', seed=0, variations=1, bones=True, steps=50, cfg=2.,
                color='auto', show_head=True, head_profile='upstream', scale=1., offset=[0., 0., 0.],
                uv_mode='shared', texture_size='2K', material='volume', glb=True, vrm=True,
                motion=False, motion_chains=False, diagnostics=True, source_data=True, zip=True, colors=True, checkpoints=WEIGHTS)
GENERATION_KEYS = ('image', 'seed', 'steps', 'cfg', 'colors', 'checkpoints')


def numeric(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(label+' must be a finite number.')
    if not low <= value <= high or (integer and int(value) != value):
        raise ValueError(label+f' must be between {low} and {high}.')
    return int(value) if integer else float(value)


def validate(data):
    if not isinstance(data, dict) or set(data)-set(DEFAULTS): raise ValueError('Unknown hair options.')
    config = {**DEFAULTS, **data}
    name = config['name']
    if not isinstance(name, str) or not name.strip() or len(name) > 120: raise ValueError('Name the hair asset (up to 120 characters).')
    config['name'] = name.strip()
    relative_name(config['image'])
    if not config['image'].lower().endswith(('.png', '.jpg', '.jpeg', '.webp')): raise ValueError('Choose a PNG, JPEG or WebP reference.')
    for key in ('bones', 'show_head', 'glb', 'vrm', 'motion', 'motion_chains', 'diagnostics', 'source_data', 'zip', 'colors'):
        if type(config[key]) is not bool: raise ValueError('Choose whether to enable '+key+'.')
    if not config['glb'] and not config['vrm']: raise ValueError('Select static GLB or rigged VRM.')
    if (config['vrm'] or config['motion']) and not config['bones']: raise ValueError('VRM and motion require spring bones.')
    config['seed'] = numeric(config['seed'], 'Seed', 0, 2**53-16, True)
    config['variations'] = numeric(config['variations'], 'Variations', 1, 4, True)
    config['steps'] = numeric(config['steps'], 'Steps', 1, 200, True)
    config['cfg'] = numeric(config['cfg'], 'CFG', 1, 4)
    config['scale'] = numeric(config['scale'], 'Hair fitting scale', .25, 4)
    if not isinstance(config['offset'], list) or len(config['offset']) != 3: raise ValueError('Supply X, Y and Z fitting offsets.')
    config['offset'] = [numeric(x, 'Fitting offset (metres)', -1, 1) for x in config['offset']]
    if config['color'] != 'auto' and not re.fullmatch('#[0-9a-fA-F]{6}', str(config['color'])): raise ValueError('Use auto or #RRGGBB for hair color.')
    for key, options in dict(uv_mode=('shared', 'unique'), texture_size=('1K', '2K', '4K'), material=('volume', 'ribbon', 'solid', 'checker')).items():
        if config[key] not in options: raise ValueError('Choose a supported '+key+'.')
    if not isinstance(config['head_profile'], str) or not re.fullmatch(r'[\w .-]{1,80}', config['head_profile']): raise ValueError('Choose a local head profile.')
    weights = config['checkpoints']
    if not isinstance(weights, dict) or set(weights) != set(WEIGHTS): raise ValueError('Choose the six HairDeck checkpoints.')
    config['checkpoints'] = {key: relative_name(value).as_posix() for key, value in weights.items()}
    return config


def catalog():
    from ..image_to_3d.readiness import viewer_module
    from .integration import upstream
    try:
        native = upstream()
        choices = {key: native.model_files.filenames(key) for key in WEIGHTS}
        roots = native.model_files.resources()
        heads = native.heads.choices(roots.values())
        available = True
    except (ImportError, KeyError, RuntimeError):
        choices = {key: [value] for key, value in WEIGHTS.items()}; heads = ['upstream']; available = False
    from .graph import template
    return dict(title=TITLE, defaults=DEFAULTS, checkpoints=choices, heads=heads, installed=available,graph_template=template(),
                viewer_module=viewer_module(), reference='One clear head or upper-body image with the full hairstyle visible. Stylized portraits are the intended domain.',
                limitations=['Stylized volumetric hair cards, not strand Groom.', 'GLB is static. VRM 0.x includes skinning and spring bones.',
                             'Motion is an MP4 preview, not an animation clip.', 'Head fitting is uniform scale and translation; visual review is required.'])
