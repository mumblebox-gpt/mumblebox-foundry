"""Durable sequential image jobs. GUI and MCP share this owner."""
import asyncio
import copy
import hashlib
import importlib
import json
import secrets
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from PIL import Image
from ...artifacts import digest,owned_path
from .definition import validate,text,number
from .graph import compile_stage,ensure_models,cancel_download

ACTIVE=None

def busy():return ACTIVE is not None and bool(ACTIVE.tasks)

def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class ImageRuns:
    def __init__(self,library,input_root,native,lifecycle,other_busy,prepare=ensure_models,compiler=compile_stage):
        self.library=library;self.input_root=Path(input_root).resolve();self.native=native
        self.lifecycle=lifecycle;self.other_busy=other_busy;self.prepare=prepare;self.compiler=compiler
        self.tasks={};self.records={}
        library.busy=lambda:bool(self.tasks)

    def get(self,ident):
        # The Gallery is authoritative about removal, including other clients.
        saved=self.library.get(ident)
        if ident in self.records:return self.records[ident]
        record=saved;self.records[ident]=record
        if record['status'] in ('running','cleaning'):
            pending=record.get('pending')
            if pending and (pending['prompt_id'] in self.native.active_ids() or self.native.history(pending['prompt_id'])):
                self.tasks[ident]=asyncio.create_task(self.recover(record))
            else:
                record.update(status='interrupted',error='The image job was interrupted. Continue to reuse completed images.')
                record.pop('pending',None);self.library.save(record)
        return record

    def create(self,data):
        config=validate(data);self.check_references(config)
        scope=data.get('graph_scope','')
        if scope not in ('','ccore-reference'):raise ValueError('Choose a supported image workspace.')
        record=self.library.create(config)
        if scope:
            record['graph_scope']=scope
            self.library.save(record)
        self.records[record['id']]=record
        return self.public(record)

    def check_references(self,config):
        for reference in config['references']:
            path=owned_path(self.input_root,self.input_root/reference['filename'])
            if not path.is_file() or path.stat().st_size>20*1024**2:raise ValueError('Upload an image smaller than 20 MB.')
            with Image.open(path) as image:
                if image.width*image.height>40_000_000:raise ValueError('Reference exceeds 40 megapixels.')
                image.verify()
            reference['sha256']=digest(path)

    def update(self,ident,data):
        record=self.get(ident)
        if ident in self.tasks:raise ValueError('Wait for the current image job before changing its inputs.')
        config=validate(data);self.check_references(config)
        previous={k:v for k,v in record['config'].items() if k!='name'}
        if previous!={k:v for k,v in config.items() if k!='name'}:
            record.update(stages={},accepted={},outputs={},status='idle',error='',saved=False)
            for key in ('generation_seed','request_id','edit','candidate'):record.pop(key,None)
        record['config']=config;self.library.save(record)
        return self.public(record)

    def public(self,record):
        result=copy.deepcopy({k:v for k,v in record.items() if k not in ('cancel','pending')})
        result['active']=record['id'] in self.tasks
        for revision in result['revisions']:
            revision['url']='/mumblebox-foundry/v1/images/'+record['id']+'/files/'+revision['id']
        if record.get('pending'):
            pending=record['pending'];result['pending']={k:pending[k] for k in ('prompt_id','side','graph','bindings') if k in pending}
        return result

    def start(self,ident,data):
        record=self.get(ident);request=text(data.get('request_id',''),'Request identity',100,True)
        if record.get('request_id')==request:
            if record.get('operation')!=data.get('operation','generate'):raise ValueError('This request identity belongs to another operation.')
            return self.public(record)
        if self.tasks or self.native.active_ids() or self.other_busy():raise ValueError('Another workflow is running. Wait before starting image generation.')
        operation=data.get('operation','generate')
        if operation not in ('generate','regenerate','edit'):raise ValueError('Choose image generation, regeneration or a prepared edit.')
        edit=record.get('edit') if operation=='edit' else None
        if operation=='edit' and not edit:raise ValueError('Prepare a selection before generating an edit.')
        if edit and record['accepted'].get(edit['side'])!=edit['source_id']:raise ValueError('The source image changed. Reopen the editor.')
        record.update(status='running',error='',cancel=False,operation=operation,request_id=request,started_at=time.time(),client_id=text(data.get('client_id',''),'Client',200))
        if operation=='regenerate':
            record['stages']={}
            record['generation_seed']=secrets.randbelow(2**32)
        if operation in ('generate','regenerate') and 'generation_seed' not in record:
            seed=record['config']['settings']['seed'];record['generation_seed']=secrets.randbelow(2**32) if seed<0 else seed
        self.library.save(record);self.tasks[ident]=asyncio.create_task(self.execute(record,edit))
        return self.public(record)

    def cancel(self,ident):
        record=self.get(ident)
        if ident in self.tasks:
            record['cancel']=True
            if record.get('pending'):self.native.cancel(record['pending']['prompt_id'])
            if self.prepare is ensure_models:cancel_download(ident)
            self.library.save(record)
        return self.public(record)

    def check_cancel(self,record):
        if record.get('cancel'):raise asyncio.CancelledError()

    def event(self,record,message):
        record['events']=(record['events']+[{'time':time.time(),'text':message}])[-40:]
        self.library.save(record)

    async def execute(self,record,edit=None):
        try:
            if edit:await self.stage(record,edit['side'],edit)
            else:
                for side in (('front','back') if record['config']['paired'] else ('single',)):
                    await self.stage(record,side)
            record['status']='cleaning'
        except asyncio.CancelledError:record.update(status='cancelled',error='Cancelled. Completed images and original revisions are preserved.')
        except InterruptedError as error:
            record.update(status='cancelled' if record.get('cancel') else 'failed',error=str(error))
        except Exception as error:record.update(status='failed',error=str(error))
        finally:await self.finish(record)

    async def finish(self,record):
        record.pop('pending',None);record.pop('dependency',None)
        try:
            if not self.native.active_ids():record['cleanup']=await self.lifecycle().release('Foundry image creation finished')
        except Exception as error:record['cleanup']={'status':'failed','error':str(error)}
        if record['status']=='cleaning':record['status']='complete'
        self.tasks.pop(record['id'],None);self.library.save(record)

    async def recover(self,record):
        try:
            await self.accept_pending(record)
            record.update(status='interrupted',error='Recovered the completed image. Continue to finish remaining work.')
        except Exception as error:record.update(status='failed',error=str(error))
        finally:await self.finish(record)

    def output_reference(self,record,revision_id,role):
        revision=self.library.revision(record,revision_id);path=self.library.file(record,revision_id)
        return {'id':revision_id,'filename':path.relative_to(self.library.output_root).as_posix()+' [output]',
                'sha256':revision['sha256'],'role':role,'description':'Preserve this exact subject and its proportions.'}

    async def stage(self,record,side,edit=None):
        self.check_cancel(record)
        references=copy.deepcopy(record['config']['references'])
        if edit:references=[self.output_reference(record,edit['source_id'],'image to edit')]
        elif side=='back':references.insert(0,self.output_reference(record,record['accepted']['front'],'front of this exact subject'))
        for ref in references:
            if not ref['filename'].endswith(' [output]'):
                path=owned_path(self.input_root,self.input_root/ref['filename'])
                if digest(path)!=ref['sha256']:raise ValueError('A reference changed since this creation was configured. Upload it again.')
        config={k:v for k,v in record['config'].items() if k!='name'}
        identity=fingerprint({'config':config,'side':side,'references':references})
        old=record['stages'].get(side)
        if not edit and old and old['fingerprint']==identity:
            self.library.file(record,old['revision_id']);self.event(record,'Reused the completed '+side+' image.');return
        record['stage']=('Editing ' if edit else 'Generating ')+side
        self.event(record,record['stage'])
        await self.lifecycle().barrier();await self.lifecycle().release('before Foundry image '+side)
        self.check_cancel(record)
        seed=secrets.randbelow(2**32) if edit else (record['generation_seed']+int(side=='back'))%(2**53-16)
        loop=asyncio.get_running_loop()
        def progress(value):loop.call_soon_threadsafe(lambda:record.update(dependency=value))
        await asyncio.to_thread(self.prepare,record,seed,references,lambda:record.get('cancel',False),progress)
        self.check_cancel(record)
        attempt=uuid.uuid4().hex
        compiled=self.compiler(record,side,seed,references,attempt,edit=edit)
        prompt_id=str(uuid.UUID(attempt))
        record['pending']={**compiled,'prompt_id':prompt_id,'side':side,'fingerprint':identity,'seed':seed,'started':time.time(),'edit':copy.deepcopy(edit)}
        self.library.save(record)
        await self.native.submit(compiled['graph'],prompt_id,record.get('client_id',''))
        await self.accept_pending(record);self.check_cancel(record)

    async def accept_pending(self,record):
        pending=record['pending'];history=await self.native.wait(pending['prompt_id'],7200,lambda:record.get('cancel',False))
        if history.get('status',{}).get('status_str')!='success':
            self.check_cancel(record)
            messages=history.get('status',{}).get('messages',[])
            reason='; '.join(str(m[1].get('exception_message','')) for m in messages if m[0]=='execution_error')
            raise ValueError('Image generation did not finish. '+(reason or 'Retry to keep completed images.'))
        output=history.get('outputs',{}).get(pending['output_node'],{})
        images=output.get('images',[])
        if len(images)!=1 or images[0].get('type')!='output':raise ValueError('The recipe did not save exactly one image.')
        entry=images[0];path=owned_path(self.library.directory(record['id']),self.library.output_root/entry.get('subfolder','')/entry['filename'])
        details=output.get('creation_provenance',[pending['provenance']])[0]
        source=None
        if pending.get('edit'):
            self.library.track_file(record,path)
            edit=pending['edit'];source=edit['source_id']
            if record['accepted'].get(pending['side'])!=source:raise ValueError('The source changed before this edit completed.')
            base=__package__.split('.foundry',1)[0] if '.foundry' in __package__ else ''
            masks=importlib.import_module((base+'.' if base else '')+'image_masks')
            original_path=self.library.file(record,source)
            mask_path=owned_path(self.library.directory(record['id']),self.library.output_root/edit['mask']['file'][:-9])
            with Image.open(original_path) as original,Image.open(path) as generated,Image.open(mask_path) as mask:
                composite=masks.composite_image(original,generated,mask.convert('L'))
            result=path.with_name(path.stem+'-accepted-area.png');composite.save(result);path=result
        revision=self.library.add_revision(record,pending['side'],path,details,accepted=source is None,source=source)
        record['outputs'].update(history.get('outputs',{}))
        record['last_stage']={k:pending[k] for k in ('prompt_id','side','graph','bindings') if k in pending}
        if source:record['candidate']=revision['id']
        else:record['stages'][pending['side']]={'fingerprint':pending['fingerprint'],'revision_id':revision['id'],'prompt_id':pending['prompt_id'],'seed':pending['seed']}
        record.pop('pending',None);self.event(record,'Saved '+pending['side']+(' edit preview.' if source else ' image.'))

    def prepare_edit(self,ident,side,revision_id,prompt,mask_bytes,feather=0,replace_detail=False):
        record=self.get(ident)
        if ident in self.tasks:raise ValueError('Wait for the current image job.')
        if record['accepted'].get(side)!=revision_id:raise ValueError('The source changed. Open the latest image.')
        prompt=text(prompt,'Edit description',8000,True)
        if type(replace_detail) is not bool:raise ValueError('Choose whether to replace selected details.')
        base=__package__.split('.foundry',1)[0] if '.foundry' in __package__ else ''
        masks=importlib.import_module((base+'.' if base else '')+'image_masks')
        source=self.output_reference(record,revision_id,'image to edit')
        path=self.library.file(record,revision_id)
        with Image.open(path) as image:mask=masks.prepare_mask(image.size,mask_bytes,feather)
        target=self.library.directory(ident)/(uuid.uuid4().hex+'-mask.png');mask.save(target)
        self.library.track_file(record,target)
        edit={'side':side,'source_id':revision_id,'source':{'id':revision_id,'file':source['filename'],'sha256':source['sha256']},
              'mask':{'file':target.relative_to(self.library.output_root).as_posix()+' [output]','sha256':digest(target)},
              'prompt':prompt,'feather':feather,'replace_detail':replace_detail}
        record['edit']=edit;record.pop('candidate',None);self.library.save(record);return self.public(record)

    def accept(self,ident,revision_id,expected):
        record=self.get(ident)
        if ident in self.tasks:raise ValueError('Wait for the current image job before accepting a revision.')
        self.library.accept(record,revision_id,expected);record.pop('candidate',None)
        self.library.save(record);return self.public(record)

    def handoff(self,ident,single=False):
        record=self.get(ident)
        if not record['config']['paired'] and not single:raise ValueError('This standalone image creation has no 3D asset handoff.')
        self.library.publish(record)
        references=[]
        sides=(('single','primary'),) if not record['config']['paired'] else ((('front','primary'),) if single else (('front','primary'),('back','back')))
        for side,role in sides:
            revision=self.library.revision(record,record['accepted'][side]);source=self.library.file(record,revision['id'])
            relative=Path('foundry-created')/ident/(side+'-'+revision['sha256'][:16]+'.png')
            target=owned_path(self.input_root,self.input_root/relative);target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if digest(target)!=revision['sha256']:raise ValueError('A previous handoff input changed; it has been preserved.')
            else:shutil.copyfile(source,target)
            references.append({'id':side,'filename':relative.as_posix(),'role':role,'description':record['config'].get(side,'')})
        from .lineage import save_handoff
        return {'name':record['config']['name'],'category':record['config']['category'],'references':references,
                'image_creation':save_handoff(self.library,record,references)}
