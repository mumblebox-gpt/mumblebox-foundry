"""Image creation HTTP actions. All state transitions belong to ImageRuns."""
import asyncio
import json
from aiohttp import web
from .definition import catalog
from .package import build as build_package

PREFIX='/mumblebox-foundry/v1/images'

async def body(request):
    raw=await request.content.read(65537)
    if len(raw)>65536:raise ValueError('Image options exceed 64 KB.')
    value=json.loads(raw or b'{}')
    if not isinstance(value,dict):raise ValueError('Supply one image operation.')
    return value

def register(routes,factory,endpoint,notify=lambda ident:None):
    @routes.get(PREFIX+'/capabilities')
    @endpoint
    async def capabilities(request):return catalog()

    @routes.get(PREFIX)
    @endpoint
    async def listing(request):
        query=request.query
        return await asyncio.to_thread(factory().library.list,query.get('search',''),query.get('category',''),
            query.get('kind','all'),query.get('sort','newest'),query.get('cursor',''),int(query.get('limit',24)))

    @routes.post(PREFIX)
    @endpoint
    async def create(request):return factory().create(await body(request))

    @routes.post(PREFIX+'/removal-preview')
    @endpoint
    async def removal_preview(request):
        data=await body(request)
        return factory().library.preview_removal(data.get('ids'),data.get('delete_files',False))

    @routes.post(PREFIX+'/remove')
    @endpoint
    async def remove(request):
        return factory().library.remove((await body(request)).get('token'))

    @routes.get(PREFIX+'/{id}')
    @endpoint
    async def get(request):
        service=factory();return service.public(service.get(request.match_info['id']))

    @routes.patch(PREFIX+'/{id}')
    @endpoint
    async def update(request):return factory().update(request.match_info['id'],await body(request))

    @routes.post(PREFIX+'/{id}/start')
    @endpoint
    async def start(request):
        data=await body(request);result=factory().start(request.match_info['id'],data)
        if data.get('client_id')=='foundry-agent':notify(result['id'])
        return result

    @routes.post(PREFIX+'/{id}/cancel')
    @endpoint
    async def cancel(request):
        await body(request);return factory().cancel(request.match_info['id'])

    @routes.post(PREFIX+'/{id}/show')
    @endpoint
    async def show(request):
        await body(request);record=factory().get(request.match_info['id']);notify(record['id'])
        return {'id':record['id'],'display_requested':True}

    @routes.get(PREFIX+'/{id}/files/{revision}')
    @endpoint
    async def image(request):
        service=factory();record=service.get(request.match_info['id'])
        path=service.library.file(record,request.match_info['revision'])
        return web.FileResponse(path,headers={'Cache-Control':'private, no-cache','X-Content-Type-Options':'nosniff'})

    @routes.post(PREFIX+'/{id}/save')
    @endpoint
    async def save(request):
        await body(request);service=factory();record=service.get(request.match_info['id'])
        if record['id'] in service.tasks:raise ValueError('Wait for image generation to finish before saving.')
        service.library.publish(record);return service.public(record)

    @routes.get(PREFIX+'/{id}/package')
    @endpoint
    async def package(request):
        service=factory();record=service.get(request.match_info['id'])
        if record['id'] in service.tasks:raise ValueError('Finish image creation before downloading the set.')
        path=build_package(service.library,record)
        return web.FileResponse(path,headers={'Content-Disposition':'attachment; filename="'+path.name+'"','Cache-Control':'private, no-cache'})

    @routes.post(PREFIX+'/{id}/accept')
    @endpoint
    async def accept(request):
        data=await body(request)
        return factory().accept(request.match_info['id'],data.get('revision_id'),data.get('expected'))

    @routes.post(PREFIX+'/{id}/edit')
    @endpoint
    async def edit(request):
        reader=await request.multipart();options=None;mask=None;seen=set()
        async for part in reader:
            if part.name not in ('mask','options') or part.name in seen:raise ValueError('Supply one mask and one options part.')
            seen.add(part.name)
            limit=20*1024**2 if part.name=='mask' else 16384
            chunks=[];total=0
            while True:
                chunk=await part.read_chunk()
                if not chunk:break
                total+=len(chunk)
                if total>limit:raise ValueError('The edit selection is too large.')
                chunks.append(chunk)
            value=b''.join(chunks)
            if part.name=='mask':mask=value
            elif part.name=='options':options=json.loads(value)
            else:raise ValueError('Supply mask and options only.')
        if not isinstance(options,dict) or mask is None:raise ValueError('Supply an edit selection and description.')
        return factory().prepare_edit(request.match_info['id'],options.get('side'),options.get('source_id'),
            options.get('prompt'),mask,options.get('feather',0),options.get('replace_detail',False))

    @routes.post(PREFIX+'/{id}/handoff')
    @endpoint
    async def handoff(request):
        options=await body(request);service=factory()
        if options.get('mode','pair') not in ('single','pair'):raise ValueError('Choose a single-image or paired handoff.')
        if request.match_info['id'] in service.tasks:raise ValueError('Finish image creation before the 3D handoff.')
        return service.handoff(request.match_info['id'],single=options.get('mode')=='single')

    @routes.post(PREFIX+'/{id}/reuse')
    @endpoint
    async def reuse(request):
        await body(request);service=factory()
        return service.create(service.get(request.match_info['id'])['config'])
