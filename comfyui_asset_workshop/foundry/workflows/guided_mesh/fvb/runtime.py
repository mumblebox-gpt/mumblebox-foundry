"""Lab-local configuration and owned artifacts; imports never start generation."""
import json
import os
from pathlib import Path
from .journal import Journal, digest

ROOT=Path(__file__).resolve().parents[1]


def configuration():
    import folder_paths
    from .....finishing.runtime import settings
    config=settings()
    config.update(data_root=str(Path(folder_paths.get_user_directory())/'mumblebox-foundry'/'guided-data'),
        comfy_core=str(Path(folder_paths.__file__).resolve().parent),
        hi3d_url=config.get('hi3d_url','http://127.0.0.1:8378'))
    for key in ('data_root','comfy_core','blender','worker_python'):
        if 'onedrive' in str(config[key]).lower():
            raise ValueError('Active runtime paths must stay outside OneDrive: '+key)
    return config


def journal():
    return Journal(configuration()['data_root'])


def context(ident):
    store=journal(); job=store.read(ident)
    if job['status']!='running' or not job.get('request_id'):
        raise ValueError('This processing node needs an explicitly started owned stage, not an unbound Queue Prompt.')
    return store,job


def artifact(ident,key):
    store=journal(); job=store.read(ident)
    record=job['artifacts'].get(key)
    if not record:
        raise ValueError('Required checkpoint not available: '+key)
    path=store.artifact_path(ident,record['path'])
    if not path.is_file() or digest(path)!=record['sha256']:
        raise ValueError('Checkpoint missing or modified: '+key)
    return path,record


def target(ident,key,suffix):
    store,job=context(ident)
    safe=''.join(c if c.isalnum() or c in '_-' else '_' for c in key)
    relative=f"stages/{job['request_id']}/{safe}{suffix}"
    path=store.artifact_path(ident,relative); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        raise ValueError('Refusing to overwrite an existing immutable artifact: '+relative)
    return path,relative


def record(path,relative,kind,**metadata):
    return dict(path=relative,sha256=digest(path),kind=kind,status='complete',**metadata)


def preview_image(path,ident):
    return preview_file(path,ident)


def preview_file(path,ident):
    import folder_paths
    import shutil
    from .journal import digest
    entry=preview_entry(ident,digest(path),Path(path).suffix.lower())
    relative=Path(entry['subfolder'])/entry['filename']
    dest=Path(folder_paths.get_output_directory())/relative
    if 'onedrive' in str(dest).lower():
        raise ValueError('Configured Comfy output directory is not a safe lab destination.')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():
        shutil.copy2(path,dest)
    return entry


def preview_entry(ident,sha256,suffix):
    """Address the byte-identical published checkpoint through native /view."""
    relative=Path('FoundryViewBridge')/ident/(sha256[:16]+suffix)
    return dict(filename=relative.name,subfolder=relative.parent.as_posix(),type='output')
