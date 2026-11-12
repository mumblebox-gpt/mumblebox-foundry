"""Own one isolated Foundry session and its two local services, never other installations."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from bootstrap import Layout, atomic_json, install_extension


class InstallationLock:
    """The OS releases this lock even if Pinokio terminates the launcher."""
    def __init__(self,path):self.path=Path(path);self.file=None
    def __enter__(self):
        import msvcrt
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('a+b')
        try:
            if os.fstat(self.file.fileno()).st_size == 0:self.file.write(b'0');self.file.flush()
            self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.file.close();self.file=None
            raise RuntimeError('This Foundry installation is already running or being maintained. Stop it before Install, Update or Repair.') from None
        return self
    def __exit__(self,*args):
        import msvcrt
        if self.file:
            self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            self.file.close();self.file=None


class ChildJob:
    """Windows closes this handle on parent exit, stopping only our service process trees."""
    def __init__(self):
        class Limits(ctypes.Structure):
            _fields_=[('per_process',ctypes.c_int64),('per_job',ctypes.c_int64),('flags',wintypes.DWORD),
                ('min_working',ctypes.c_size_t),('max_working',ctypes.c_size_t),('active',wintypes.DWORD),
                ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(key,ctypes.c_uint64) for key in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Limits),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
                      ('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype=wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.kernel.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        info=Extended();info.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)):
            error=ctypes.WinError(ctypes.get_last_error());self.close();raise error
    def add(self,process):
        if not self.kernel.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(process._handle))):
            error=ctypes.WinError(ctypes.get_last_error());process.terminate();process.wait();raise error
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None


def available_ports(count):
    sockets=[]
    try:
        for _ in range(count):
            sock=socket.socket();sock.bind(('127.0.0.1',0));sockets.append(sock)
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:sock.close()


def installation_ports(layout):
    """Keep browser origins stable across Stop/Start, Update and Repair."""
    path=layout.state/'ports.json'
    if path.exists():
        record=json.loads(path.read_text(encoding='utf-8'))
        ports=[record.get('comfy'),record.get('hi3d')]
        if any(type(port) is not int or not 1024<=port<=65535 for port in ports) or len(set(ports))!=2:
            raise RuntimeError('The saved Foundry service ports are invalid. Check .pinokio/ports.json.')
        for port in ports:
            with socket.socket() as probe:
                if sys.platform=='win32':probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
                try:probe.bind(('127.0.0.1',port))
                except OSError:
                    raise RuntimeError(f'Foundry port {port} is already in use. Stop the other service and start Foundry again. The saved address has not been changed.') from None
        return ports
    ports=available_ports(2)
    atomic_json(path,{'comfy':ports[0],'hi3d':ports[1]})
    return ports


def service_commands(layout,comfy_port,hi3d_port):
    return {
        'hi3d':[str(layout.hi3d/'.venv'/'Scripts'/'python.exe'),'-u',str(layout.root/'scripts'/'pinokio'/'hi3d_entry.py'),'--port',str(hi3d_port)],
        'comfy':[str(layout.host_python),'-u',str(layout.comfy/'main.py'),'--listen','127.0.0.1','--port',str(comfy_port),
            '--user-directory',str(layout.data/'user'),'--models-directory',str(layout.data/'models'),
            '--input-directory',str(layout.data/'input'),'--output-directory',str(layout.data/'output'),
            '--temp-directory',str(layout.data/'temp'),'--disable-auto-launch']}


def read_json(url,timeout=4):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url,timeout=timeout) as response:return json.load(response)


def wait_ready(process,url,seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError(f'Service exited with code {process.returncode}. See the service log above.')
        try:return read_json(url)
        except (OSError,ValueError):time.sleep(.5)
    raise RuntimeError(f'Service did not become ready: {url}. See logs/pinokio for its startup log.')


def write_mcp_configuration(layout):
    atomic_json(layout.state/'mcp.json',{'mcpServers':{'mumblebox-foundry':{
        'command':str(layout.mcp_python),
        'args':[str(layout.root/'scripts'/'pinokio'/'connect_agent.py'),'--root',str(layout.root)]}}})


def start_service(name,command,cwd,env,job,logs):
    process=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW)
    job.add(process)
    def drain():
        with (logs/(name+'.log')).open('a',encoding='utf-8') as output:
            for line in process.stdout:
                output.write(line);output.flush();print(f'[{name}] {line.rstrip()}',flush=True)
    threading.Thread(target=drain,daemon=True).start()
    return process


def launch(root):
    layout=Layout(root)
    if (layout.state/'repair-required.json').exists():
        raise RuntimeError('A staged update failed. Run Repair software before starting; your assets and settings were preserved.')
    record_path=layout.state/'installed.json'
    if not record_path.is_file():raise RuntimeError('Run Install before starting Foundry.')
    installed=json.loads(record_path.read_text())
    with InstallationLock(layout.state/'operation.lock'):
        comfy_port,hi3d_port=installation_ports(layout)
        install_extension(layout,layout.root/installed['blender'],layout.root,hi3d_port)
        env=os.environ.copy()
        for key in ('PYTHONHOME','PYTHONPATH'):env.pop(key,None)
        env.update({'PYTHONUNBUFFERED':'1','PYTHONIOENCODING':'utf-8',
            'MUMBLEBOX_PINOKIO_ROOT':str(layout.root),
            'HF_HOME':str(layout.data/'huggingface'),'TORCH_HOME':str(layout.data/'torch')})
        commands=service_commands(layout,comfy_port,hi3d_port)
        logs=layout.root/'logs'/'pinokio';logs.mkdir(parents=True,exist_ok=True)
        job=ChildJob();processes=[];runtime_path=layout.state/'runtime.json'
        # An old record can survive a forced stop, but cannot own this OS lock.
        runtime_path.unlink(missing_ok=True)
        try:
            print('Starting Foundry software. Models load only when a workflow needs them.',flush=True)
            hi3d=start_service('hi3d',commands['hi3d'],layout.hi3d,env,job,logs);processes.append(hi3d)
            wait_ready(hi3d,f'http://127.0.0.1:{hi3d_port}/api/health')
            comfy=start_service('comfy',commands['comfy'],layout.comfy,env,job,logs);processes.append(comfy)
            url=f'http://127.0.0.1:{comfy_port}'
            wait_ready(comfy,url+'/system_stats')
            capabilities=read_json(url+'/mumblebox-foundry/v1/bootstrap')
            if not capabilities.get('wizard_available'):raise RuntimeError('Foundry wizard failed to load. Run Repair software and inspect the startup log.')
            atomic_json(runtime_path,{'schema':1,'pid':os.getpid(),'instance':str(uuid.uuid4()),
                'comfy_url':url,'hi3d_url':f'http://127.0.0.1:{hi3d_port}','version':capabilities['version']})
            write_mcp_configuration(layout)
            print(f'Foundry ready: {url}',flush=True)
            while all(process.poll() is None for process in processes):time.sleep(1)
            raise RuntimeError('A Foundry service stopped unexpectedly. Your saved files are preserved; inspect logs/pinokio and restart.')
        finally:
            job.close()
            for process in processes:
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            runtime_path.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    try:launch(parser.parse_args().root)
    except KeyboardInterrupt:pass
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as error:
        print(f'Foundry could not start: {error}',file=sys.stderr,flush=True);sys.exit(1)
