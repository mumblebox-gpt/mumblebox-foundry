"""Locate the installed upstream once, without importing any weights on app startup."""
import importlib
import json
import subprocess
import sys
from pathlib import Path


def upstream():
    import nodes
    cls = nodes.NODE_CLASS_MAPPINGS.get('HairDeckGenerate')
    if cls is None: raise RuntimeError('Install the pinned ComfyUI-HairDeck node pack and restart ComfyUI.')
    return importlib.import_module(cls.__module__)


def models_root():
    import folder_paths
    return Path(folder_paths.models_dir).resolve() / 'hairdeck'


def ensure(config, cancelled, progress):
    """Explicit first-use preparation; never triggered by opening Foundry or installing it."""
    from ...artifacts import digest
    import os
    native = upstream(); root = models_root(); root.mkdir(parents=True, exist_ok=True)
    script = Path(native.__file__).parent / 'install_models.py'
    command = [sys.executable, str(Path(__file__).with_name('prepare.py')), '--pack',str(script.parent),'--models-dir', str(root)]
    if config.get('colors',True):command.append('--colors')
    if config['vrm'] or config['motion']: command.append('--with-blender')
    # The upstream transport already pins hashes and resumes bounded chunks. Its
    # public sources match the official HairDeck distributions; no token is sent.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    import queue, threading, time
    lines = queue.Queue()
    def drain():
        for line in process.stdout: lines.put(line.strip())
    threading.Thread(target=drain, daemon=True).start(); tail=[]
    try:
        while process.poll() is None or not lines.empty():
            if cancelled(): raise InterruptedError('Hair preparation cancelled; partial downloads can resume.')
            try:
                line = lines.get(timeout=.2); tail.append(line); tail=tail[-16:]
                progress({'phase': 'preparing hair resources', 'name': line,
                          'message': 'The model is downloading on first use. This may take some time but only happens once per model.'})
            except queue.Empty: pass
        if process.returncode: raise RuntimeError('Hair resource preparation failed: '+'\n'.join(tail))
    finally:
        if process.poll() is None: process.terminate(); process.wait(timeout=15)
    # Existing files are preserved, but independently verify the pinned manifest.
    manifest = json.loads((root/'MANIFEST.json').read_text(encoding='utf-8'))['files']
    install = importlib.util.spec_from_file_location('_foundry_hair_installer', script)
    module = importlib.util.module_from_spec(install); install.loader.exec_module(module)
    receipts_path = root/'foundry-verification.json'
    try: receipts=json.loads(receipts_path.read_text(encoding='utf-8'))
    except (OSError, ValueError): receipts={}
    selected={name:meta['sha256'] for name,meta in manifest.items() if name.startswith(('ckpt/card_vae/','ckpt/image_model/','ckpt/chain_model/','data/avatar/')) and 'latents_test' not in name}
    selected.update({name:manifest[name]['sha256'] for name in native.model_files.RESOURCE_FILES})
    selected.update({name:sha for _,name,sha in module.THIRD_PARTY})
    for name, sha in selected.items():
        if cancelled(): raise InterruptedError('Cancelled during hair resource verification.')
        path=root/name; stat=path.stat(); identity=[stat.st_size,stat.st_mtime_ns,sha]
        if receipts.get(name)!=identity:
            progress({'phase':'verifying hair resources','name':name})
            if digest(path)!=sha: raise ValueError('Hair resource checksum mismatch; preserved '+name)
            receipts[name]=identity
    receipts_path.write_text(json.dumps(receipts),encoding='utf-8')
    native.model_files.register()
    files=native.model_files.resolve('hairdeck', config['checkpoints'])
    if config['head_profile'] not in native.heads.choices([root]): raise ValueError('The selected reference-head profile is not installed.')
    selected_models={}
    if config.get('colors',True):
        from .prepare import color_resource
        color=color_resource();path=root/color['name']
        if path.stat().st_size!=color['size'] or digest(path)!=color['sha256']:raise ValueError('The HairDeck color checkpoint failed verification.')
        selected_models['color_model']={'filename':color['name'],'bytes':color['size'],'sha256':color['sha256'],'pinned_default':True}
    for role,name in config['checkpoints'].items():
        path=getattr(files,role);stat=path.stat()
        relative=path.relative_to(root).as_posix() if path.is_relative_to(root) else None
        receipt=receipts.get(relative)
        sha=receipt[2] if receipt and receipt[:2]==[stat.st_size,stat.st_mtime_ns] else digest(path)
        selected_models[role]={'filename':name,'bytes':stat.st_size,'sha256':sha,'pinned_default':relative in selected and selected.get(relative)==sha}
    return selected_models
