"""Install pinned HairDeck software only. Workflow first use owns all model/tool downloads."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def run(command,**kwargs):
    result=subprocess.run([str(x) for x in command],capture_output=True,text=True,encoding='utf-8',errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,**kwargs)
    if result.stdout:print(result.stdout,flush=True)
    if result.returncode:raise RuntimeError('HairDeck software install failed: '+result.stderr[-2500:])

def install(core,python,source=ROOT):
    core=Path(core).resolve();python=Path(python).resolve();source=Path(source).resolve()
    if 'onedrive' in str(core).lower():raise ValueError('Install outside OneDrive.')
    spec=json.loads((source/'dependencies.json').read_text(encoding='utf-8'))['hairdeck_wrapper']
    cache=core/'user/mumblebox-foundry/software/hairdeck'
    if not (cache/'.git').is_dir():
        cache.parent.mkdir(parents=True,exist_ok=True);run(['git','clone',spec['repository'],cache])
    if subprocess.check_output(['git','-C',str(cache),'rev-parse','HEAD'],text=True).strip()!=spec['revision']:
        if subprocess.check_output(['git','-C',str(cache),'status','--porcelain'],text=True).strip():raise ValueError('HairDeck source has local changes; preserved it instead of overwriting.')
        run(['git','-C',cache,'fetch','origin',spec['revision']]);run(['git','-C',cache,'checkout','--detach',spec['revision']])
    # The host's Torch is installed separately. A constraint prevents upstream
    # dependency resolution from silently swapping that qualified build.
    constraints=cache.parent/'hair-host-constraints.txt'
    torch_version=subprocess.check_output([str(python),'-c','import torch; print(torch.__version__)'],text=True).strip()
    constraints.write_text('torch=='+torch_version+'\n',encoding='utf-8')
    run(['uv','pip','install','--python',python,'--constraint',constraints.name,'-r',source/spec['requirements']],cwd=constraints.parent)
    target=core/'custom_nodes/ComfyUI-HairDeck';target.mkdir(parents=True,exist_ok=True)
    from datetime import datetime,timezone
    backup=core/'user/mumblebox-foundry/install-backups'/('hair-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    for path in cache.rglob('*'):
        rel=path.relative_to(cache)
        if not path.is_file() or any(x in ('.git','__pycache__','.venv') for x in rel.parts):continue
        dest=target/rel
        if dest.exists() and dest.read_bytes()!=path.read_bytes():
            old=backup/rel;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,old)
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    (target/'foundry-source.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    probe=source/'scripts/probe_hairdeck.py'
    run([python,probe,core,target])
    print('HairDeck software ready. No model weights or export tools were downloaded by installation.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--comfy',type=Path,required=True)
    parser.add_argument('--python',type=Path,required=True);args=parser.parse_args();install(args.comfy,args.python)
