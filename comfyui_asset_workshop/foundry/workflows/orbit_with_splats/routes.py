"""Bounded frame transfer from the local Foundry hybrid review surface."""
from ...agent_connection import local_request
from . import hybrid

def register_hybrid(routes, factory, endpoint, prefix):
    path = prefix + "/runs/{id}/hybrid"

    def context(request):
        if not local_request(request):
            raise ValueError("Export hybrid video from the local Foundry interface.")
        service = factory()
        return service, service.get(request.match_info["id"])

    @routes.post(path)
    @endpoint
    async def begin(request):
        service, run = context(request)
        return await hybrid.begin(service, run)

    @routes.put(path + "/{token}/frames/{index}")
    @endpoint
    async def frame(request):
        _, run = context(request)
        data = bytearray()
        async for chunk in request.content.iter_chunked(65536):
            data.extend(chunk)
            if len(data) > hybrid.MAX_FRAME:
                raise ValueError("The hybrid renderer did not send a valid frame.")
        return await hybrid.append(run, request.match_info["token"], int(request.match_info["index"]), data)

    @routes.post(path + "/{token}/finish")
    @endpoint
    async def finish(request):
        service, run = context(request)
        return await hybrid.finish(service, run, request.match_info["token"])

    @routes.delete(path + "/{token}")
    @endpoint
    async def cancel(request):
        _, run = context(request)
        await hybrid.discard(run, request.match_info["token"])
        return {"cancelled": True}
