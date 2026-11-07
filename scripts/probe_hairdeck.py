"""Import real node entrypoints without opening or downloading any model files."""
import asyncio
import importlib.util
from pathlib import Path
import sys
core,pack=map(Path,sys.argv[1:3]);sys.path.insert(0,str(core))
spec=importlib.util.spec_from_file_location('foundry_hair_probe',pack/'__init__.py',submodule_search_locations=[str(pack)])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
async def probe():
    extension=await module.comfy_entrypoint();nodes=await extension.get_node_list()
    assert {node.define_schema().node_id for node in nodes}=={'HairDeckLoader','HairDeckGenerate','HairDeckSave'}
    import torch
    from hairdeck_core import paths
    # Generation reaches this hub lazily in DinoEncoder. Importing node schemas
    # alone misses its segmentation/logging dependencies. Build on meta with no
    # pretrained weights: no downloads, model files or GPU allocations.
    torch.hub.load(paths.dinov3_repo(), 'dinov3_vitl16', source='local', pretrained=False, device='meta')
    # The generated-card review imports its renderer lazily too. Import the
    # implementation without creating a GL context or rendering any assets.
    from hairdeck_core.vrm.render import _pyrender
    _pyrender()
    print('HairDeck real entrypoints imported:',torch.__version__,flush=True)
asyncio.run(probe())
