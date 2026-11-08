"""Probe the real official color adapter and color conversion; no weights or GPU allocation."""
import importlib.util
from pathlib import Path
import sys
import numpy as np

core,pack,source=map(Path,sys.argv[1:4]);sys.path.insert(0,str(core));sys.path.insert(0,str(pack/'_vendor'))
path=source/'comfyui_asset_workshop/foundry/workflows/hair_creation/upstream_color.py'
spec=importlib.util.spec_from_file_location('_foundry_official_hair_color',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
converted=module.lab_to_srgb(np.array([[[50.,0.,0.]]]))
assert converted.shape==(1,1,3) and np.isfinite(converted).all()
print('Official HairDeck ColorDiT entrypoint and CIELAB conversion imported; no model loaded.')
