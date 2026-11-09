"""Adapt the established native model recipes to creator-owned image inputs/outputs."""
import copy
import importlib
from .prompts import compile_prompt

ROOT=__package__.split('.foundry',1)[0]


def recipe_asset(config,seed,references):
    store=importlib.import_module(ROOT+'.store')
    settings=store.default_settings()
    settings.update(resolution=config['settings']['resolution'],steps=config['settings']['steps'],
                    cfg=config['settings']['cfg'],seed=seed,image_checkpoint=config['checkpoint'],
                    sdxl_negative_prompt=config['settings']['negative_prompt'],
                    sdxl_reference_strength=config['settings']['reference_strength'],
                    sdxl_edit_denoise=config['settings']['edit_denoise'])
    return {'id':'foundry-image-creator','profile':config['model'],'prompt':config['description'],
            'category':config['category'],'settings':settings,'references':references,'loras':config['loras'],
            'memory_preset_id':'default','preset_overrides':{},'schema_version':2}


def compile_stage(record,side,seed,references,attempt,edit=None):
    recipes=importlib.import_module(ROOT+'.recipes')
    refs=[{**item,'file':item['filename'],'instructions':item.get('description','')} for item in references]
    asset=recipe_asset(record['config'],seed,refs)
    contract=compile_prompt(record['config'],side,edit=edit['prompt'] if edit else None)
    graph,details,bindings=recipes.image_recipe(asset,{'id':attempt},side,'generate',
        task_contract=contract,references=refs,edit=edit)
    nodes=copy.deepcopy(graph.nodes);output=None
    for node_id,node in nodes.items():
        inputs=node['inputs']
        if node['class_type']=='AW_LoadImage':
            node['class_type']='FoundryLoadCreationImage'
            node['inputs']={'filename':inputs['relative_path'],'sha256':inputs.get('expected_sha256','')}
        elif node['class_type']=='AW_SaveImage':
            node['class_type']='FoundrySaveCreationImage'
            node['inputs']={'image':inputs['image'],'creation_id':record['id'],'attempt_id':attempt,
                            'recipe':inputs['recipe']}
            for key,value in inputs.items():
                if key.startswith('lora_reports.lora'):node['inputs']['report'+key.rsplit('lora',1)[1]]=value
            output=node_id
    if output is None:raise ValueError('The selected image recipe has no image output.')
    # A separate ID range keeps queue progress/output events off the 3D nodes.
    offset=660000 if record.get('graph_scope')=='ccore-reference' else 60000
    mapping={ident:str(offset+index) for index,ident in enumerate(nodes)}
    for node in nodes.values():
        for key,value in node['inputs'].items():
            if isinstance(value,list) and len(value)==2 and str(value[0]) in mapping:
                node['inputs'][key]=[mapping[str(value[0])],value[1]]
    return {'graph':{mapping[k]:v for k,v in nodes.items()},'output_node':mapping[output],
            'provenance':details,'bindings':bindings}


def ensure_models(record,seed,references,cancelled,progress):
    """Only the selected recipe's dependencies; shared downloader owns transport/hash checks."""
    models=importlib.import_module(ROOT+'.models');recipes=importlib.import_module(ROOT+'.recipes')
    memory=importlib.import_module(ROOT+'.memory_policy')
    asset=recipe_asset(record['config'],seed,references)
    memory.preflight(asset,'image')
    keys=recipes.required_models(asset,'image',action='reference_view' if references else 'create_image')
    if record['config']['paired']:
        # The back image conditions on the generated front. Prepare its adapter
        # before generating that front, even when no upload was supplied.
        keys = list(dict.fromkeys([*keys, *recipes.required_models(asset,'image',action='reference_view')]))
    for key in keys:
        if cancelled():raise InterruptedError('Image generation cancelled before model loading.')
        if models.installed(key) is None:
            if not models.DOWNLOAD_LOCK.acquire(blocking=False):raise ValueError('Another model download is running. Retry after it finishes.')
            try:
                models.DOWNLOAD.update(status='running',cancel=False,owner=record['id'])
                progress({'phase':'downloading','name':models.MODELS[key]['name']})
                models.download_one(models.MODELS[key]);models.DOWNLOAD.update(status='complete')
            except Exception as error:
                models.DOWNLOAD.update(status='failed',error=str(error));raise
            finally:models.DOWNLOAD_LOCK.release()
    progress({'phase':'verifying selected models'})
    models.verify(keys);recipes.selected_image_model(asset,True)


def cancel_download(ident):
    models=importlib.import_module(ROOT+'.models')
    if models.DOWNLOAD.get('owner')==ident:models.DOWNLOAD['cancel']=True
