"""Durable HairDeck jobs. The GUI and agents share one queue and checkpoint owner."""
import asyncio
import copy
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from PIL import Image
from ...artifacts import owned_path, digest
from .definition import validate, GENERATION_KEYS
from . import graph, integration

ACTIVE = None
def busy(): return ACTIVE is not None and bool(ACTIVE.tasks)
def signature(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


class HairRuns:
    def __init__(self,state,input_root,output_root,native,lifecycle,other_busy,library,prepare=integration.ensure):
        self.state=Path(state);self.state.mkdir(parents=True,exist_ok=True)
        self.input_root=Path(input_root).resolve();self.output_root=Path(output_root).resolve()
        self.native=native;self.lifecycle=lifecycle;self.other_busy=other_busy;self.library=library;self.prepare=prepare
        self.records={};self.tasks={}

    def path(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Invalid hair creation identity.')
        return self.state/(ident+'.json')

    def save(self,record):
        record['updated']=time.time();path=self.path(record['id']);temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)

    def get(self,ident):
        if ident in self.records:return self.records[ident]
        record=json.loads(self.path(ident).read_text(encoding='utf-8'))
        # An older saved generation used a single measured color. Do not
        # relabel it as ColorDiT output or invalidate its saved hair on resume.
        record['config']=validate({'colors':False,**record['config']});self.records[ident]=record
        if record['status'] in ('running','cleaning'):
            pending=record.get('pending')
            if pending and (pending['id'] in self.native.active_ids() or self.native.history(pending['id'])):
                self.tasks[ident]=asyncio.create_task(self.recover(record))
            else:
                record.update(status='interrupted',error='The hair job was interrupted. Completed variations remain available.')
                record.pop('pending',None);self.save(record)
        return record

    def source(self,config):
        path=owned_path(self.input_root,self.input_root/config['image'])
        if not path.is_file() or path.stat().st_size>20*1024**2:raise ValueError('Upload a reference smaller than 20 MB.')
        with Image.open(path) as image:
            if image.width*image.height>40_000_000:raise ValueError('Reference exceeds 40 megapixels.')
            image.verify()
        return digest(path)

    def create(self,data):
        config=validate(data);sha=self.source(config)
        record=dict(id=uuid.uuid4().hex,config=config,source_sha256=sha,status='idle',stage='Starting image',
                    variants=[],selected=0,events=[],error='',created=time.time(),progress=0)
        self.records[record['id']]=record;self.save(record);return self.public(record)

    def update(self,ident,data):
        record=self.get(ident)
        if ident in self.tasks:raise ValueError('Wait for this hair job before changing options.')
        config=validate(data);sha=self.source(config)
        if any(config[k]!=record['config'][k] for k in GENERATION_KEYS) or sha!=record['source_sha256']:
            record.update(variants=[],selected=0)
            record.pop('preview',None);record.pop('motion_preview',None);record.pop('avatar_preview',None)
        elif any(config[k]!=record['config'][k] for k in ('color','show_head','head_profile','scale','offset','uv_mode','texture_size','material')):
            for key in ('preview','avatar_preview','motion_preview'):record.pop(key,None)
            for variant in record['variants']:variant.pop('reviews',None)
        elif config['motion_chains']!=record['config']['motion_chains']:
            record.pop('motion_preview',None)
            for variant in record['variants']:variant.get('reviews',{}).pop('motion_preview',None)
        record.update(config=config,source_sha256=sha,status='idle',error='',progress=0)
        record.pop('package',None);record.pop('export',None);record.pop('request_id',None)
        self.save(record);return self.public(record)

    def public(self,record):
        result=copy.deepcopy({k:v for k,v in record.items() if k not in ('pending','cancel')})
        result['active']=record['id'] in self.tasks
        if record.get('pending'):result['pending']={k:record['pending'][k] for k in ('id','graph')}
        return result

    def start(self,ident,data):
        record=self.get(ident);request=data.get('request_id');operation=data.get('operation','generate')
        if not isinstance(request,str) or not 1<=len(request)<=100:raise ValueError('Supply a retry-safe request identity.')
        if operation not in ('generate','rig','preview','avatar_preview','motion_preview','export'):raise ValueError('Choose hair generation, spring chains, material preview, avatar preview, motion preview or export.')
        if record.get('request_id')==request:
            if record.get('operation')!=operation:raise ValueError('Request identity belongs to another operation.')
            return self.public(record)
        if self.tasks or self.native.active_ids() or self.other_busy():raise ValueError('Another workflow is active. Wait before starting hair creation.')
        selected=data.get('selected',record['selected'])
        if type(selected) is not int or selected<0 or (operation!='generate' and selected>=len(record['variants'])):raise ValueError('Select a generated variation.')
        if self.source(record['config'])!=record['source_sha256']:raise ValueError('The reference changed. Upload it again before generating.')
        record.update(status='running',cancel=False,error='',request_id=request,operation=operation,selected=selected,
                      client_id=str(data.get('client_id',''))[:100],progress=0)
        if operation in ('rig','avatar_preview','motion_preview'):record['config']['bones']=True
        self.save(record);self.tasks[ident]=asyncio.create_task(self.execute(record));return self.public(record)

    def cancel(self,ident):
        record=self.get(ident)
        if ident in self.tasks:
            record['cancel']=True
            if record.get('pending'):self.native.cancel(record['pending']['id'])
            self.save(record)
        return self.public(record)

    def check(self,record):
        if record.get('cancel'):raise InterruptedError('Cancelled. Completed hair variations and exports are preserved.')

    def event(self,record,text,progress=None):
        record['stage']=text
        if progress is not None:record['progress']=progress
        record['events']=(record['events']+[{'time':time.time(),'text':text}])[-30:];self.save(record)

    async def prepare_resources(self,record):
        self.event(record,'Preparing selected HairDeck resources',2)
        loop=asyncio.get_running_loop()
        def progress(value):loop.call_soon_threadsafe(lambda:record.update(dependency=value))
        preparation=copy.deepcopy(record['config'])
        if record['operation'] in ('avatar_preview','motion_preview'):preparation['vrm']=True
        record['models']=await asyncio.to_thread(self.prepare,preparation,lambda:record.get('cancel',False),progress)
        record.pop('dependency',None);self.check(record)

    async def execute(self,record):
        try:
            await self.lifecycle().barrier();await self.lifecycle().release('before Foundry hair creation')
            await self.prepare_resources(record)
            if record['operation']=='generate':
                for index in range(len(record['variants']),record['config']['variations']):
                    self.check(record)
                    self.event(record,f'HairDeck: generating hair variation {index+1} of {record["config"]["variations"]}',
                               10+int(index/record['config']['variations']*80))
                    await self.enqueue(record,graph.generate(record,index),'70003','generate',index)
                if record['config']['bones']:
                    for index,item in enumerate(record['variants']):
                        if not item.get('bone_model'):
                            self.check(record);self.event(record,f'Adding matching spring chains to variation {index+1}',85)
                            await self.enqueue(record,graph.rig(record,index),'70005','rig',index)
                self.event(record,'Hair variations saved for review',95)
            elif record['operation']=='rig':
                self.event(record,'HairDeck: adding matching spring chains to the saved hair',10)
                await self.enqueue(record,graph.rig(record,record['selected']),'70005','rig',record['selected'])
            else:
                if record['config']['bones'] and not record['variants'][record['selected']].get('bone_model'):
                    self.event(record,'Adding matching spring chains to the selected saved variation',8)
                    await self.enqueue(record,graph.rig(record,record['selected']),'70005','rig',record['selected'])
                self.event(record,'Preparing materials, selected rig and exports',10)
                checkpoint=record['variants'][record['selected']]['checkpoint']
                request=copy.deepcopy(record)
                if record['operation']=='preview':request['config'].update(glb=True,vrm=False,motion=False)
                if record['operation']=='avatar_preview':request['config'].update(glb=True,vrm=True,motion=False)
                if record['operation']=='motion_preview':request['config'].update(glb=True,vrm=True,motion=True)
                await self.enqueue(record,graph.export(request,checkpoint),'70004',record['operation'],record['selected'])
                if record['operation']=='export':
                    self.check(record);self.event(record,'Building the selected hair package and History entry',85)
                    from .package import build
                    record['package']=await asyncio.to_thread(build,self,record)
            record['status']='cleaning'
        except asyncio.CancelledError:record.update(status='cancelled',error='Cancelled. Completed hair generations are preserved.')
        except InterruptedError as error:record.update(status='cancelled',error=str(error))
        except Exception as error:record.update(status='failed',error=str(error))
        finally:await self.finish(record)

    async def enqueue(self,record,prompt,output,phase,index):
        ident=str(uuid.uuid4())
        record['pending']=dict(id=ident,graph=prompt,output=output,phase=phase,index=index)
        self.save(record);await self.native.submit(prompt,ident,record.get('client_id',''))
        await self.accept(record)

    async def accept(self,record):
        pending=record['pending'];result=await self.native.wait(pending['id'],7200,lambda:record.get('cancel',False))
        if result.get('status',{}).get('status_str')!='success':
            self.check(record)
            errors=[m[1].get('exception_message','') for m in result.get('status',{}).get('messages',[]) if m[0]=='execution_error']
            raise ValueError('Hair stage failed: '+'; '.join(errors)[:2000])
        data=result.get('outputs',{}).get(pending['output'],{}).get('foundry_hair',[])
        if len(data)!=1:raise ValueError('HairDeck did not return a saved result.')
        item=data[0]
        for key in ('model','checkpoint'):
            if not owned_path(self.output_root,self.output_root/item[key]).is_file():raise ValueError('A saved hair artifact is missing.')
        if pending['phase']=='generate':
            if len(record['variants'])==pending['index']:record['variants'].append(item)
        elif pending['phase']=='rig':record['variants'][pending['index']]=item
        else:
            record[pending['phase']]=item
            if pending['phase'] in ('preview','avatar_preview','motion_preview'):
                record['variants'][pending['index']].setdefault('reviews',{})[pending['phase']]=item
        record.pop('pending',None);self.save(record)

    async def recover(self,record):
        try:
            await self.accept(record);record.update(status='interrupted',error='Recovered saved output. Continue to finish the remaining stages.')
        except Exception as error:record.update(status='failed',error=str(error))
        finally:await self.finish(record)

    async def finish(self,record):
        record.pop('pending',None);record.pop('dependency',None)
        try:
            if not self.native.active_ids():record['cleanup']=await self.lifecycle().release('Foundry hair stage finished')
        except Exception as error:record['cleanup']={'status':'failed','error':str(error)}
        if record['status']=='cleaning':record.update(status='complete',progress=100)
        self.tasks.pop(record['id'],None);self.save(record)

    def file(self,ident,name):
        record=self.get(ident);allowed=set()
        reviews=[v for item in record['variants'] for v in item.get('reviews',{}).values()]
        for item in [*record['variants'],*reviews,record.get('export',{}),record.get('preview',{}),record.get('avatar_preview',{}),record.get('motion_preview',{})]:
            for key in ('model','bone_model'):
                if item.get(key):allowed.add(item[key])
            allowed.update(item.get('views',{}).values())
            for file in item.get('files',[]):allowed.add(file['subfolder']+'/'+file['filename'])
        if record.get('package'):allowed.add(record['package']['path'])
        if name not in allowed:raise ValueError('This file does not belong to the saved hair result.')
        return owned_path(self.output_root,self.output_root/name)
