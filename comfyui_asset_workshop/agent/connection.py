"""Report the SDK's real stdio handshake and tool activity to local Foundry."""
from contextlib import asynccontextmanager
from urllib.error import URLError
from uuid import uuid4

import anyio

from client import APIError

SESSION_HEADER = "X-Foundry-Agent-Session"


class AgentConnection:
    def __init__(self, client):
        self.client = client
        self.session = uuid4().hex
        self.initialized = False
        self.calls = 0

    def publish(self, *, used=False, closed=False):
        try:
            self.client.request("/agent/session", {
                "id": self.session, "calls": self.calls, "used": used, "closed": closed,
            }, timeout=2)
        except (OSError, URLError, APIError):
            # A temporary HTTP outage should not break the stdio protocol.
            pass

    async def send(self, *, used=False, closed=False):
        await anyio.to_thread.run_sync(lambda: self.publish(used=used, closed=closed))

    async def heartbeat(self):
        while True:
            await anyio.sleep(15)
            if self.initialized:
                await self.send()

    @asynccontextmanager
    async def lifespan(self, _server):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(self.heartbeat)
            try:
                yield {}
            finally:
                tasks.cancel_scope.cancel()
                if self.initialized:
                    with anyio.move_on_after(3, shield=True):
                        await self.send(closed=True)

    async def observe(self, context, call_next):
        if context.method == "notifications/initialized":
            result = await call_next(context)
            self.initialized = True
            self.client.headers[SESSION_HEADER] = self.session
            self.client.upload_api.headers[SESSION_HEADER] = self.session
            await self.send()
            return result
        if not self.initialized or context.method != "tools/call":
            return await call_next(context)
        self.calls += 1
        try:
            await self.send(used=True)
            return await call_next(context)
        finally:
            self.calls -= 1
            with anyio.move_on_after(3, shield=True):
                await self.send(used=True)
