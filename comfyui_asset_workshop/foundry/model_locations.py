"""Registered runtime locations; deletion requests never supply a filesystem root."""
import os
from pathlib import Path

def registered_locations():
    import folder_paths
    from ..runtime import configuration
    result=[]
    def add(path,label,workflows=()):
        if path and Path(path).is_dir():result.append({'path':str(Path(path).resolve()),'label':label,'workflows':list(workflows)})
    add(folder_paths.models_dir,'ComfyUI models')
    for category,entry in folder_paths.folder_names_and_paths.items():
        if category=='custom_nodes':continue # Code trees are not model stores.
        for path in entry[0]:add(path,'ComfyUI / '+category)
    config=configuration();runtime=config.get('pipeline_runtime',{})
    add(runtime.get('trellis_models'),'TRELLIS.2 worker',('Turnaround','3D-Guided'))
    for label,path in config.get('model_locations',{}).items():add(path,label,('Hi3D',) if 'hi3d' in label.lower() else ())
    cache=os.environ.get('HF_HOME')
    add(Path(cache)/'hub' if cache else Path.home()/'.cache/huggingface/hub','Hugging Face model cache')
    add(os.environ.get('HUGGINGFACE_HUB_CACHE'),'Hugging Face model cache')
    add(os.environ.get('HF_HUB_CACHE'),'Hugging Face model cache')
    return result

def invalidate_model_lists():
    import folder_paths
    folder_paths.filename_list_cache.clear()
