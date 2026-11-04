"""Durable, independent job state. No model tensors or Foundry records."""
import copy
import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from .contracts import validate_spec, stages


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def atomic_json(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(temporary,path)


class Journal:
    def __init__(self,root):
        self.root=Path(root).resolve(); self.lock=threading.RLock()

    def folder(self,job_id):
        if not isinstance(job_id,str) or not re.fullmatch('[a-f0-9]{32}',job_id):
            raise ValueError('Invalid job identifier.')
        path=(self.root/'jobs'/job_id).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Job path escaped the lab state root.')
        return path

    def artifact_path(self,job_id,relative):
        root=self.folder(job_id)
        path=(root/relative).resolve()
        if path==root or not path.is_relative_to(root):
            raise ValueError('Artifact path escaped this job.')
        return path

    def create(self,spec,workflow):
        with self.lock:
            spec=validate_spec(spec,require_input=False)
            ident=uuid.uuid4().hex; spec['job_id']=ident
            job=dict(schema='fvb.job/1',id=ident,spec=spec,status='ready',completed={},artifacts={},
                     current_stage='',awaiting_stage='',error='',cancelled=False,created=time.time(),updated=time.time(),events=[])
            folder=self.folder(ident); folder.mkdir(parents=True)
            atomic_json(folder/'workflow.json',workflow)
            atomic_json(folder/'run.json',job)
            return copy.deepcopy(job)

    def read(self,ident):
        with self.lock:
            return json.loads((self.folder(ident)/'run.json').read_text(encoding='utf-8'))

    def update(self,ident,**values):
        with self.lock:
            job=self.read(ident); job.update(copy.deepcopy(values)); job['updated']=time.time()
            atomic_json(self.folder(ident)/'run.json',job)
            return copy.deepcopy(job)

    def event(self,ident,message):
        with self.lock:
            job=self.read(ident)
            job['events']=(job['events']+[dict(time=time.time(),message=message)])[-200:]
            return self.update(ident,events=job['events'])

    def revise(self,ident,overrides):
        with self.lock:
            if set(overrides)&{'job_id','schema'}:
                raise ValueError('Job identifier and schema are immutable; create a new job instead.')
            job=self.read(ident)
            if job['status']=='running':
                raise ValueError('Stop the owned job before revising its settings.')
            spec=validate_spec({**job['spec'],**overrides},require_input=False)
            changed={k for k in overrides if spec[k]!=job['spec'].get(k)}
            if not changed:
                return job
            repair_safe={'repair_requests','selected_view_ids','guided','client_id','reference_view_id',
                'reconstruction_seed','reconstruction_resolution','refine_resolution','refine_steps','refine_seed','cpu_offload','attention',
                'texture_enabled','texture_seed','texture_steps','texture_size','texture_guidance'}
            if not changed<=repair_safe:spec['repair_requests']={}
            keep=set()
            if not changed & {'original','category','asset_description','special_instructions','turnaround_seed','turnaround_steps','turnaround_cfg'}:
                keep.add('concept')
            if not changed & {'original','proxy_seed','proxy_resolution','structure_steps','shape_steps','upscale_steps','mesh_cfg','proxy_color_steps','proxy_color_cfg'}:
                keep.add('proxy')
            # Downstream edits preserve preceding stages only; all descendants are invalidated.
            sequence=stages(spec)
            if changed <= {'repair_requests'}:
                keep.update(s for s in sequence if s not in ('reconstruct','refine','texture') and not s.startswith('repair:'))
                keep.update('repair:'+v for v,r in spec['repair_requests'].items() if r==job['spec'].get('repair_requests',{}).get(v))
            elif changed <= {'texture_enabled','texture_seed','texture_steps','texture_size','texture_guidance'}:
                keep.update(s for s in sequence if s!='texture')
            elif changed <= {'refine_resolution','refine_steps','refine_seed','cpu_offload','attention','reference_view_id'}:
                keep.update(s for s in sequence if s not in ('refine','texture'))
            elif changed <= {'reconstruction_seed','reconstruction_resolution'}:
                keep.update(s for s in sequence if s not in ('reconstruct','refine','texture'))
            elif changed <= {'selected_view_ids'}:
                keep.update(s for s in sequence if s not in ('reconstruct','refine','texture'))
            elif changed <= {'sheet_gutter'}:
                keep.add('render')
            elif changed <= {'structure_control','mask_threshold','mask_dilation_px','canny_low_threshold','canny_high_threshold'}:
                keep.add('render')
            elif changed <= {'enhancement_seed','enhancement_steps','enhancement_cfg','adapter_strength','enhancement_suffix','extra_references','supplementary_resolution',
                             'control_strength','control_start_percent','control_end_percent','mask_mode','restore_black_gutters','controlled_cache_device'}:
                keep.add('render')
                if spec.get('enhancement_mode')=='sheet':keep.add('sheet')
            elif changed <= {'view_overrides'}:
                keep.add('render')
                for view in (s for s in sequence if s.startswith('enhance:')):
                    view_id=view.split(':',1)[1]
                    if spec['view_overrides'].get(view_id,{})==job['spec'].get('view_overrides',{}).get(view_id,{}):keep.add(view)
            if changed <= {'guided','client_id'}:
                keep.update(sequence)
            completed={k:v for k,v in job['completed'].items() if k in keep}
            # Keep all old files and record history rather than overwriting revisions.
            archive=self.folder(ident)/'revisions'/(str(time.time_ns())+'.json')
            atomic_json(archive,job)
            return self.update(ident,spec=spec,completed=completed,status='ready',error='',awaiting_stage='',cancelled=False)

    def publish(self,ident,stage,result,fingerprint):
        with self.lock:
            job=self.read(ident)
            for key,artifact in result.get('artifacts',{}).items():
                path=self.artifact_path(ident,artifact['path'])
                if not path.is_file() or digest(path)!=artifact['sha256']:
                    raise ValueError('Completed artifact is absent or changed: '+key)
            done=dict(job['completed']); done[stage]=dict(fingerprint=fingerprint,finished=time.time(),result=result)
            artifacts={**job['artifacts'],**result.get('artifacts',{})}
            return self.update(ident,completed=done,artifacts=artifacts)

    def reusable(self,job,stage,fingerprint):
        record=job['completed'].get(stage)
        if not record or record['fingerprint']!=fingerprint:
            return False
        for artifact in record['result'].get('artifacts',{}).values():
            path=self.artifact_path(job['id'],artifact['path'])
            if not path.is_file() or digest(path)!=artifact['sha256']:
                return False
        return True
