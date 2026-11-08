"""Apply a published Foundry release, or repair software, without replacing user data."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from urllib.request import urlopen
from urllib.error import URLError
from bootstrap import Layout, atomic_json, capture, download, extract_checked, install, run
from runtime import InstallationLock


REPOSITORY='https://github.com/mumblebox-gpt/mumblebox-foundry'


def require_idle(root,read=None):
    """Check both Foundry jobs and the Comfy queue before stopping this installation."""
    runtime=Path(root)/'.pinokio'/'runtime.json'
    if not runtime.exists():return
    record=json.loads(runtime.read_text(encoding='utf-8'))
    base=record['comfy_url']
    if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+',base):
        raise ValueError('Invalid local Foundry service address.')
    def request(path):
        with urlopen(base+path,timeout=5) as response:
            return json.loads(response.read(1024*1024))
    read=read or request
    try:
        status=read('/asset-workshop/status');queue=read('/queue')
    except URLError as error:
        # A closed backend can leave its runtime receipt behind. Only a refused
        # connection AND a confirmed exited runtime establish that it is stopped.
        if not isinstance(error.reason,ConnectionRefusedError):raise
        import psutil
        pid=record.get('pid')
        if not isinstance(pid,int) or pid<=0:
            raise ValueError('Cannot verify the saved Foundry runtime process.') from error
        try:psutil.Process(pid)
        except psutil.NoSuchProcess:
            print('Foundry runtime has exited; no backend is listening. Safe to update.',flush=True)
            return
        raise ValueError('Foundry backend is unavailable but its runtime is still running. Wait for startup or stop it before updating.') from error
    if status.get('running') or queue.get('queue_running') or queue.get('queue_pending'):
        raise ValueError('A generation is active or queued. Finish or cancel it before updating. Foundry was not stopped.')
    print('Foundry is idle; it can be stopped safely for the update.',flush=True)


def stop_owned_runtime(root):
    """Pinokio may close its terminal while its Python child is still running."""
    import psutil
    root=Path(root).resolve();runtime=root/'.pinokio'/'runtime.json'
    if not runtime.exists():return
    record=json.loads(runtime.read_text(encoding='utf-8'))
    try:process=psutil.Process(record['pid'])
    except psutil.NoSuchProcess:return
    command=process.cmdline();cwd=Path(process.cwd()).resolve()
    script=next((arg for arg in command[1:] if arg.endswith('runtime.py')),None)
    if not script or (cwd/script).resolve()!=root/'scripts'/'pinokio'/'runtime.py' or cwd!=root:
        raise ValueError('The saved process is not this Foundry runtime. No process was stopped.')
    require_idle(root)
    # Closing this exact runtime also closes its Windows job object, which owns
    # only this installation's ComfyUI and Hi3D process trees.
    process.terminate();process.wait(timeout=20)
    if runtime.exists() and json.loads(runtime.read_text()).get('instance')==record.get('instance'):
        runtime.unlink()
    print('Stopped this installation\'s owned runtime.',flush=True)


def require_clean_checkout(root):
    if not (root/'.git').exists():
        raise ValueError('Update requires the GitHub checkout installed by Pinokio. Your files were preserved.')
    if capture(['git','remote','get-url','origin'],root).removesuffix('.git') != REPOSITORY:
        raise ValueError('This checkout does not use the official Foundry repository.')
    if capture(['git','status','--porcelain','--untracked-files=no'],root):
        raise ValueError('This checkout has local source changes. Preserve or commit them before updating; nothing was overwritten.')
    return capture(['git','rev-parse','HEAD'],root)


def release_policy(root):
    # Reuse the GUI release-channel and trusted-URL policy without importing ComfyUI.
    package=root/'comfyui_asset_workshop'/'foundry'
    name='_foundry_release_policy'
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    from importlib import import_module
    return import_module(name+'.updates')


def select_download(root,current,tag=None):
    policy=release_policy(root)
    status,releases,_=policy.fetch_releases({})
    if status!=200 or not isinstance(releases,list):raise ValueError('GitHub release information is unavailable. Retry Update later.')
    if tag:releases=[r for r in releases if r.get('tag_name')==tag]
    selected=policy.select_release(releases,policy.Version(current))
    if not selected:raise ValueError('No eligible published release was found.')
    version,details=selected
    if version<=policy.Version(current):return None
    release=next(r for r in releases if r['html_url']==details['release_url'])
    asset=next((a for a in release.get('assets',[]) if a.get('browser_download_url')==details['download_url']),None)
    digest=(asset or {}).get('digest','')
    if not asset or not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):
        raise ValueError('This release has no verifiable Foundry archive yet. No update was installed.')
    return {'tag':release['tag_name'],'url':details['download_url'],'sha256':digest[7:]}


def verify_bundle(directory):
    """A release inventory owns application files only, never .pinokio or user state."""
    directory=Path(directory)
    hashes=json.loads((directory/'SHA256SUMS.json').read_text(encoding='utf-8'))
    if not isinstance(hashes,dict) or not hashes:raise ValueError('Release inventory is empty.')
    allowed_roots={'comfyui_asset_workshop','scripts','docs','licenses'}
    allowed_files={'README.md','CHANGELOG.md','INSTALL.md','THIRD-PARTY.md','LICENSE','NOTICE',
                   'dependencies.json','requirements-worker-windows.txt','pinokio.js','pinokio.json',
                   'install.js','start.js','update.js','repair.js','icon.png'}
    for name,digest in hashes.items():
        path=PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name
                or not path.parts or (path.parts[0] not in allowed_roots and name not in allowed_files)):
            raise ValueError('Release inventory contains a path outside application ownership.')
        file=directory.joinpath(*path.parts)
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
            raise ValueError(f'Release checksum did not match: {name}')
    actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual!=set(hashes)|{'SHA256SUMS.json'}:raise ValueError('Release contains unlisted files.')
    return hashes


def verify_tag_files(root,tag,hashes,archive):
    run(['git','fetch','origin','tag',tag],root)
    run(['git','archive','--format=zip','--output',archive,tag],root)
    with zipfile.ZipFile(archive) as source:
        for name,digest in hashes.items():
            if name not in source.namelist() or hashlib.sha256(source.read(name)).hexdigest()!=digest:
                raise ValueError(f'Published archive disagrees with its Git tag: {name}')
    # Git protects tracked edits; this also protects untracked paths a new tag will own.
    for name in hashes:
        existing=root/name
        tracked=capture(['git','ls-files','--',name],root)
        if existing.exists() and not tracked:
            raise ValueError(f'Preserving local untracked file that conflicts with the update: {name}')


def checkpoint(layout,backup):
    paths={
        'extension':layout.comfy/'custom_nodes'/'comfyui_asset_workshop',
        'config.json':layout.data/'user'/'asset-workshop.json',
        'installed.json':layout.state/'installed.json'}
    backup.mkdir(parents=True)
    for name,path in paths.items():
        if path.is_dir():shutil.copytree(path,backup/name)
        elif path.is_file():shutil.copy2(path,backup/name)
    return paths


def restore_checkpoint(paths,backup):
    for name,path in paths.items():
        previous=backup/name
        if previous.is_dir():
            # Preserve the failed extension for diagnosis, including new files.
            if path.exists():path.rename(backup/'failed-extension')
            shutil.copytree(previous,path)
        elif previous.is_file():shutil.copy2(previous,path)


def apply_staged(layout,staged,tag,old_commit,installer=None):
    backup=layout.state/'update-backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    paths=checkpoint(layout,backup)
    try:
        if installer is None:
            spec=importlib.util.spec_from_file_location('_foundry_staged_bootstrap',staged/'scripts'/'pinokio'/'bootstrap.py')
            candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
            installer=candidate.install
        installer(layout.root,staged)
        run(['git','checkout','--detach',tag],layout.root)
    except Exception:
        restore_checkpoint(paths,backup)
        atomic_json(layout.state/'repair-required.json',{'previous_commit':old_commit,'backup':str(backup),
            'message':'Application and config restored. Dependencies may have changed; run Repair software before Start.'})
        raise
    atomic_json(backup/'result.json',{'previous_commit':old_commit,'installed_tag':tag})
    (layout.state/'repair-required.json').unlink(missing_ok=True)
    print(f'Updated to {tag}. Previous application/config: {backup}',flush=True)


def maintain(root,action,tag=None):
    if action=='check-idle':
        require_idle(root);return
    if action=='stop-owned':
        stop_owned_runtime(root);return
    layout=Layout(root)
    with InstallationLock(layout.state/'operation.lock'):
        if action=='repair':
            print(f'Repairing deployment software under {layout.software} and {layout.state / "envs"}. Saved assets, settings and model weights are preserved.',flush=True)
            install(layout.root,repair=True)
            (layout.state/'repair-required.json').unlink(missing_ok=True)
        else:
            previous=require_clean_checkout(layout.root)
            current=json.loads((layout.state/'installed.json').read_text())['version']
            release=select_download(layout.root,current,tag)
            if not release:print('Foundry is already on the newest eligible release.',flush=True);return
            if not re.fullmatch(r'v?[0-9][A-Za-z0-9.+-]*',release['tag']):raise ValueError('Invalid release tag.')
            stage=layout.state/'releases'/(release['tag']+'-'+uuid.uuid4().hex[:8])
            archive=stage/'release.zip'
            download(release['url'],archive,release['sha256'])
            with zipfile.ZipFile(archive) as bundle:
                if sum(i.file_size for i in bundle.infolist())>1024**3:raise ValueError('Application archive exceeds the size limit.')
            extracted=stage/'source';extract_checked(archive,extracted)
            hashes=verify_bundle(extracted)
            verify_tag_files(layout.root,release['tag'],hashes,stage/'git-source.zip')
            apply_staged(layout,extracted,release['tag'],previous)
        print('Foundry maintenance completed.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('update','repair','check-idle','stop-owned'))
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--release-tag')
    args=parser.parse_args()
    try:maintain(args.root,args.action,args.release_tag)
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as error:
        print(f'Foundry maintenance stopped: {error}',file=sys.stderr,flush=True);sys.exit(1)
