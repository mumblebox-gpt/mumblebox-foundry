"""Existing-Comfy queue coordinator. Never executes inside its own queued node."""
import asyncio
import copy
import importlib
import json
import shutil
import time
import uuid
from pathlib import Path
from aiohttp import ClientSession,ClientTimeout
from . import runtime
from .contracts import validate_spec, stages, view_records, effective_reference
from .journal import atomic_json, digest, signature
from .recipes import canonical_api, editable_api, compile_stage, endpoints, ancestor, ROOT
from .runner import JobRunner

_SERVICE=None


def service():
    global _SERVICE
    if _SERVICE is None:_SERVICE=Service()
    return _SERVICE


class Service:
    def __init__(self):
        from server import PromptServer
        from custom_nodes.comfyui_asset_workshop.resource_lifecycle import ResourceLifecycle
        from custom_nodes.comfyui_asset_workshop.routes import resource_sample
        self.server=PromptServer.instance; self.store=runtime.journal(); self.queue=self.server.prompt_queue
        self.tasks={}; self.live={}; self.owned_prompts={}
        # Reuse the installed lifecycle algorithm with a lab-only record callback.
        self.lifecycle=ResourceLifecycle(self.queue,resource_sample,lambda owner,report:None)
        self.runner=JobRunner(self.store,self.execute,self.fingerprint,self.interrupt)
        for path in (self.store.root/'jobs').glob('*/run.json') if (self.store.root/'jobs').exists() else []:
            job=json.loads(path.read_text(encoding='utf-8'))
            if job['status']=='running':self.store.update(job['id'],status='interrupted',error='Backend restarted. Explicit resume is required; no stage was resubmitted.')

    def fingerprint(self,job,stage):
        api=self.stage_graph(job,stage)
        required=set()
        for node in api.values():
            if node['class_type'] in ('G3D_LoadImage','G3D_LoadMesh'):
                required.add(node['inputs']['artifact_key'])
            if node['class_type']=='G3D_ReadCameras':required.add('enhanced:cameras' if node['inputs'].get('source')=='enhanced' else 'cameras')
            if node['class_type']=='G3D_RenderProxy':required.update(('proxy','original'))
            if node['class_type']=='G3D_SplitSheet':required.add('sheet:layout')
            if node['class_type']=='G3D_ControlSheet':
                required.add('cameras')
                required.update('render:'+v+':'+kind for v in ('front','right','back','left') for kind in
                    (('depth','alpha') if node['inputs']['control_mode']=='depth' else ('alpha',)))
            if node['class_type'] in ('G3D_LoadControl','G3D_FinalizeSheet'):
                required.update(('control:sheet','control:mask','control:metadata','sheet:layout','cameras'))
            if node['class_type']=='G3D_SaveImage' and node['inputs']['artifact_key']=='enhanced:sheet':required.add('sheet:layout')
        if stage.startswith('repair:'):
            view=stage.split(':')[1];required.update(('repair_source:'+view,'repair_mask:'+view,'enhanced:cameras'))
        # Repair adapters validate these records beyond the adjacent graph links.
        parents={key:job['artifacts'].get(key,{}).get('sha256') for key in required}
        recipe_hashes={p.name:digest(p) for p in [ROOT/'fvb/recipes.py',ROOT/'fvb/prompts.py',ROOT/'fvb/camera_math.py',ROOT/'fvb/blender_render.py',ROOT/'fvb/sheet.py',ROOT/'fvb/sheet_nodes.py',ROOT/'fvb/control.py',ROOT/'fvb/nodes.py',ROOT/'fvb/contracts.py',ROOT/'fvb/repair.py',ROOT/'fvb/repair_nodes.py',ROOT/'fvb/proxy.py',ROOT/'fvb/proxy_nodes.py',ROOT/'sources/provenance.json',ROOT/'sources/models.lock.json']}
        render_controls={k:job['spec'][k] for k in ('view_preset','azimuths_deg','elevation_deg','include_top','custom_views',
            'horizontal_fov_deg','orbit_margin','render_samples','render_threads','proxy_yaw_deg','render_size',
            'guide_material','proxy_cleanup','guide_smooth_factor','guide_smooth_iterations')} if stage=='render' else {}
        if stage=='render':render_controls.update({k:job['spec'].get(k,0) for k in ('proxy_pitch_deg','proxy_roll_deg')})
        selection=job['spec'].get('selected_view_ids',[]) if stage in ('reconstruct','refine','texture') else None
        repair_settings=job['spec'].get('repair_requests',{}).get(stage.split(':')[1]) if stage.startswith('repair:') else None
        return signature(dict(graph=api,parents=parents,recipes=recipe_hashes,render_controls=render_controls,selection=selection,repair_settings=repair_settings))

    def stage_graph(self,job,stage):
        path=self.store.folder(job['id'])/'workflow.json'
        frozen=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        graph=ancestor(frozen or canonical_api(job['spec']),endpoints(stage,job['spec']))
        for node in graph.values():node.pop('_meta',None)
        return graph

    def revise(self,ident,overrides):
        if 'repair_requests' in overrides:raise ValueError('Use the validated repair controls to apply or clear a request.')
        if set(overrides)&{'job_id','schema'}:raise ValueError('Job identifier and schema are immutable.')
        current=self.store.read(ident)
        if current['status']=='running':raise ValueError('Stop this job before changing inputs.')
        updated=validate_spec({**current['spec'],**overrides})
        source_records=self.capture_inputs(updated,ident,current['artifacts'])
        job=self.store.revise(ident,overrides)
        changed={key for key,record in source_records.items() if record['sha256']!=current['artifacts'].get(key,{}).get('sha256')}
        completed=job['completed']
        if 'original' in changed:completed={}
        elif changed:completed={k:v for k,v in completed.items() if k in ('concept','proxy','render')}
        artifacts={k:v for k,v in job['artifacts'].items() if not k.startswith('extra:')}
        job=self.store.update(ident,completed=completed,artifacts={**artifacts,**source_records})
        atomic_json(self.store.folder(ident)/'workflow.json',canonical_api(job['spec']))
        return job

    def source_images(self,spec):
        import folder_paths
        from PIL import Image
        root=Path(folder_paths.get_input_directory()).resolve()
        names=[('original',spec['original']),*[('extra:'+str(i),r['filename']) for i,r in enumerate(spec['extra_references'])]]
        sources=[]
        for key,name in names:
            path=(root/name).resolve()
            if not path.is_relative_to(root) or not path.is_file():raise ValueError('Input image unavailable: '+name)
            try:
                with Image.open(path) as image:image.verify()
            except Exception as error:raise ValueError('Input is not a readable image: '+name) from error
            sources.append((key,path))
        return sources

    def capture_inputs(self,spec,ident,previous=None):
        previous=previous or {}; copied={}; revision=str(time.time_ns())
        for i,(key,source) in enumerate(self.source_images(spec)):
            if previous.get(key,{}).get('sha256')==digest(source):
                copied[key]=previous[key];continue
            relative=f'inputs/{revision}/{i}'+source.suffix.lower();dest=self.store.artifact_path(ident,relative)
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
            copied[key]=runtime.record(dest,relative,'input',source_filename=source.name)
        return copied

    def create(self,candidate):
        import folder_paths
        spec=validate_spec(candidate)
        if spec['repair_requests']:raise ValueError('Create a new job without repairs; prepare its own current views first.')
        if not spec['client_id']:
            spec['client_id']=self.live.get('client_id','')
        if self.runner.active or any(not t.done() for t in self.tasks.values()):raise ValueError('A view-bridge job is already active.')
        self.source_images(spec)
        job=self.store.create(spec,{})
        spec=job['spec']; graph=canonical_api(spec)
        atomic_json(self.store.folder(job['id'])/'workflow.json',graph)
        copied=self.capture_inputs(spec,job['id'])
        return self.store.update(job['id'],artifacts=copied)

    def schedule(self,ident,operation):
        current=self.tasks.get(ident)
        if current and not current.done():raise ValueError('This job already has an in-flight stage.')
        job=self.store.read(ident)
        if operation=='start' and job['status']!='ready':raise ValueError('Start only a ready job; use Continue or explicit Resume for saved work.')
        if operation=='continue' and job['status']!='awaiting_review':raise ValueError('There is no completed review checkpoint awaiting Continue.')
        if operation=='resume' and job['status'] not in ('cancelled','failed','interrupted','ready'):raise ValueError('Explicit Resume is for stopped or revised work.')
        task=asyncio.create_task(self.runner.advance(ident,continue_review=operation=='continue',resume=operation=='resume'))
        self.tasks[ident]=task
        return dict(job_id=ident,operation=operation,scheduled=True,default_guided=job['spec']['guided'])

    def interrupt(self,ident):
        from server import PromptServer
        import nodes
        prompt_id=self.owned_prompts.get(ident)
        running,pending=self.queue.get_current_queue_volatile()
        if prompt_id and any(item[1]==prompt_id for item in running):nodes.interrupt_processing()
        if prompt_id and any(item[1]==prompt_id for item in pending):
            self.queue.delete_queue_item(lambda item:item[1]==prompt_id)

    async def idle(self,ident):
        started=time.monotonic()
        while self.queue.get_tasks_remaining():
            if self.store.read(ident)['cancelled']:raise InterruptedError('Stopped while waiting for Comfy queue.')
            if time.monotonic()-started>600:raise TimeoutError('Another Comfy job stayed active for ten minutes; no resources were cleared.')
            await asyncio.sleep(.5)

    async def guard(self,workflow_path='workflows/Foundry View Bridge — proxy guided reconstruction.json'):
        if self.live.get('workflow')!=workflow_path or time.time()-self.live.get('seen',0)>60:
            raise RuntimeError('Open the 3D-Guided wizard in the selected Foundry graph before continuing.')
        return {'workflow':workflow_path,'client_id':self.live.get('client_id')}

    async def bind_live(self,job,graph):
        await self.guard(job['spec']['workflow_path'])
        if not job['spec']['client_id']:raise ValueError('The existing native Comfy client ID is required to bind stage previews.')
        request_id=uuid.uuid4().hex
        saved_outputs=self.preview_outputs(job)
        await self.server.send_json('guided.bind',dict(job_id=job['id'],request_id=request_id,graph=graph,
            canvas_graph=editable_api(job['spec']),saved_outputs=saved_outputs,spec=job['spec']),sid=job['spec']['client_id'])
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if self.live.get('request_id')==request_id and self.live.get('job_id')==job['id']:
                return
            await asyncio.sleep(.2)
        raise RuntimeError('The existing lab canvas did not acknowledge current stage inputs; generation was not submitted.')

    def preview_outputs(self,job):
        outputs={}
        for completed in job['completed'].values():outputs.update(copy.deepcopy(completed['result'].get('outputs',{})))
        for ident,key in {'4781':'proxy:glb','7901':'reconstruction:glb','7992':'refined:glb','8803':'textured'}.items():
            record=job['artifacts'].get(key)
            if ident not in outputs or not record:continue
            path=self.store.artifact_path(job['id'],record['path'])
            if digest(path)!=record['sha256']:raise ValueError('Preview artifact changed: '+key)
            outputs[ident]['3d']=[runtime.preview_file(path,job['id'])]
        return outputs

    async def execute(self,job,stage):
        import psutil
        from comfy.cli_args import args
        ident=job['id']; spec=job['spec']
        graph=self.stage_graph(job,stage)
        await self.idle(ident)
        await self.bind_live(job,graph)
        # Actual native processing IDs belong exclusively to the guided branch.
        # Journal/recipe IDs remain stable within this independent engine.
        from .recipes import remap
        graph=remap(graph,100000)
        await self.lifecycle.release('before view bridge '+stage)
        if psutil.virtual_memory().available < spec['min_ram_free_gb']*1024**3:
            raise RuntimeError('Not enough free system RAM for the selected stage; saved checkpoints retained.')
        if stage=='enhance_sheet' and spec['render_size']==2048 and psutil.virtual_memory().available < 28*1024**3:
            raise RuntimeError('Experimental 4K-class sheet requires at least 28 GiB free RAM before inference. No resize or alternate inference was started.')
        request_id=stage.replace(':','_')+'-'+str(time.time_ns())
        folder=self.store.folder(ident)/'stages'/request_id
        folder.mkdir(parents=True)
        atomic_json(folder/'prompt.json',graph)
        if stage.startswith('enhance:'):
            from .prompts import enhancement
            text,roles=enhancement(spec,stage.split(':')[1])
            atomic_json(folder/'references.json',dict(prompt=text,references=[{**r,'artifact':job['artifacts'][r['key']]} for r in roles],settings=spec))
        if stage=='enhance_sheet':
            from .prompts import sheet_enhancement
            text,roles=sheet_enhancement(spec)
            atomic_json(folder/'references.json',dict(prompt=text,references=[{**r,'artifact':job['artifacts'][r['key']]} for r in roles],settings=spec))
        self.store.update(ident,request_id=request_id)
        prompt_id=str(uuid.uuid4()); self.owned_prompts[ident]=prompt_id
        self.store.update(ident,pending=dict(prompt_id=prompt_id,stage=stage,request_id=request_id))
        history=None; guard_warning=''; next_guard=time.monotonic()+30
        try:
            async with ClientSession(timeout=ClientTimeout(total=60)) as client:
                async with client.post(f'http://127.0.0.1:{args.port}/prompt',json=dict(prompt=graph,prompt_id=prompt_id,client_id=spec['client_id'],extra_data={'fvb_job_id':ident})) as response:
                    answer=await response.json()
                    if response.status>=400:raise ValueError('Comfy rejected stage: '+json.dumps(answer))
            started=time.monotonic()
            while history is None:
                history=self.queue.get_history(prompt_id).get(prompt_id)
                if self.store.read(ident)['cancelled']:
                    self.interrupt(ident)
                    running,pending=self.queue.get_current_queue_volatile()
                    if not any(item[1]==prompt_id for item in running+pending):raise InterruptedError('Owned stage cancelled.')
                if time.monotonic()>next_guard:
                    try:await self.guard(spec['workflow_path'])
                    except Exception as error:guard_warning=str(error)
                    next_guard=time.monotonic()+30
                running,pending=self.queue.get_current_queue_volatile()
                if history is None and not any(item[1]==prompt_id for item in running+pending) and time.monotonic()-started>3:
                    raise InterruptedError('Owned prompt disappeared from the queue without completion; no later stage was started.')
                if time.monotonic()-started>6*3600:
                    self.interrupt(ident); raise TimeoutError('Owned stage exceeded six hours; no later stage was started.')
                if history is None:await asyncio.sleep(.5)
            atomic_json(folder/'history.json',history)
            if history.get('status',{}).get('status_str')!='success':
                raise RuntimeError('Stage failed: '+json.dumps(history.get('status',{}))[-4000:])
            history=copy.deepcopy(history)
            history['outputs']={str(int(key)-100000):value for key,value in history.get('outputs',{}).items()}
            artifacts={}
            for output in history.get('outputs',{}).values():
                for item in output.get('fvb_artifacts',[]):artifacts.update(item)
            required={'concept':['appearance','concept:sheet','concept:front','concept:left','concept:back','concept:right'],
                      'proxy':['proxy','proxy:glb','proxy:fov'],'render':['cameras',*['render:'+v['id'] for v in view_records(spec)]],
                      'sheet':['guide:sheet','sheet:layout'],'enhance_sheet':['enhanced:sheet'],
                      'split':['enhanced:cameras',*['enhanced:'+v['id'] for v in view_records(spec)]],
                      'prepare':['prepared:'+v['id'] for v in view_records(spec)],'reconstruct':['reconstruction'],
                      'refine':['refined','refine:raw'],'texture':['textured']}.get(stage,[stage.replace('enhance:','enhanced:')])
            if stage=='proxy' and spec.get('proxy_processing')=='upright_solid_box':required+=['proxy:raw','proxy:orientation','proxy:processing','proxy:conditioning_input']
            if spec.get('structure_control','off')!='off':
                if stage=='sheet':required+=['control:sheet','control:mask','control:metadata']
                if stage=='enhance_sheet':required+=['enhanced:sheet_raw']
            if stage.startswith('repair:'):
                view=stage.split(':')[1];required=['corrected:'+view,'repair_raw:'+view,'repair_applied_mask:'+view,'repair_report:'+view]
            if set(required)-artifacts.keys():raise RuntimeError('Stage finished without required artifacts: '+str(set(required)-artifacts.keys()))
            # Preview delivery uses the exact native output-node IDs in the selected graph.
            result=dict(outputs=history.get('outputs',{}),artifacts=artifacts,requires_review=spec['guided'] and (bool(guard_warning) or stage=='split' or stage.startswith('repair:')),warning=guard_warning)
            # Commit successful outputs before resource cleanup: an unload error must not lose a completed stage.
            self.store.publish(ident,stage,result,self.fingerprint(job,stage))
            if guard_warning:raise RuntimeError(guard_warning+' Completed outputs were retained; restore the active wizard before retrying.')
            return result
        finally:
            self.owned_prompts.pop(ident,None)
            if self.store.read(ident)['cancelled']:
                await self.wait_owned_idle(prompt_id)
            else:
                await self.idle(ident)
            if self.queue.get_tasks_remaining()==0:
                report=await self.lifecycle.release('after view bridge '+stage)
                atomic_json(folder/'resources.json',report)
            self.store.update(ident,pending=None)

    async def wait_owned_idle(self,prompt_id):
        while True:
            running,pending=self.queue.get_current_queue_volatile()
            if not any(item[1]==prompt_id for item in running+pending):return
            await asyncio.sleep(.25)

    async def repair_control(self,operation,ident,view_id,ticket_id='',mask_filename='',controls=None):
        if operation=='status' and not ident:return dict(status='ready',message='No job selected. Repair is optional after full-frame preparation; no inference scheduled.')
        job=self.store.read(ident)
        if not job['spec'].get('repair_enabled'):raise ValueError('Select the repair-and-texture workflow job.')
        if operation=='status':return dict(job_id=ident,status=job['status'],repairs=job['spec']['repair_requests'],inference_scheduled=False)
        await self.guard(job['spec']['workflow_path'])
        if job['status']=='running':raise ValueError('Wait for the owned stage to finish before editing.')
        import folder_paths
        from .repair import prepare_editor,apply_request
        if operation=='prepare_editor':
            result=prepare_editor(self.store,job,folder_paths.get_input_directory(),view_id)
            await self.server.send_json('guided.repair_editor',result,sid=job['spec']['client_id'])
            return result
        if operation=='apply_repair':
            requests,artifacts=apply_request(self.store,job,folder_paths.get_input_directory(),ticket_id,mask_filename,controls or {})
            ticket=json.loads(self.store.artifact_path(ident,'repair-editor/'+ticket_id+'/ticket.json').read_text(encoding='utf-8'))
            if ticket['view_id']!=view_id:raise ValueError('Selected view differs from the editor ticket.')
        elif operation=='clear_repair':
            requests={k:v for k,v in job['spec']['repair_requests'].items() if k!=view_id};artifacts=job['artifacts']
        else:raise ValueError('Unknown repair operation.')
        job=self.store.revise(ident,{'repair_requests':requests})
        job=self.store.update(ident,artifacts=artifacts)
        atomic_json(self.store.folder(ident)/'workflow.json',canonical_api(job['spec']))
        await self.server.send_json('guided.repair_changed',dict(job_id=ident,spec=job['spec']),sid=job['spec']['client_id'])
        return dict(job_id=ident,status=job['status'],repairs=job['spec']['repair_requests'],inference_scheduled=False,
            message='Request saved. Explicit Resume runs the repair then pauses for review. Clear removes the request while preserving every saved file.')

    def control_from_node(self,operation,spec,ident):
        async def control():
            if operation=='readiness':
                from .readiness import inspect
                return await inspect(spec)
            if operation=='create':return self.create(spec)
            if operation=='status':return self.store.read(ident)
            if operation=='cancel':return self.runner.cancel(ident)
            action=operation
            if operation in ('apply_views','continue','resume'):
                current=self.store.read(ident)
                selection=spec.get('selected_view_ids',current['spec'].get('selected_view_ids',[]))
                if selection!=current['spec'].get('selected_view_ids',[]):
                    current=self.revise(ident,{'selected_view_ids':selection});action='resume'
                if operation=='apply_views':
                    return dict(job_id=ident,selected_views=current['spec']['selected_view_ids'],effective_reference=effective_reference(current['spec']),
                        status=current['status'],message='Selection saved; enhanced images retained. Continue if awaiting review, otherwise Resume.')
            return self.schedule(ident,action)
        future=asyncio.run_coroutine_threadsafe(control(),self.server.loop)
        return future.result(timeout=90)
