"""Own 3D-Guided sessions without changing Turnaround's execution contract."""
import asyncio
import copy
import json
import time
import uuid
import zipfile
from pathlib import Path
from .definition import initial_spec,resolve_spec,METHOD_ID,VERSION
from .fvb.service import service
from .fvb import runtime
from .fvb.journal import atomic_json
from .finishing import GuidedFinisher,NativeFinishingQueue

ACTIVE=None
def busy():
    return ACTIVE is not None and bool(ACTIVE.tasks or ACTIVE.engine.runner.active or ACTIVE.finisher.tasks)

class GuidedRuns:
    def __init__(self,state,input_root,output_root,native,lifecycle,other_busy,selection_parser,variants):
        self.state=Path(state);self.engine=service();self.tasks={};self.other_busy=other_busy;self.native=native
        self.finisher=GuidedFinisher(self.state/'exports',input_root,output_root,
            NativeFinishingQueue(native,self.bind_finishing),lifecycle,
            lambda:other_busy() or bool(self.engine.runner.active),selection_parser,variants)

    def get(self,ident):return self.engine.store.read(ident)
    def public(self,job):
        result=copy.deepcopy(job)
        for key,value in result['artifacts'].items():
            value['url']='/mumblebox-foundry/v1/guided/runs/'+job['id']+'/artifacts/'+key
            if value['kind']=='glb':value['preview']=runtime.preview_entry(job['id'],value['sha256'],'.glb')
        result['active']=job['id'] in self.tasks or job['id'] in self.engine.runner.active
        result['preparing']=job.get('preparing',False)
        if job.get('export_run_id'):result['finishing']=self.finisher.public(self.finisher.get(job['export_run_id']))
        return result

    def create(self,data):
        if busy() or self.other_busy():raise ValueError('Wait for the current Foundry job to finish.')
        name=data.get('name','').strip()
        if not name or len(name)>100 or any(c in name for c in '<>:"/\\|?*') or any(ord(c)<32 for c in name):
            raise ValueError('Enter a safe asset name of 1–100 characters.')
        spec=resolve_spec(data.get('controls',{}),data.get('original',''),data.get('client_id',''),data.get('workflow_path'))
        from ..image_creation.lineage import resolve_handoff
        from .fvb.journal import digest
        source=dict(self.engine.source_images(spec))['original']
        image_creation=resolve_handoff(self.state.parent/'image-creation',data.get('image_creation'),
            [{'filename':spec['original'],'sha256':digest(source)}])
        job=self.engine.create(spec)
        return self.public(self.engine.store.update(job['id'],name=name,image_creation=image_creation))

    def revise(self,ident,data):
        spec=resolve_spec(data,self.get(ident)['spec']['original'],self.get(ident)['spec']['client_id'],self.get(ident)['spec']['workflow_path'])
        current=self.get(ident)['spec']
        overrides={key:spec[key] for key in data if spec[key]!=current[key]}
        return self.public(self.engine.revise(ident,overrides)) if overrides else self.public(self.get(ident))

    def start(self,ident,operation,data=None):
        if busy() or self.other_busy():raise ValueError('Wait for the current Foundry stage to finish.')
        if operation=='rocket':
            from ..image_to_3d.definition import resolve_settings
            data=data or {};job=self.get(ident)
            selection=self.finisher.selection(data['selection'])
            overrides=data.get('overrides',{});resolve_settings('default',overrides)
            # Continuation policy is not an inference input. Preserve completed
            # stages instead of invalidating geometry when Rocket is selected.
            spec={**job['spec'],'guided':False}
            self.engine.store.update(ident,spec=spec,rocket=True,rocket_selection=selection,rocket_overrides=overrides)
            operation='start' if job['status']=='ready' else 'continue' if job['status']=='awaiting_review' else 'resume'
        if operation not in ('start','continue','resume'):raise ValueError('Choose Start, Continue or Retry.')
        if operation=='resume':self.engine.store.update(ident,cancelled=False)
        self.engine.store.update(ident,started_at=time.time())
        self.tasks[ident]=asyncio.create_task(self.prepare_start(ident,operation))
        return self.public(self.get(ident))

    async def prepare_start(self,ident,operation):
        self.engine.store.update(ident,preparing=True,error='')
        try:
            from ..image_to_3d.readiness import ensure
            loop=asyncio.get_running_loop()
            def cancelled():return self.get(ident)['cancelled']
            def progress(value):loop.call_soon_threadsafe(lambda:self.engine.store.update(ident,dependency=value))
            # All selected resources are prepared before inference. ensure owns
            # hashes/downloads and reuses its cached verification receipts.
            for stage in ('turnaround','geometry','guided','refinement','texture'):
                await asyncio.to_thread(ensure,stage,self.state,cancelled,ident,progress,'qwen21')
            self.engine.store.update(ident,preparing=False,dependency=None)
            self.engine.schedule(ident,operation)
            await self.engine.tasks[ident]
            job=self.get(ident)
            if job.get('rocket') and job['status']=='complete':
                # No await between relinquishing this operation and acquiring
                # the established finisher's owned lane.
                self.tasks.pop(ident,None)
                self.finish(ident,{'selection':job['rocket_selection'],'overrides':job.get('rocket_overrides',{})},continued=True)
        except (Exception,asyncio.CancelledError) as error:
            self.engine.store.update(ident,preparing=False,dependency=None,status='cancelled' if self.get(ident)['cancelled'] else 'failed',error=str(error))
        finally:self.tasks.pop(ident,None)

    async def bind_finishing(self,graph,client_id,offset=200000):
        request=uuid.uuid4().hex
        await self.engine.server.send_json('guided.bind',{'request_id':request,'graph':graph,'offset':offset,'finishing':True},sid=client_id)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if self.engine.live.get('request_id')==request:return
            await asyncio.sleep(.1)
        raise ValueError('The active 3D-Guided wizard did not bind the finishing graph. No stage was submitted.')

    def finish(self,ident,data,*,continued=False):
        job=self.get(ident)
        if job['status']!='complete' or 'textured' not in job['artifacts']:raise ValueError('Complete and review the textured master before choosing exports.')
        if busy() or self.other_busy():raise ValueError('Wait for the current Foundry job to finish.')
        overrides=data.get('overrides',{})
        if set(overrides)-{'balanced_triangles','compact_triangles','quad_count','print_height_mm'}:
            raise ValueError('Choose supported output geometry settings; texture settings belong to the preceding generation step.')
        if job.get('export_run_id'):
            from ..image_to_3d.definition import resolve_settings
            run=self.finisher.get(job['export_run_id'])
            revised=resolve_settings('default',overrides)
            for key in ('balanced_triangles','compact_triangles','quad_count','print_height_mm'):run['settings'][key]=revised[key]
            run.update(selection=self.finisher.selection(data['selection']),overrides=overrides)
            self.finisher.save(run)
        else:run=self.finisher.adopt(job,job['name'],data['selection'],overrides,job['spec']['client_id'])
        self.engine.store.update(ident,export_run_id=run['id'],started_at=job.get('started_at') if continued else time.time())
        self.finisher.start(run['id'],'finish',job['spec']['client_id'],data.get('request_id') or uuid.uuid4().hex)
        return self.public(self.get(ident))

    def source_archive(self,ident):
        job=self.get(ident)
        if job['status']=='running' or busy():raise ValueError('Finish or stop the current stage before downloading the production archive.')
        from .fvb.journal import signature
        root=self.engine.store.folder(ident);target=root/('private-production-'+signature(job)[:12]+'.zip')
        if target.exists():return target
        files=[p for p in root.rglob('*') if p.is_file() and not p.name.startswith('private-production')]
        if len(files)>20000 or sum(p.stat().st_size for p in files)>30*1024**3:raise ValueError('The retained production exceeds the download limit. Use the recorded local folder.')
        temporary=target.with_suffix('.partial')
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('README.txt','PRIVATE PRODUCTION ARCHIVE\nContains original images, prompts, local execution paths, cameras and intermediate meshes. Review before sharing.\n')
            for path in files:
                if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Production file escaped its run folder.')
                archive.write(path,path.relative_to(root).as_posix())
        temporary.replace(target)
        return target
