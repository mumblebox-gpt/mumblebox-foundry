"""Preview-confirm-purge for explicitly registered disposable cache roots only."""
import os,secrets,threading,time
from pathlib import Path

ACTIVE=None
def busy():return bool(ACTIVE and ACTIVE.running)

class CacheManager:
    def __init__(self,roots,busy,clock=time.time):
        self.roots=[(label,Path(root).resolve(),partials) for label,root,partials in roots]
        self.busy,self.clock=busy,clock
        self.lock=threading.Lock();self.receipt=None;self.running=False
    def available(self):
        if self.running or self.busy():raise ValueError('Wait for generation, exports and downloads to finish before clearing cache.')
    def safe(self,path,root):
        if path.is_symlink() or not path.resolve().is_relative_to(root) or path.resolve()==root:return False
        for part in (path,*path.parents):
            if part==root:break
            try:
                if getattr(part.lstat(),'st_file_attributes',0)&0x400:return False
            except OSError:return False
        return True
    def preview(self):
        with self.lock:
            self.available();records=[];groups=[];truncated=False;visited=0
            for label,root,partials in self.roots:
                count=total=0
                if not root.is_dir():continue
                for folder,dirs,files in os.walk(root,followlinks=False):
                    dirs[:]=sorted(d for d in dirs if self.safe(Path(folder)/d,root))
                    for name in sorted(files):
                        visited+=1
                        if visited>10000:truncated=True;break
                        path=Path(folder)/name
                        if not partials and path.suffix.lower() in ('.safetensors','.ckpt','.pt','.pth','.onnx'):continue
                        if partials and path.suffix not in ('.part','.incomplete','.tmp'):continue
                        if not self.safe(path,root):continue
                        try:stat=path.stat()
                        except OSError:continue
                        if not path.is_file():continue
                        records.append((path,root,stat.st_size,stat.st_mtime_ns,label));count+=1;total+=stat.st_size
                    if truncated:break
                groups.append({'name':label,'count':count,'bytes':total,'root':str(root)})
                if truncated:break
            token=secrets.token_hex(20)
            self.receipt={'token':token,'expires':self.clock()+300,'files':records}
            return {'token':token,'count':len(records),'bytes':sum(x[2] for x in records),'groups':groups,'truncated':truncated,
                'files':[{'path':str(p),'bytes':size,'group':label} for p,root,size,mtime,label in records]}
    def purge(self,token,groups=None):
        with self.lock:
            self.available();receipt=self.receipt
            if not receipt or not secrets.compare_digest(str(token),receipt['token']) or self.clock()>receipt['expires']:
                raise ValueError('This cache preview expired. Preview it again before clearing.')
            known={row[4] for row in receipt['files']}
            if groups is not None:
                if not isinstance(groups,list) or not groups or len(groups)>len(self.roots) or any(not isinstance(x,str) or x not in known for x in groups):
                    raise ValueError('Choose at least one cache category from this preview.')
                records=[row for row in receipt['files'] if row[4] in set(groups)]
            else:records=receipt['files']
            self.receipt=None;self.running=True;removed=freed=skipped=0;failures=[]
            try:
                for path,root,size,mtime,label in records:
                    if self.busy():raise ValueError('A job started. Remaining cache files were kept; preview again when it finishes.')
                    try:
                        stat=path.stat()
                        if not self.safe(path,root) or (stat.st_size,stat.st_mtime_ns)!=(size,mtime):skipped+=1;continue
                        path.unlink();removed+=1;freed+=size
                    except FileNotFoundError:skipped+=1
                    except OSError:failures.append(str(path))
                return {'removed':removed,'bytes':freed,'skipped':skipped,'failures':failures}
            finally:self.running=False
