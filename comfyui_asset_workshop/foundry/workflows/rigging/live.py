"""Relay read-only measurements to the active browser with one request per kind."""
import asyncio
from uuid import uuid4


class ViewportRequests:
    def __init__(self, notify):
        self.notify = notify
        self.pending = {}

    async def ask(self, kind, window, data, validate):
        if kind in self.pending:
            raise ValueError("Wait for the current viewport inspection to finish.")
        future = asyncio.get_running_loop().create_future()
        token = uuid4().hex
        self.pending[kind] = (window["browser"], token, future, validate)
        try:
            self.notify({"action":kind,"id":window["id"],"browser":window["browser"],"token":token,**data})
            return await asyncio.wait_for(future,12)
        except asyncio.TimeoutError:
            raise ValueError("The wizard did not finish the inspection. Check the visible rig and try again.") from None
        finally:
            self.pending.pop(kind, None)

    def receive(self, kind, data):
        current = self.pending.get(kind)
        if not current:
            return {"accepted":False}
        browser, token, future, validate = current
        if data.get("browser")!=browser or data.get("token")!=token or future.done():
            return {"accepted":False}
        try:
            if data.get("failed"):
                raise ValueError("The visible mesh changed or could not be measured. Inspect the current rig again.")
            result = validate(data)
        except (ValueError, AttributeError, TypeError) as error:
            future.set_exception(ValueError(str(error)))
            return {"accepted":False}
        future.set_result(result)
        return {"accepted":True}
