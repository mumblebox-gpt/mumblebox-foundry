"""HTTP boundary for the independently owned splat workflow."""
import asyncio,json
from aiohttp import web
from copy import deepcopy
from .definition import capabilities,DEFAULTS
from .graph import compile_stage
PREFIX='/mumblebox-foundry/v1/splat'

async def body(request):
    raw=await request.content.read(32769)
    if len(raw)>32768:raise ValueError('Splat options exceed 32 KB.')
    value=json.loads(raw or b'{}')
    if not isinstance(value,dict):raise ValueError('Supply a splat operation.')
    return value

def register(routes,factory,endpoint):
    @routes.get(PREFIX+'/capabilities')
    @endpoint
    async def cap(request):return capabilities()
    @routes.get(PREFIX+'/template')
    @endpoint
    async def template(request):return compile_stage(dict(id='preview',config=deepcopy(DEFAULTS),source_sha256='',artifacts={}), 'generation', full=True)
    @routes.post(PREFIX+'/runs')
    @endpoint
    async def create(request):return factory().create(await body(request))
    @routes.get(PREFIX+'/runs/{id}')
    @endpoint
    async def get(request):
        s=factory();return s.public(s.get(request.match_info['id']))
    @routes.patch(PREFIX+'/runs/{id}')
    @endpoint
    async def update(request):return factory().update(request.match_info['id'],await body(request))
    @routes.get(PREFIX+'/runs/{id}/graph')
    @endpoint
    async def graph(request):
        s=factory();r=s.get(request.match_info['id']);stage=request.query.get('stage','generation')
        if stage not in ('generation','refinement','cleanup'):raise ValueError('Unknown splat graph stage.')
        return compile_stage(r,stage,full=request.query.get('full')=='1')
    @routes.post(PREFIX+'/runs/{id}/start')
    @endpoint
    async def start(request):
        data = await body(request)
        result = factory().start(request.match_info['id'], data)
        if data.get('client_id') == 'foundry-agent':
            from server import PromptServer
            PromptServer.instance.send_sync('mumblebox-foundry-splat', {'id': result['id']})
        return result
    @routes.post(PREFIX+'/runs/{id}/cancel')
    @endpoint
    async def cancel(request):
        await body(request);return factory().cancel(request.match_info['id'])
    @routes.post(PREFIX+'/runs/{id}/show')
    @endpoint
    async def show(request):
        await body(request);r=factory().get(request.match_info['id'])
        from server import PromptServer
        PromptServer.instance.send_sync('mumblebox-foundry-splat',{'id':r['id']})
        return {'id':r['id'],'display_requested':True}
    @routes.get(PREFIX+'/runs/{id}/file')
    @endpoint
    async def file(request):
        path=factory().file(request.match_info['id'],request.query.get('path',''));headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
        if request.query.get('download')=='1':
            from urllib.parse import quote
            headers['Content-Disposition']="attachment; filename*=UTF-8''"+quote(path.name)
        return web.FileResponse(path,headers=headers)
