"""Install software into one Pinokio checkout; model acquisition remains owned by Foundry."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile


class Layout:
    def __init__(self, root):
        self.root=Path(root).resolve()
        if 'onedrive' in str(self.root).lower():
            raise ValueError('Install Foundry outside OneDrive or another synchronized folder.')
        self.state=self.root/'.pinokio'
        self.software=self.state/'software'
        self.data=self.state/'data'
        self.comfy=self.software/'comfyui'
        self.trellis=self.software/'trellis'
        self.hi3d=self.software/'hi3d'
        self.host_python=self.python('host')
        self.worker_python=self.python('worker')
        self.mcp_python=self.python('mcp')
    def python(self,name):
        return self.state/'envs'/name/'Scripts'/'python.exe'


def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8')
    temporary.replace(path)


class StepState:
    def __init__(self,path,repair=False):
        self.path=Path(path);self.repair=repair
        self.values=json.loads(self.path.read_text()) if self.path.exists() else {}
    def run(self,name,fingerprint,operation):
        if not self.repair and self.values.get(name)==fingerprint:
            print(f'[Installed] {name}',flush=True);return
        self.values.pop(name,None);atomic_json(self.path,self.values)
        print(f'[Installing software] {name}',flush=True)
        operation()
        self.values[name]=fingerprint;atomic_json(self.path,self.values)


def run(arguments,cwd=None,env=None):
    subprocess.run([str(v) for v in arguments],cwd=cwd,env=env,check=True)


def capture(arguments,cwd=None,env=None):
    return subprocess.check_output([str(v) for v in arguments],cwd=cwd,env=env,text=True).strip()


def managed_python(uv,version):
    # Pinokio may set the legacy preference; uv rejects it together with this flag.
    env=os.environ.copy()
    env.pop('UV_PYTHON_PREFERENCE',None)
    return capture([uv,'python','find','--managed-python',version],env=env)


def checkout(spec,destination):
    destination=Path(destination)
    if not destination.exists():
        destination.parent.mkdir(parents=True,exist_ok=True)
        run(['git','clone',spec['repository'],destination])
    if not (destination/'.git').exists():raise ValueError(f'Unrecognized software directory: {destination}')
    # A prior interrupted --no-checkout clone has only .git, not user edits.
    empty_checkout = all(path.name == '.git' for path in destination.iterdir())
    if not empty_checkout and capture(['git','status','--porcelain','--untracked-files=no'],destination):
        raise ValueError(f'Preserving modified upstream software. Resolve edits in {destination} before updating.')
    if capture(['git','remote','get-url','origin'],destination).removesuffix('.git')!=spec['repository'].removesuffix('.git'):
        raise ValueError(f'Unexpected repository at {destination}')
    run(['git','fetch','origin',spec['revision']],destination)
    run(['git','checkout','--detach',spec['revision']],destination)


def extract_checked(archive,destination):
    destination=Path(destination).resolve()
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            target=(destination/item.filename).resolve()
            if not target.is_relative_to(destination) or '\\' in item.filename:
                raise ValueError('Archive contains an unsafe path')
        bundle.extractall(destination)


def download(url,path,sha256):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    def digest(p):
        with p.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
    if path.exists() and digest(path)==sha256:return
    temporary=path.with_suffix(path.suffix+'.partial')
    print(f'Downloading software: {path.name}',flush=True)
    request=urllib.request.Request(url,headers={'User-Agent':'Mumblebox-Foundry (+https://github.com/mumblebox-gpt/mumblebox-foundry)'})
    with urllib.request.urlopen(request,timeout=60) as response,temporary.open('wb') as output:
        size=int(response.headers.get('Content-Length',0));received=0;report=0
        while block:=response.read(8*1024*1024):
            output.write(block);received+=len(block)
            if received-report>=64*1024*1024:
                print(f'{path.name}: {received//1048576} / {size//1048576} MB',flush=True);report=received
    if digest(temporary)!=sha256:raise ValueError('Software checksum did not match; download was not installed.')
    temporary.replace(path)


def hi3d_setup_commands(root,python):
    """Mirror pinned upstream Setup.ps1 using argv, avoiding Windows PowerShell quote loss."""
    worker=root/'.venv'/'Scripts'/'python.exe'
    commands=[]
    if not worker.exists():commands.append([python,'-m','venv',root/'.venv'])
    commands.extend([
        [worker,'-m','pip','install','--upgrade','pip'],
        [worker,'-m','pip','install','torch==2.11.0+cu128','torchvision==0.26.0+cu128',
         '--index-url','https://download.pytorch.org/whl/cu128'],
        [worker,'-m','pip','install','-r',root/'requirements-worker-windows.txt'],
        [worker,'-m','pip','install',str(root)+'[workbench]']])
    return commands


def native_wheels(directory,abi):
    """Select our dependencies, ignoring unrelated wheels bundled by upstream."""
    selected=[]
    for package in ('cumesh','flex_gemm','nvdiffrast','nvdiffrec_render','o_voxel'):
        matches=sorted(Path(directory).glob(f'{package}-*-{abi}.whl'))
        if len(matches)!=1:
            raise ValueError(f'Expected one {package} wheel for {abi}; found {len(matches)} in {directory}')
        selected.append(matches[0])
    return selected


def install_extension(layout,blender,source,port=8378):
    run([sys.executable,source/'scripts'/'install_foundry.py','--comfy',layout.comfy,
         '--user-directory',layout.data/'user','--worker-python',layout.worker_python,
         '--trellis-repo',layout.trellis,'--trellis-models',layout.data/'trellis-models',
         '--blender',blender,'--host-python',layout.host_python,'--hi3d-url',f'http://127.0.0.1:{port}',
         '--hi3d-models',layout.hi3d/'models'])


def install(root,source=None,repair=False):
    if sys.platform!='win32':raise ValueError('This beta installer currently supports Windows with NVIDIA GPUs.')
    layout=Layout(root);source=Path(source or root).resolve()
    manifest=json.loads((source/'dependencies.json').read_text(encoding='utf-8-sig'))
    uv=shutil.which('uv')
    if not uv:raise ValueError('uv is missing. Install the Pinokio AI bundle and retry Install.')
    for path in [layout.software,layout.data/'user',layout.data/'input',layout.data/'output',layout.data/'temp',layout.data/'models',layout.data/'trellis-models']:
        path.mkdir(parents=True,exist_ok=True)
    state=StepState(layout.state/'steps.json',repair)
    def step(name,value,operation):
        fingerprint=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
        state.run(name,fingerprint,operation)
    def venv(python,version):
        if not python.exists():run([uv,'venv','--seed','--python',version,python.parent.parent])
    def pip(python,*args):run([uv,'pip','install','--python',python,*args])
    for key,dest in [('comfyui',layout.comfy),('trellis_wrapper',layout.trellis),('hi3d_workbench',layout.hi3d)]:
        spec=manifest[key]
        step(key+' source',spec,lambda s=spec,d=dest:checkout(s,d))
    host=manifest['comfyui'];worker=manifest['trellis_wrapper']
    orbit_nodes=manifest.get('orbit_kjnodes')
    if orbit_nodes:
        step('Orbit KJNodes source', orbit_nodes,
             lambda: checkout(orbit_nodes, layout.comfy/'custom_nodes'/'ComfyUI-KJNodes'))
    step('host Python',host['python'],lambda:venv(layout.host_python,host['python']))
    step('worker Python',worker['python'],lambda:venv(layout.worker_python,worker['python']))
    step('MCP Python',host['python'],lambda:venv(layout.mcp_python,host['python']))
    # Upstream core pins a different frontend. Select the inspected, tested frontend explicitly.
    requirements=layout.state/'host-requirements.txt'
    original=(layout.comfy/'requirements.txt').read_text()
    # ComfyUI already supplies Pillow and the full OpenCV wheel for KJNodes.
    orbit_packages=orbit_nodes['packages'] if orbit_nodes else []
    requirements.write_text('\n'.join(line for line in original.splitlines() if not line.startswith('comfyui-frontend-package'))+'\n'+
        '\n'.join(host['packages']+orbit_packages)+'\ncomfyui-frontend-package=='+host['frontend']+'\n',encoding='utf-8')
    torch_index='https://download.pytorch.org/whl/cu130'
    step('host CUDA packages',[host['torch'],host['torchvision']],lambda:pip(layout.host_python,
         'torch=='+host['torch'],'torchvision=='+host['torchvision'],'--index-url',torch_index))
    step('ComfyUI packages',[requirements.read_text(),(source/'comfyui_asset_workshop'/'requirements.txt').read_text()],lambda:pip(layout.host_python,'-r',requirements,'-r',source/'comfyui_asset_workshop'/'requirements.txt'))
    step('worker CUDA packages',[worker['torch'],worker['torchvision']],lambda:pip(layout.worker_python,
         'torch=='+worker['torch'],'torchvision=='+worker['torchvision'],'--index-url',torch_index))
    worker_requirements=source/'requirements-worker-windows.txt'
    step('finishing packages',worker_requirements.read_text(),lambda:pip(layout.worker_python,'-r',worker_requirements))
    wheels=native_wheels(layout.trellis/worker['wheel_directory'],worker['wheel_abi'])
    step('native finishing wheels',[worker['revision'],[p.name for p in wheels]],lambda:pip(layout.worker_python,*wheels))
    def setup_hi3d():
        run([uv,'python','install',manifest['hi3d_workbench']['python']])
        python=managed_python(uv,manifest['hi3d_workbench']['python'])
        for command in hi3d_setup_commands(layout.hi3d,Path(python)):
            run(command,cwd=layout.hi3d)
        checkout({'repository':'https://github.com/hi3d-official/Hi3Dv1.0.git',
                  'revision':'23dcc684bc6e1fab86ecafb99ec5270edad122f9'},layout.hi3d/'upstream'/'Hi3Dv1.0')
        run([layout.hi3d/'.venv'/'Scripts'/'python.exe','-m','hi3d_workbench.worker','--diagnose','--probe'],cwd=layout.hi3d)
    step('Hi3D software',manifest['hi3d_workbench'],setup_hi3d)
    step('agent MCP',manifest['mcp'],lambda:pip(layout.mcp_python,'mcp=='+manifest['mcp']['sdk']))
    blender_spec=manifest['blender_portable'];archive=layout.state/'downloads'/blender_spec['filename']
    blender=layout.software/blender_spec['folder']/'blender.exe'
    def setup_blender():
        download(blender_spec['url'],archive,blender_spec['sha256'])
        extract_checked(archive,layout.software)
        run([blender,'--background','--factory-startup','--version'])
    step('Blender',blender_spec,setup_blender)
    install_extension(layout,blender,source)
    # Probe software imports without loading weights or allocating GPU models.
    run([layout.host_python,'-c','import torch,torchvision,trimesh,keyring,scipy,networkx; from trimesh.poses import compute_stable_poses; print("Host imports and stable support-pose entry point OK",torch.__version__)'])
    run([layout.host_python,'-c','import sys; sys.path.insert(0,sys.argv[1]); from comfy.ldm.moge.model import MoGeModel; from PIL import Image; import numpy,psutil; print("Guided camera/render adapter imports OK")',layout.comfy])
    run([layout.worker_python,'-c','import torch,cumesh,flex_gemm,nvdiffrast,nvdiffrec_render,o_voxel,pymeshlab,meshlib,pyquadriflow,pynanoinstantmeshes; print("Finishing and quad solver imports OK",torch.__version__)'])
    run([layout.host_python,'-c','import sys; sys.path.insert(0,sys.argv[1]); import comfy_extras.nodes_triposplat,comfy_extras.nodes_gaussian_splat,comfy_extras.nodes_mesh_postprocess,comfy_extras.nodes_mesh_io; print("Native Idol splat, mesh extraction and cleanup imports OK")',layout.comfy])
    run([layout.worker_python,'-c','import runpy,sys; runpy.run_path(sys.argv[1],run_name="splat_quality_probe"); import numpy,trimesh,pymeshlab; print("Splat geometry audit imports OK")',layout.comfy/'custom_nodes/comfyui_asset_workshop/foundry/workflows/splat_solid/quality.py'])
    # Import the real texture entry point, including its ComfyUI dependencies.
    # A native-wheel-only probe misses libraries inherited from developer installs.
    texture_probe=layout.state/'texture-probe.json'
    atomic_json(texture_probe,{'comfy_core':str(layout.comfy),'trellis_repo':str(layout.trellis),
                               'trellis_models':str(layout.data/'trellis-models')})
    run([layout.worker_python,layout.comfy/'custom_nodes'/'comfyui_asset_workshop'/
         'pipeline_workers'/'trellis_texture_worker.py',texture_probe,'--probe'])
    if orbit_nodes:
        run([layout.host_python, '-c',
             'import importlib,sys; sys.path.insert(0,sys.argv[1]); '
             'from comfy_extras.nodes_minimax_h3 import PH3ImageConditioning, MiniMaxH3ImageToVideo; '
             'nodes=importlib.import_module("custom_nodes.ComfyUI-KJNodes").NODE_CLASS_MAPPINGS; '
             'assert {"MiniMaxChunkFeedForward","MiniMaxLowVRAMAttention"} <= nodes.keys(); '
             'print("Native H3 image, video and KJNodes memory controls OK")', layout.comfy])
    run([layout.mcp_python,'-c','from mcp.server import MCPServer; print("MCP imports OK")'])
    record={'schema':1,'version':manifest['version'],'blender':str(blender.relative_to(layout.root)),
            'models_downloaded_by_installer':False,'hi3d_workspace':str(layout.hi3d.relative_to(layout.root))}
    atomic_json(layout.state/'installed.json',record)
    print('Foundry software is installed. Model weights download only on first use.',flush=True)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--source',type=Path)
    parser.add_argument('--repair',action='store_true')
    args=parser.parse_args()
    try:
        from runtime import InstallationLock
        with InstallationLock(Layout(args.root).state/'operation.lock'):
            install(args.root,args.source,args.repair)
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as error:
        print(f'Installation stopped: {error}\nCompleted software and user data were preserved. Retry Install or Repair.',file=sys.stderr,flush=True)
        sys.exit(1)
