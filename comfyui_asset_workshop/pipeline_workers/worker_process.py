"""Own an isolated worker tree, including across an unexpected Windows host exit."""
import os
import subprocess

class OwnedWorker:
    def __init__(self,command,log,*,env=None):
        self.job=None;self.kernel=None
        flags=(subprocess.CREATE_NO_WINDOW|0x00000004) if os.name=='nt' else 0
        self.process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=flags,env=env)
        try:
            if os.name=='nt':self._attach_windows_job()
        except BaseException:
            try:self.process.kill();self.process.wait(timeout=10)
            finally:self.close()
            raise

    def _attach_windows_job(self):
        import ctypes as c
        from ctypes import wintypes as w
        import psutil
        class Basic(c.Structure):
            _fields_=[('process_time',c.c_longlong),('job_time',c.c_longlong),('flags',w.DWORD),('min_working_set',c.c_size_t),('max_working_set',c.c_size_t),('process_limit',w.DWORD),('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class Counters(c.Structure):
            _fields_=[(name,c.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Limits(c.Structure):
            _fields_=[('basic',Basic),('io',Counters),('process_memory',c.c_size_t),('job_memory',c.c_size_t),('peak_process_memory',c.c_size_t),('peak_job_memory',c.c_size_t)]
        k=c.WinDLL('kernel32',use_last_error=True);self.kernel=k
        k.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];k.CreateJobObjectW.restype=w.HANDLE
        k.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];k.SetInformationJobObject.restype=w.BOOL
        k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];k.AssignProcessToJobObject.restype=w.BOOL
        k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
        k.OpenThread.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenThread.restype=w.HANDLE
        k.ResumeThread.argtypes=[w.HANDLE];k.ResumeThread.restype=w.DWORD
        k.TerminateJobObject.argtypes=[w.HANDLE,w.UINT];k.TerminateJobObject.restype=w.BOOL
        k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
        self.job=k.CreateJobObjectW(None,None)
        if not self.job:raise c.WinError(c.get_last_error())
        limits=Limits();limits.basic.flags=0x00002000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.job,9,c.byref(limits),c.sizeof(limits)):raise c.WinError(c.get_last_error())
        process_handle=k.OpenProcess(0x0101,False,self.process.pid) # SET_QUOTA | TERMINATE
        if not process_handle:raise c.WinError(c.get_last_error())
        try:
            if not k.AssignProcessToJobObject(self.job,process_handle):raise c.WinError(c.get_last_error())
        finally:k.CloseHandle(process_handle)
        # The root starts suspended, so none of its children can escape assignment.
        resumed=False
        for thread in psutil.Process(self.process.pid).threads():
            handle=k.OpenThread(0x0002,False,thread.id)
            if not handle:raise c.WinError(c.get_last_error())
            try:
                count=k.ResumeThread(handle)
                if count==0xffffffff:raise c.WinError(c.get_last_error())
                resumed=resumed or count>0
            finally:k.CloseHandle(handle)
        if not resumed:raise RuntimeError('The owned worker could not be resumed')

    def stop(self):
        if self.job:
            if not self.kernel.TerminateJobObject(self.job,1):
                import ctypes
                raise ctypes.WinError(ctypes.get_last_error())
            self.process.wait(timeout=10)
        else:
            import psutil
            try:children=psutil.Process(self.process.pid).children(recursive=True)
            except psutil.NoSuchProcess:children=[]
            for child in children:
                try:child.terminate()
                except psutil.NoSuchProcess:pass
            self.process.terminate()
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            _,alive=psutil.wait_procs(children,timeout=5)
            for child in alive:
                try:child.kill()
                except psutil.NoSuchProcess:pass
            psutil.wait_procs(alive,timeout=5)

    def close(self):
        if self.job:self.kernel.CloseHandle(self.job);self.job=None
