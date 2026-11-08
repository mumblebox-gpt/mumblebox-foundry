"""Thin HTTP boundary; HairRuns owns every state transition."""
import asyncio
import json
from aiohttp import web
from .definition import catalog
PREFIX='/mumblebox-foundry/v1/hair'

async def body(request):
    raw=await request.content.read(16385)
    if len(raw)>16384:raise ValueError('Hair options exceed 16 KB.')
    value=json.loads(raw or b'{}')
    if not isinstance(value,dict):raise ValueError('Supply one hair operation.')
    return value

def register(routes,factory,endpoint,notify):
    @routes.get(PREFIX+'/capabilities')
    @endpoint
    async def capabilities(request):return catalog()
    @routes.post(PREFIX+'/runs')
    @endpoint
    async def create(request):return factory().create(await body(request))
    @routes.get(PREFIX+'/runs/{id}')
    @endpoint
    async def get(request):
        service=factory();return service.public(service.get(request.match_info['id']))
    @routes.patch(PREFIX+'/runs/{id}')
    @endpoint
    async def update(request):return factory().update(request.match_info['id'],await body(request))
    @routes.get(PREFIX+'/runs/{id}/graph')
    @endpoint
    async def graph(request):
        from . import graph as compiler
        service=factory();record=service.get(request.match_info['id'])
        selected=int(request.query.get('selected',record['selected']))
        operation=request.query.get('operation','generate')
        if operation=='generate':
            if not 0<=selected<record['config']['variations']:raise ValueError('Choose a configured variation.')
            return compiler.generate(record,selected)
        if operation not in ('rig','preview','avatar_preview','motion_preview','export') or not 0<=selected<len(record['variants']):raise ValueError('Choose a saved variation and operation.')
        if operation=='rig':return compiler.rig(record,selected)
        return compiler.export(record,record['variants'][selected]['checkpoint'])
    @routes.post(PREFIX+'/runs/{id}/start')
    @endpoint
    async def start(request):
        data=await body(request);result=factory().start(request.match_info['id'],data)
        if data.get('client_id')=='foundry-agent':notify(result['id'])
        return result
    @routes.post(PREFIX+'/runs/{id}/cancel')
    @endpoint
    async def cancel(request):
        await body(request);return factory().cancel(request.match_info['id'])
    @routes.post(PREFIX+'/runs/{id}/show')
    @endpoint
    async def show(request):
        await body(request);record=factory().get(request.match_info['id']);notify(record['id'])
        return {'id':record['id'],'display_requested':True}
    @routes.get(PREFIX+'/runs/{id}/file')
    @endpoint
    async def file(request):
        path=factory().file(request.match_info['id'],request.query.get('path',''))
        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
        if request.query.get('download')=='1':
            from urllib.parse import quote
            headers['Content-Disposition']="attachment; filename*=UTF-8''"+quote(path.name)
        return web.FileResponse(path,headers=headers)
