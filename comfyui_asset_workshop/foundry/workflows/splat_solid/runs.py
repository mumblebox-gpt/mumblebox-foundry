"""Durable independent stage ownership, shared by the GUI and agent routes."""
import asyncio,copy,hashlib,json,re,time,uuid
from pathlib import Path
from PIL import Image
from ...artifacts import owned_path,digest
from .definition import validate,GROUPS,needs_mesh
from .graph import compile_stage,ROLES

ACTIVE=None
def busy():return ACTIVE is not None and bool(ACTIVE.tasks)
def signature(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

class SplatRuns:
    def __init__(self,state,input_root,output_root,native,lifecycle,other_busy,library):
        self.state=Path(state);self.state.mkdir(parents=True,exist_ok=True)
        self.input_root=Path(input_root).resolve();self.output_root=Path(output_root).resolve()
        self.native=native;self.lifecycle=lifecycle;self.other_busy=other_busy;self.library=library
        self.records={};self.tasks={}
    def path(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Invalid splat asset identity.')
        return self.state/(ident+'.json')
    def save(self,r):
        r['updated']=time.time();p=self.path(r['id']);tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps(r,indent=2),encoding='utf-8');tmp.replace(p)
    def get(self,ident):
        if ident in self.records:return self.records[ident]
        r=json.loads(self.path(ident).read_text(encoding='utf-8'));self.records[ident]=r
        if r['status']=='running':
            if r.get('pending') and (r['pending']['id'] in self.native.active_ids() or self.native.history(r['pending']['id'])):
                self.tasks[ident]=asyncio.create_task(self.recover(r))
            else:r.update(status='interrupted',error='Processing was interrupted. Saved stages are preserved.');r.pop('pending',None);self.save(r)
        return r
    def public(self,r):
        result=copy.deepcopy({k:v for k,v in r.items() if k not in ('pending','cancel','client_id')})
        if 'orbit' in result['artifacts'] and not self.artifact_path(r,'orbit').is_file():
            result['artifacts'].pop('orbit')
        result['active']=r['id'] in self.tasks
        if r.get('pending'):result['pending']={k:r['pending'][k] for k in ('id','stage')}
        return result
    def source(self,c):
        p=owned_path(self.input_root,self.input_root/c['image'])
        if not p.is_file() or p.stat().st_size>20*1024**2:raise ValueError('Upload an image smaller than 20 MB.')
        with Image.open(p) as im:
            if im.width*im.height>40000000:raise ValueError('The reference exceeds 40 megapixels.')
            im.verify()
        return digest(p)
    def create(self,data):
        c=validate(data);r=dict(id=uuid.uuid4().hex,config=c,source_sha256=self.source(c),status='idle',stage='Starting image',artifacts={},completed={},outputs={},events=[],progress=0,error='',created=time.time())
        self.records[r['id']]=r;self.save(r);return self.public(r)
    def update(self,ident,data):
        r=self.get(ident)
        if ident in self.tasks:raise ValueError('Wait for this asset before changing settings.')
        c=validate(data);sha=self.source(c)
        if sha!=r['source_sha256']:r['completed']={};r['artifacts']={};r['outputs']={}
        r.update(config=c,source_sha256=sha,status='idle',error='');r.pop('package',None);r.pop('request_id',None)
        self.save(r);return self.public(r)
    def fingerprint(self,r,stage,*,orbit=None):
        keys=GROUPS['generation'] if stage=='generation' else GROUPS['refinement'] if stage=='refinement' else GROUPS['cleanup']
        previous=None if stage=='generation' else r['completed'].get('generation' if stage=='refinement' or not r['config']['refine'] else 'refinement')
        settings={k:r['config'][k] for k in keys}
        if stage=='generation' and r['config'].get('generation_mode')=='turbo':
            settings.update(generation_mode='turbo',steps=5,cfg=1.0)
        if stage=='generation':
            previous=r['config']['outputs']['orbit'] if orbit is None else orbit
        return signature([r['source_sha256'],settings,previous])
    def fresh(self,r,stage,*,require_orbit=False):
        saved=r['completed'].get(stage)
        if not saved or (require_orbit and 'orbit' not in saved['roles']):return False
        signatures={self.fingerprint(r,stage)}
        if stage=='generation' and not r['config']['outputs']['orbit']:
            signatures.add(self.fingerprint(r,stage,orbit=True))
        # The video is an optional export. Mesh and splat stages can reuse
        # their saved files after the standalone video has been deleted.
        roles=[role for role in saved['roles'] if role!='orbit' or require_orbit]
        return saved['signature'] in signatures and all(
            role in r['artifacts'] and self.artifact_path(r,role).is_file() for role in roles)
    def artifact_path(self,r,role):return owned_path(self.output_root,self.output_root/r['artifacts'][role]['relative'])
    def file(self,ident,name):
        r=self.get(ident);allowed={x['relative'] for x in r['artifacts'].values()}
        if r.get('package'):allowed.add(r['package']['path'])
        if name not in allowed:raise ValueError('This file is not part of the saved splat asset.')
        return owned_path(self.output_root,self.output_root/name)
    def check(self,r):
        if r.get('cancel'):raise InterruptedError('Cancelled. Completed splat and mesh stages remain saved.')
    def event(self,r,text,progress=None):
        r['stage']=text
        if progress is not None:r['progress']=progress
        r['events']=(r['events']+[{'time':time.time(),'text':text}])[-40:];self.save(r)
    def start(self,ident,data):
        r=self.get(ident);op=data.get('operation','rocket');key=data.get('request_id')
        if op not in ('generation','cleanup','export','rocket') or not isinstance(key,str) or not 1<=len(key)<=100:raise ValueError('Choose a stage and supply a retry-safe request identity.')
        if key==r.get('request_id'):
            if op!=r.get('operation'):raise ValueError('Request identity belongs to another operation.')
            return self.public(r)
        if self.tasks or self.native.active_ids() or self.other_busy():raise ValueError('Another workflow is running. Finish it before starting this asset.')
        if self.source(r['config'])!=r['source_sha256']:raise ValueError('The reference image changed. Save the updated reference first.')
        r.update(status='running',cancel=False,error='',operation=op,request_id=key,client_id=str(data.get('client_id',''))[:100],progress=0,started_at=time.time())
        self.save(r);self.tasks[ident]=asyncio.create_task(self.execute(r));return self.public(r)
    def cancel(self,ident):
        r=self.get(ident);r['cancel']=True
        from ..image_to_3d.readiness import cancel_download
        cancel_download(r['id'])
        if r.get('pending'):self.native.cancel(r['pending']['id'])
        self.save(r);return self.public(r)
    async def prepare(self,r):
        from ..image_to_3d.readiness import ensure
        self.event(r,'Preparing all selected models before processing',2)
        loop=asyncio.get_running_loop()
        progress=lambda d:loop.call_soon_threadsafe(lambda:r.update(dependency=d))
        mode='splat_turbo' if r['config'].get('generation_mode')=='turbo' else 'splat'
        await asyncio.to_thread(ensure,mode,self.state,lambda:r.get('cancel',False),r['id'],progress)
        if r['config']['refine'] and needs_mesh(r['config']):await asyncio.to_thread(ensure,'refinement',self.state,lambda:r.get('cancel',False),r['id'],progress)
        r.pop('dependency',None);self.check(r)
    async def execute(self,r):
        try:
            await self.lifecycle().barrier();await self.lifecycle().release('before Splat & Solid')
            await self.prepare(r)
            op=r['operation']
            if op in ('generation','rocket'):await self.stage(r,'generation',8)
            if op in ('cleanup','rocket') and needs_mesh(r['config']):
                if not self.fresh(r,'generation'):raise ValueError('Generate or restore the splat and original mesh first.')
                if r['config']['refine']:await self.stage(r,'refinement',35)
                await self.stage(r,'cleanup',70)
                self.event(r,'Checking the saved master and companion geometry',88)
                from .quality import audit
                await asyncio.to_thread(audit,self,r)
            if op in ('export','rocket'):
                if not self.fresh(r,'generation') or (needs_mesh(r['config']) and not self.fresh(r,'cleanup')):raise ValueError('Complete the selected generation and cleanup stages before exporting.')
                if needs_mesh(r['config']) and (not r.get('quality') or not all(x['passed'] for x in r['quality'].values())):raise ValueError('The saved geometry audit must pass before export.')
                if r['config']['outputs']['orbit'] and (
                    'orbit' not in r['artifacts'] or not self.artifact_path(r,'orbit').is_file()):
                    raise ValueError('The saved orbit is missing. Generate it again or turn off the orbit video in the export options.')
                self.event(r,'Writing selected files, credits, README and History',95)
                from .package import build
                r['package']=await asyncio.to_thread(build,self,r)
            r.update(status='complete',progress=100,error='')
        except (asyncio.CancelledError,InterruptedError) as e:r.update(status='cancelled',error=str(e) or 'Cancelled; saved stages remain available.')
        except Exception as e:r.update(status='failed',error=str(e))
        finally:await self.finish(r)
    async def stage(self,r,stage,progress):
        self.check(r)
        if self.fresh(r,stage,require_orbit=stage=='generation' and r['config']['outputs']['orbit']):self.event(r,'Reused saved '+stage+' stage',progress);return
        await self.lifecycle().barrier();await self.lifecycle().release('before splat '+stage)
        generator='Idol Turbo' if r['config'].get('generation_mode')=='turbo' else 'Idol'
        self.event(r,{'generation':generator+' · generating the splat and original mesh','refinement':'Hi3D · refining the original geometry','cleanup':'ComfyUI · closing and simplifying the geometry'}[stage],progress)
        prompt=compile_stage(r,stage);ident=str(uuid.uuid4())
        r['pending']=dict(id=ident,stage=stage,graph=prompt,signature=self.fingerprint(r,stage));self.save(r)
        await self.native.submit(prompt,ident,r.get('client_id',''));await self.accept(r)
    async def accept(self,r):
        p=r['pending'];result=await self.native.wait(p['id'],7200,lambda:r.get('cancel',False))
        if result.get('status',{}).get('status_str')!='success':
            self.check(r);errors=[x[1].get('exception_message','') for x in result.get('status',{}).get('messages',[]) if x[0]=='execution_error']
            raise ValueError('Splat stage failed: '+'; '.join(errors)[:2000])
        roles=[]
        for role,node_id in ROLES.items():
            value=result.get('outputs',{}).get(node_id,{})
            entries=[item for values in value.values() if isinstance(values,list) for item in values if isinstance(item,dict) and item.get('filename') and item.get('type')=='output']
            if not entries:continue
            item=entries[0];relative=(Path(item.get('subfolder',''))/item['filename']).as_posix();path=owned_path(self.output_root,self.output_root/relative)
            if not path.is_file():raise ValueError('A native splat output is missing.')
            r['artifacts'][role]={'relative':relative,'bytes':path.stat().st_size,'sha256':digest(path)};roles.append(role)
        if not roles:raise ValueError('The native stage returned no durable output.')
        r['outputs'].update(result.get('outputs',{}));r['completed'][p['stage']]={'signature':p['signature'],'roles':roles,'prompt_id':p['id']}
        r.pop('pending',None);self.save(r)
    async def recover(self,r):
        try:await self.accept(r);r.update(status='interrupted',error='Recovered the saved stage. Continue manually or use Rocket Mode.')
        except Exception as e:r.update(status='failed',error=str(e))
        finally:await self.finish(r)
    async def finish(self,r):
        r.pop('pending',None);r.pop('dependency',None)
        try:
            if not self.native.active_ids():r['cleanup_memory']=await self.lifecycle().release('Splat & Solid finished')
        except Exception as e:r['cleanup_memory']={'error':str(e)}
        self.tasks.pop(r['id'],None);self.save(r)
