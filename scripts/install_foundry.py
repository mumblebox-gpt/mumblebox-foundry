"""Install this release into an existing ComfyUI; preserve models, outputs and prior files."""
import argparse,json,runpy,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]

def install_ccore(host, source):
    requirement=next(line for line in (source/'requirements.txt').read_text(encoding='utf-8').splitlines()
                     if line.startswith('playwright=='))
    wanted=requirement.split('==',1)[1]
    installed=subprocess.run([host,'-c','from importlib.metadata import version; print(version("playwright"))'],
                             capture_output=True,text=True)
    if installed.returncode or installed.stdout.strip()!=wanted:
        subprocess.run([host,'-m','pip','install',requirement],check=True)
    subprocess.run([host,'-m','playwright','install','chromium','--only-shell'],check=True)
    subprocess.run([host,source/'foundry/workflows/ccore_prop/renderer.py','--probe'],check=True)


def install(args):
    core=Path(args.comfy).resolve()
    if not (core/"folder_paths.py").is_file() or not (core/"custom_nodes").is_dir():
        raise ValueError("--comfy must contain folder_paths.py and custom_nodes")
    if "onedrive" in str(core).lower():raise ValueError("Use a local installation outside OneDrive")
    url=urlsplit(args.hi3d_url)
    if url.scheme!="http" or url.hostname not in ("localhost","127.0.0.1","::1") or url.username or url.password or url.query or url.fragment:
        raise ValueError("Hi3D must use a local HTTP service")
    runtime={"comfy_core":str(core),"hi3d_url":args.hi3d_url}
    for key in ("worker_python","trellis_repo","trellis_models","blender"):
        path=Path(getattr(args,key)).resolve()
        if "onedrive" in str(path).lower():raise ValueError("Use runtime paths outside OneDrive")
        if not path.exists():raise FileNotFoundError(f"{key}: {path}")
        runtime[key]=str(path)
    if not (Path(runtime["trellis_repo"])/"__init__.py").is_file():raise ValueError("trellis_repo must contain ComfyUI-Trellis2")
    target=core/"custom_nodes/comfyui_asset_workshop";source=ROOT/"comfyui_asset_workshop"
    if source.resolve()==target.resolve():raise ValueError("Extract the release outside custom_nodes before installing")
    user=Path(args.user_directory).resolve() if args.user_directory else core/"user"
    if "onedrive" in str(user).lower():raise ValueError("Use a user directory outside OneDrive")
    backup=user/"mumblebox-foundry/install-backups"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    config=user/"asset-workshop.json"
    existing=json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    if sys.platform=="win32":
        quad_runtime=runpy.run_path(str(source/"finishing/quad_runtime.py"))
        version=quad_runtime["verify_bundle"]()
        print("Verified CyberRemesher CUDA runtime "+version)
    existing.setdefault("pipeline_runtime",{}).update(runtime)
    hi3d_models=getattr(args,'hi3d_models',None)
    if hi3d_models:
        model_root=Path(hi3d_models).resolve()
        if 'onedrive' in str(model_root).lower():raise ValueError('Use local model storage outside OneDrive')
        existing.setdefault('model_locations',{})['Hi3D models']=str(model_root)
    backup.mkdir(parents=True)
    if config.exists():shutil.copy2(config,backup/"asset-workshop.json")
    changed=[]
    for path in source.rglob("*"):
        rel=path.relative_to(source)
        if not path.is_file() or any(x in ("__pycache__",".venv",".git","node_modules") for x in rel.parts):continue
        dest=target/rel
        if dest.exists():
            if dest.read_bytes()==path.read_bytes():continue
            old=backup/"custom-node"/rel;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,old)
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest);changed.append(rel.as_posix())
    config.parent.mkdir(parents=True,exist_ok=True);pending=config.with_suffix(".json.tmp")
    pending.write_text(json.dumps(existing,indent=2),encoding="utf-8");pending.replace(config)
    (backup/"changed-files.json").write_text(json.dumps(changed,indent=2),encoding="utf-8")
    host=Path(args.host_python).resolve() if getattr(args,'host_python',None) else core/'.venv/Scripts/python.exe'
    if not host.is_file():raise ValueError('Supply --host-python for this ComfyUI installation.')
    install_ccore(host, source)
    if not getattr(args,'skip_hair_software',False):
        from install_hairdeck import install as install_hair
        install_hair(core,host,ROOT)
    print(f"Installed {len(changed)} files. Previous files/config: {backup}")
    print("Restart ComfyUI. Open custom_nodes/comfyui_asset_workshop/workflows/Mumblebox 3D Asset Foundry.json")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy",required=True)
    parser.add_argument("--user-directory",help="Only for a custom ComfyUI --user-directory")
    for key in ("worker-python","trellis-repo","trellis-models","blender"):parser.add_argument("--"+key,required=True)
    parser.add_argument("--hi3d-url",default="http://127.0.0.1:8378")
    parser.add_argument('--hi3d-models',help='The existing Hi3D model directory, included in installed-model management.')
    parser.add_argument('--host-python',help='The ComfyUI host interpreter (required when it has no local .venv).')
    parser.add_argument('--skip-hair-software',action='store_true',help=argparse.SUPPRESS)
    install(parser.parse_args())
