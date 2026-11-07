"""Registered model locations and confirmed exact-file deletion."""
import hashlib,os,secrets,threading,time
from pathlib import Path

class ResourceInventory:
    EXTENSIONS={'.safetensors','.gguf','.ckpt','.pt','.pth','.bin','.onnx','.npz','.pkl','.sft'}
    def __init__(self,root,busy,locations=None,models=None,invalidate=lambda:None):
        self.root=Path(root).resolve();self.busy=busy;self.locations=locations or (lambda:[])
        self.models=models or {};self.invalidate=invalidate;self.tokens={};self.lock=threading.RLock()
    def roots(self):
        roots=[dict(path=str(self.root),label='ComfyUI models',workflows=[]),*self.locations()]
        result={}
        for e in roots:
            p=Path(e['path']).resolve()
            if p.is_dir():result.setdefault(str(p).casefold(),{**e,'path':p})
        return sorted(result.values(),key=lambda e:(-len(e['path'].parts),str(e['path']).casefold()))
    @staticmethod
    def _fingerprint(p):
        s=p.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    def _scan(self):
        roots=self.roots();items=[];seen=set();truncated=False;in_use=self.busy()
        from .workflows.image_to_3d.readiness import MODELS
        labels={'splat':['Splat & Solid'],'guided':['3D-Guided'],'turnaround':['Turnaround'],'geometry':['Turnaround','3D-Guided'],'refinement':['Turnaround','3D-Guided','Splat & Solid'],'texture':['Turnaround','3D-Guided']}
        for location in roots:
            root=location['path']
            for directory,dirs,files in os.walk(root,followlinks=False):
                dirs[:]=sorted(d for d in dirs if not (Path(directory)/d).is_symlink() and not getattr(Path(directory)/d,'is_junction',lambda:False)())
                for name in sorted(files):
                    p=Path(directory)/name
                    if p.suffix.lower() not in self.EXTENSIONS:continue
                    try:
                        real=p.resolve();key=str(p.absolute()).casefold()
                        if key in seen:continue
                        seen.add(key)
                        reason='' if any(real.is_relative_to(x['path']) for x in roots) else 'Target is outside registered model locations.'
                        if in_use:reason='Unload models and finish active jobs or downloads before deleting.'
                        stat=p.stat();relative=p.relative_to(root).as_posix();matched_key=next((k for k,m in self.models.items() if m.get('name')==name),None);matched=self.models.get(matched_key,{})
                        workflows=list(location.get('workflows',[]))
                        for stage,keys in MODELS.items():
                            if matched_key in keys:workflows.extend(labels.get(stage,[]))
                        if 'idol' in name.lower():workflows.append('Splat & Solid')
                        if 'hairdeck' in str(real).lower():workflows.append('HairDeck')
                        if name.startswith('birefnet'):workflows.extend(['Turnaround','3D-Guided','HairDeck','Splat & Solid'])
                        items.append(dict(id=hashlib.sha256(key.encode()).hexdigest()[:24],name=name,relative_path=relative,location=location['label'],
                            kind='lora' if 'lora' in str(p.parent).lower() else 'image_model' if any(x in str(p.parent).lower() for x in ('diffusion_models','checkpoints')) else 'component',workflows=sorted(set(workflows)),bytes=stat.st_size,
                            deletable=not reason,reason=reason,shared_links=stat.st_nlink,symlink=p.is_symlink(),download_known=bool(matched),path=str(p.absolute())))
                    except OSError:continue
                    if len(items)>=100000:truncated=True;break
                if truncated:break
            if truncated:break
        return {'items':items,'truncated':truncated}
    def list(self,cursor=0,limit=100):
        cursor=int(cursor);limit=int(limit)
        if cursor<0 or cursor>100000 or not 1<=limit<=200:raise ValueError('Invalid model list page.')
        with self.lock:
            data=self._scan();rows=data['items']
            return {'items':[{k:v for k,v in i.items() if k!='path'} for i in rows[cursor:cursor+limit]],
                'next_cursor':cursor+limit if cursor+limit<len(rows) else None,'total':len(rows),'truncated':data['truncated']}
    def _target(self,ident):
        item=next((i for i in self._scan()['items'] if i['id']==ident),None)
        if item is None:raise ValueError('This model is no longer installed. Refresh the list.')
        if not item['deletable']:raise ValueError(item['reason'])
        return Path(item['path']),item
    def preview(self,ident):
        with self.lock:
            p,item=self._target(ident);now=time.monotonic();self.tokens={k:v for k,v in self.tokens.items() if v['expires']>now}
            if len(self.tokens)>=32:raise ValueError('Close older deletion requests and retry.')
            token=secrets.token_urlsafe(24);self.tokens[token]={'id':ident,'fingerprint':self._fingerprint(p),'expires':now+300}
            return {**{k:item[k] for k in ('name','relative_path','bytes','location','workflows','shared_links','symlink','download_known')},'token':token,'exact_path':str(p)}
    def remove(self,token):
        with self.lock:
            receipt=self.tokens.pop(token,None)
            if not receipt or receipt['expires']<time.monotonic():raise ValueError('Deletion confirmation expired. Refresh and select the model again.')
            p,item=self._target(receipt['id'])
            if self._fingerprint(p)!=receipt['fingerprint']:raise ValueError('The file changed after confirmation. Nothing was deleted.')
            p.unlink();self.invalidate()
            return {'removed':True,'id':item['id'],'bytes':item['bytes'],'shared_links_remaining':max(0,item['shared_links']-1)}
