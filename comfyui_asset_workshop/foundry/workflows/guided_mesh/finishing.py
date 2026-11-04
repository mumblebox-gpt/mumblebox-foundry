"""Independent guided run adapter to the established finishing/export owner."""
import copy
import json
import time
import uuid
from pathlib import Path
from ..image_to_3d.runs import WizardRuns,signature
from ..image_to_3d.definition import resolve_settings
from .definition import METHOD_ID,VERSION,QUAD_RETOPOLOGY_ENABLED,export_variants
from .fvb import runtime
from .fvb.journal import digest

class GuidedFinisher(WizardRuns):
    def selection(self,value):
        result=super().selection(value)
        if set(result['variants'])-set(export_variants()):
            raise ValueError('Quad retopology is disabled for 3D-Guided in this release.')
        return result

    def public(self,run):
        value=super().public(run)
        value['method']=METHOD_ID
        if value.get('package'):
            value['package']['download']='/mumblebox-foundry/v1/guided/runs/'+run['guided_job_id']+'/package'
        return value

    def fingerprint(self,run,stage):
        if stage in ('turnaround','geometry','refinement','texture'):
            return signature([VERSION,stage,run['guided_sources'][stage]])
        return super().fingerprint(run,stage)

    def adopt(self,job,name,selection,overrides,client_id):
        spec=job['spec'];store=runtime.journal();ident=uuid.uuid4().hex
        def path(key):
            p,record=runtime.artifact(job['id'],key)
            return str(p),record['sha256']
        clean,clean_hash=path('refined:glb');raw,raw_hash=path('refine:raw:glb')
        textured,texture_hash=path('textured')
        from .fvb.contracts import effective_image_key,effective_reference
        reference,_=path(effective_image_key(spec,effective_reference(spec)))
        image=runtime.preview_file(Path(reference),job['id'])
        front=(Path(image['subfolder'])/image['filename']).as_posix()+' [output]'
        original,_=path('original')
        settings=resolve_settings('default',overrides)
        settings.update({key:spec[key] for key in ('refine_resolution','refine_steps','refine_seed','cpu_offload',
            'texture_seed','texture_steps','texture_size','texture_guidance')})
        run=dict(id=ident,name=name,slug='3d-guided-'+job['id'][:8],category='props',created=time.time(),
            references=[{'filename':spec['original'],'role':'primary','description':spec['asset_description']}],
            profile='default',overrides=overrides,settings=settings,selection=self.selection(selection),
            status='idle',stage='',stages={},checkpoints={'front':front,'clean':clean,'refined':raw,'texture':textured},
            previews={},outputs={},events=[],version=VERSION,error='',cancel=False,client_id=client_id,
            turnaround_model='qwen21',reference_prompt='',guided_job_id=job['id'],
            guided_sources={'turnaround':job['artifacts']['concept:sheet']['sha256'],
                'geometry':job['artifacts']['reconstruction']['sha256'],'refinement':clean_hash,'texture':texture_hash})
        for stage,files in {'turnaround':[original],'geometry':[str(runtime.artifact(job['id'],'reconstruction')[0])],
                            'refinement':[clean,raw],'texture':[textured]}.items():
            run['stages'][stage]={'fingerprint':self.fingerprint(run,stage),'files':{p:digest(p) for p in files},'source_method':METHOD_ID}
        run['previews']['clean']=self.url(Path(clean),job['id'])
        run['previews']['texture']=self.url(Path(textured),job['id'])
        self.runs[ident]=run;self.save(run)
        return run

    def url(self,path,job_id):
        from ..image_to_3d.runs import view_url
        return view_url(runtime.preview_file(path,job_id))

    def metadata(self,run):
        job=runtime.journal().read(run['guided_job_id']);spec=job['spec']
        cameras=json.loads(runtime.artifact(job['id'],'enhanced:cameras')[0].read_text(encoding='utf-8'))
        # The shareable production record contains numeric calibration and hashes,
        # never machine paths, user prompts, source pixels or worker logs.
        def portable(value):
            if isinstance(value,dict):return {k:portable(v) for k,v in value.items() if k not in ('path','source_path','mesh_path','image_path','filename','output_dir')}
            if isinstance(value,list):return [portable(v) for v in value]
            if isinstance(value,str) and (':\\' in value or value.startswith('/')):return '[retained locally]'
            return value
        resources=['qwen21','qwen21_union','pixal3d','trellis2','hi3d','pymeshlab','dinov3','birefnet','moge2','pixelartistry','trellis_wrapper']
        keys={'detailed':'texture','game_balanced':'balanced','game_compact':'compact','print':'print'}
        receipts=[]
        for variant in run['selection']['variants']:
            p=Path(run['checkpoints']['quad_manifest']).parent/'editable-quads.blend' if variant=='quad_light' else Path(run['checkpoints'][keys[variant]])
            used=resources+(['quadriflow'] if variant=='quad_light' else [])
            if variant=='print' and run.get('print_report',{}).get('contact_repair'):used+=['meshlib']
            receipts.append({'variant_id':variant,'sha256':digest(p),'resources':used,
                'validation':[{'name':'3D-Guided production','status':'matched','note':'Bound to the immutable measured-view run '+job['id']} ]})
        metadata={'workflow_version':VERSION,'receipts':receipts,'production':{
            'method':METHOD_ID,'workflow_version':VERSION,'category':'props','run_id':job['id'],
            'selected_view_ids':spec['selected_view_ids'],'reference_view_id':spec['reference_view_id'],
            'camera_manifest':portable(cameras),'settings':{k:v for k,v in spec.items() if k not in ('original','extra_references','asset_description','special_instructions','enhancement_suffix','workflow_path','client_id')},
            'selection':run['selection'],'source_artifacts':{k:{x:v[x] for x in ('sha256','kind') if x in v} for k,v in job['artifacts'].items()},
            'source_download':'Original images, prompts, cameras, intermediates and execution records are retained locally; download the private production archive explicitly.'}}
        if job.get('image_creation'):metadata['production']['image_creation']=job['image_creation']
        lock=json.loads(Path(__file__).resolve().parents[3].joinpath('models.lock.json').read_text(encoding='utf-8'))
        keys=('qwen21','qwen21_clip','qwen21_vae','qwen21_union','pixal_single','pixal_multiview','shape_vae','dino','moge2','birefnet')
        metadata['production']['models']={key:{k:v for k,v in lock['models'][key].items() if k in ('name','repo','file','revision','sha256','license','license_url')} for key in keys}
        metadata['production']['texture_models']=[{k:v for k,v in item.items() if k in ('name','repo','file','revision','sha256','license','license_url')} for item in lock['worker_models']['trellis_texture']]
        return metadata

class NativeFinishingQueue:
    """Distinct native graph IDs; reuse the established queue and stage logic."""
    def __init__(self,native,bind):self.native,self.bind=native,bind
    def active_ids(self):return self.native.active_ids()
    def cancel(self,ident):return self.native.cancel(ident)
    def normalize(self,history):
        if history is None:return None
        result=copy.deepcopy(history)
        result['outputs']={str(int(key)-200000):v for key,v in result.get('outputs',{}).items()}
        return result
    def history(self,ident):return self.normalize(self.native.history(ident))
    async def submit(self,graph,ident,client_id):
        from .fvb.recipes import remap
        graph=copy.deepcopy(graph)
        if not QUAD_RETOPOLOGY_ENABLED:
            for node in graph.values():
                if node['class_type']=='Hi3DQuadFinish':node['inputs']['enabled']=False
        await self.bind(graph,client_id)
        return await self.native.submit(remap(graph,200000),ident,client_id)
    async def wait(self,*args):return self.normalize(await self.native.wait(*args))
