"""Bounded HTTP interface for the independent 3D-Guided workflow."""
import asyncio
import json
import time
from pathlib import Path
from aiohttp import web
from .definition import initial_spec,reconnect_spec,METHOD_ID,VERSION,QUAD_RETOPOLOGY_ENABLED,export_variants
from .fvb import runtime
from .fvb.recipes import editable_api

PREFIX='/mumblebox-foundry/v1/guided'
async def body(request):
    raw=await request.content.read(65537)
    if len(raw)>65536:raise ValueError('Guided options exceed 64 KB.')
    value=json.loads(raw or b'{}')
    if not isinstance(value,dict):raise ValueError('Supply one guided operation.')
    return value

def register(routes,factory,endpoint):
    @routes.get(PREFIX+'/template')
    @endpoint
    async def template(request):return editable_api(initial_spec())
    @routes.get(PREFIX+'/capabilities')
    @endpoint
    async def capabilities(request):
        from ..image_to_3d.readiness import viewer_module
        from ..image_to_3d.definition import DEFAULT_SELECTION,DEFAULTS
        from ....finishing.package_catalog import VARIANTS
        from ....finishing.runtime import settings
        registry=json.loads(Path(__file__).resolve().parents[3].joinpath('finishing/package_resources.json').read_text(encoding='utf-8'))
        ids=('qwen21','qwen21_union','pixal3d','trellis2','hi3d','dinov3','birefnet','moge2')+(('quadriflow',) if QUAD_RETOPOLOGY_ENABLED else ())
        return {'id':METHOD_ID,'version':VERSION,'defaults':initial_spec(),'selection':DEFAULT_SELECTION,
            'finishing_defaults':DEFAULTS,'viewer':viewer_module(),
            'runtime':{'blender_configured':Path(settings().get('blender','')).is_file()},
            'quad_retopology_enabled':QUAD_RETOPOLOGY_ENABLED,
            'exports':[{'id':k,'directory':VARIANTS[k][0],'formats':VARIANTS[k][1],'description':VARIANTS[k][2]} for k in export_variants()],
            'resources':[registry[key] for key in ids if key in registry],
            'license_note':'Each model and tool has its own terms. Model licenses do not automatically license your source images or generated asset. The package records the resources actually used.'}
    @routes.post(PREFIX+'/live')
    @endpoint
    async def live(request):
        value=await body(request);engine=factory().engine
        if value.get('selected'):
            engine.live={**{key:value.get(key) for key in ('request_id','job_id','client_id','workflow')},'seen':time.time()}
            if value.get('job_id'):
                job=engine.store.read(value['job_id'])
                spec=reconnect_spec(job['spec'],value.get('client_id'),value.get('workflow'))
                if spec!=job['spec']:engine.store.update(job['id'],spec=spec)
        return {'recorded':True}
    @routes.post(PREFIX+'/runs')
    @endpoint
    async def create(request):return factory().create(await body(request))
    @routes.get(PREFIX+'/runs/{id}')
    @endpoint
    async def get(request):return factory().public(factory().get(request.match_info['id']))
    @routes.patch(PREFIX+'/runs/{id}')
    @endpoint
    async def revise(request):return factory().revise(request.match_info['id'],await body(request))
    @routes.get(PREFIX+'/runs/{id}/graph')
    @endpoint
    async def graph(request):return editable_api(factory().get(request.match_info['id'])['spec'])
    @routes.post(PREFIX+'/runs/{id}/action')
    @endpoint
    async def action(request):
        data=await body(request);svc=factory();ident=request.match_info['id'];operation=data.get('operation')
        if operation=='cancel':
            job=svc.get(ident)
            if job['status']!='complete':svc.engine.runner.cancel(ident)
            if job.get('export_run_id'):svc.finisher.cancel(job['export_run_id'])
            return svc.public(svc.get(ident))
        if operation=='finish':return svc.finish(ident,data)
        return svc.start(ident,operation,data)
    @routes.post(PREFIX+'/runs/{id}/concept-edit')
    @endpoint
    async def concept_edit(request):
        from .editor import start
        return start(factory(),request.match_info['id'],await body(request))
    @routes.post(PREFIX+'/runs/{id}/accept-concept-edit')
    @endpoint
    async def accept_concept_edit(request):
        from .editor import accept
        await body(request)
        return accept(factory(),request.match_info['id'])
    @routes.get(PREFIX+'/runs/{id}/artifacts/{key}')
    @endpoint
    async def artifact(request):
        path,_=runtime.artifact(request.match_info['id'],request.match_info['key'])
        return web.FileResponse(path,headers={'Cache-Control':'no-store'})
    @routes.get(PREFIX+'/runs/{id}/production')
    @endpoint
    async def production(request):
        path=await asyncio.to_thread(factory().source_archive,request.match_info['id'])
        return web.FileResponse(path,headers={'Content-Disposition':'attachment; filename="private-production.zip"','Cache-Control':'no-store'})
    @routes.get(PREFIX+'/runs/{id}/package')
    @endpoint
    async def package(request):
        from ...artifacts import owned_path
        svc=factory();job=svc.get(request.match_info['id'])
        if not job.get('export_run_id'):raise ValueError('Prepare the selected output package first.')
        run=svc.finisher.get(job['export_run_id'])
        if not run.get('package'):raise ValueError('The output package is not complete.')
        path=owned_path(svc.finisher.output_root,run['package']['archive_path'])
        return web.FileResponse(path,headers={'Content-Disposition':'attachment; filename="'+path.name+'"','Cache-Control':'no-store'})
    @routes.post(PREFIX+'/runs/{id}/open-folder')
    @endpoint
    async def folder(request):
        from ...artifacts import open_folder
        await body(request)
        if request.remote not in ('127.0.0.1','::1'):raise ValueError('Use Download ZIP from another device.')
        svc=factory();job=svc.get(request.match_info['id'])
        await asyncio.to_thread(open_folder,svc.engine.store.folder(job['id']))
        return {'ok':True}
    @routes.post(PREFIX+'/runs/{id}/open-package-folder')
    @endpoint
    async def package_folder(request):
        from ...artifacts import owned_path,open_folder
        await body(request)
        if request.remote not in ('127.0.0.1','::1'):raise ValueError('Use Download ZIP from another device.')
        svc=factory();job=svc.get(request.match_info['id'])
        run=svc.finisher.get(job['export_run_id']) if job.get('export_run_id') else {}
        if not run.get('package'):raise ValueError('Finish the output package first.')
        path=owned_path(svc.finisher.output_root,run['package']['archive_path'])
        await asyncio.to_thread(open_folder,path.parent)
        return {'ok':True}
