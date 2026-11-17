"""Exercise recoverable binding through its actual HTTP routes without Blender."""
import asyncio
from functools import wraps
import sys
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_rigging
from foundry.workflows.rigging import routes, runtime
from foundry.agent_connection import SESSION_HEADER


class RiggingJobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture=test_rigging.RiggingTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.table=web.RouteTableDef()
        self.events=asyncio.Queue()

        def endpoint(function):
            @wraps(function)
            async def call(request):
                try:
                    value=await function(request)
                    return value if isinstance(value,web.StreamResponse) else web.json_response(value)
                except ValueError as error:
                    return web.json_response({'error':str(error)},status=400)
            return call

        self.service=routes.register(self.table,self.fixture.library,endpoint,lambda *args:self.events.put_nowait(args))
        self.run=self.service.create(self.fixture.id,self.service.sources(self.fixture.id)[0]['id'])
        app=web.Application()
        app.add_routes(self.table)
        self.client=TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.local=patch.object(routes,'local_request',return_value=True)
        self.local.start()
        self.addCleanup(self.local.stop)
        self.path=routes.PREFIX+'/runs/'+self.run['id']
        self.browser = "a" * 32
        self.live = routes.PREFIX + "/live"
        await self.client.post(self.live, json={"browser": self.browser, "id": self.run["id"], "opened": True})

    async def post(self,action,data, *, agent=False):
        headers = {SESSION_HEADER: "f" * 32} if agent else {}
        response=await self.client.post(self.path+'/'+action,json={"browser": self.browser, **data}, headers=headers)
        return response.status,await response.json()

    async def test_stop_denies_every_agent_mutation_even_with_a_browser_id(self):
        payload = {"browser": self.browser, "id": self.run["id"], "action": "stop"}
        receipt = await self.client.post(self.live + "/control", json=payload)
        self.assertEqual(receipt.status, 200)
        self.assertFalse((await receipt.json())["enabled"])
        before = self.service.path(self.run["id"]).read_bytes()
        for route, fields in (
            ("edit", {"action": "reset", "orientation": 2, "revision": 0}),
            ("edit", {"action": "select", "joint": "elbow.L", "revision": 0}),
            ("command", {"action": "undo", "args": {}, "request_id": "c" * 32, "rig_revision": 0}),
            ("fit", {"method": "guided_template", "orientation": 2, "revision": 0}),
            ("fit", {"method": "local_ai", "request_id": "b" * 32, "revision": 0}),
            ("bind-start", {"request_id": "b" * 32, "revision": 0}),
            ("bind", {"request_id": "b" * 32, "revision": 0}),
            ("export", {"revision": 0}),
            ("open-blender", {"revision": 0}),
            ("show", {}),
        ):
            with self.subTest(route=route, fields=fields):
                status, result = await self.post(route, fields, agent=True)
                self.assertEqual(status, 409, result)
                self.assertEqual(result["code"], "stopped")
        self.assertEqual(self.service.path(self.run["id"]).read_bytes(), before)
        result = await self.client.post(self.live + "/control", json={**payload, "action": "prepare_resume"},
                                        headers={SESSION_HEADER: "f" * 32})
        self.assertEqual(result.status, 400)
        result = await self.client.post(self.path + "/edit", json={"action": "reset", "orientation": 2, "revision": 0})
        self.assertEqual(result.status, 400)
        status, result = await self.post("edit", {"action": "select", "joint": "knee.L", "revision": 0})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["selected_joint"], "knee.L")

    async def test_same_request_recovers_status_and_cancel_keeps_joints(self):
        started=threading.Event()
        def bind(service,run_id,revision,request_id,preset,custom,cancelled, *, context):
            started.set()
            deadline=time.monotonic()+3
            while not cancelled() and time.monotonic()<deadline:
                time.sleep(.01)
            if cancelled():
                raise InterruptedError('Binding cancelled; original joints preserved.')
            raise ValueError('Test worker timed out')

        with patch.object(runtime,'bind',side_effect=bind) as worker:
            data={'revision':self.run['revision'],'request_id':'b1ad'*8,'preset':'standard'}
            status,first=await self.post('bind-start',data)
            self.assertEqual(status,200,first)
            self.assertEqual(first['status'],'running')
            _,again=await self.post('bind-start',data)
            self.assertEqual(first,again)
            status,_=await self.post('bind-start',{**data,'preset':'quick'})
            self.assertEqual(status,400)
            status,_=await self.post('bind-cancel',{'request_id':'wrong'})
            self.assertEqual(status,400)
            await asyncio.to_thread(started.wait,1)
            _,cancel=await self.post('bind-cancel',{'request_id':data['request_id']})
            for _ in range(100):
                result=await (await self.client.get(self.path+'/bind-status')).json()
                if result['status']!='running':break
                await asyncio.sleep(.01)
            self.assertEqual(result['status'],'cancelled')
            self.assertEqual(self.service.get(self.run['id']),self.run)
            self.assertEqual(worker.call_count,1)

    async def test_stale_revision_cannot_start_a_worker(self):
        self.service.edit(self.run['id'],self.run['revision'],'select',joint='knee.L')
        with patch.object(runtime,'bind') as worker:
            status,result=await self.post('bind-start',{'revision':0,'request_id':'dead'*8})
            self.assertEqual(status,409,result)
            worker.assert_not_called()

    async def test_stop_and_resume_reject_a_late_worker_at_attachment(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def bind(service, run_id, revision, request_id, preset, custom, cancelled, *, context):
            started.set()
            self.assertTrue(release.wait(4))
            return runtime.attach_output(service,self.run,{"file":"rig.glb"},request_id,context=context)
        with patch.object(runtime,"bind",side_effect=bind):
            status,result=await self.post("bind-start",{"revision":0,"request_id":"b"*32},agent=True)
            self.assertEqual(status,200,result)
            self.assertTrue(await asyncio.to_thread(started.wait,2))
            data={"id":self.run["id"],"browser":self.browser}
            stop=await self.client.post(self.live+"/control",json={**data,"action":"stop"})
            self.assertFalse((await stop.json())["enabled"])
            offer=await self.client.post(self.live+"/control",json={**data,"action":"prepare_resume"})
            capability=(await offer.json())["capability"]
            resume=await self.client.post(self.live+"/control",json={**data,"action":"resume","capability":capability})
            self.assertTrue((await resume.json())["enabled"])
            release.set()
            for _ in range(100):
                job=await (await self.client.get(self.path+"/bind-status")).json()
                if job["status"]!="running":
                    break
                await asyncio.sleep(.01)
            self.assertEqual(job["status"],"cancelled")
            self.assertEqual(self.service.get(self.run["id"]),self.run)

    async def test_shared_edit_route_returns_saved_state_and_rejects_stale_edits(self):
        payload = {"rig_revision":0, "request_id":"face"*8, "action":"orient",
                   "args":{"bone_id":"elbow.L","roll":.5}}
        status, result = await self.post("command", payload)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["command"]["changed_ids"], ["elbow.L"])
        self.assertEqual(result["rig_revision"], 1)
        status, replay = await self.post("command", payload)
        self.assertEqual(status, 200, replay)
        self.assertEqual(replay["command"], result["command"])
        status, _ = await self.post("command", {**payload, "request_id":"dead"*8})
        self.assertEqual(status, 409)
        saved = self.service.get(self.run["id"])
        self.assertEqual(next(b["roll"] for b in saved["skeleton"]["bones"] if b["id"]=="elbow.L"), .5)

    async def test_other_foundry_work_prevents_a_competing_bind(self):
        previous=self.fixture.library.busy
        self.fixture.library.busy=lambda:True
        self.addCleanup(setattr,self.fixture.library,'busy',previous)
        with patch.object(runtime,'bind') as worker:
            status,result=await self.post('bind-start',{'revision':0,'request_id':'baad'*8})
            self.assertEqual(status,400,result)
            worker.assert_not_called()

    async def test_live_pointer_lease_protects_both_edit_routes_until_commit(self):
        live = routes.PREFIX+"/live"
        browser, drag = "a"*32, "b"*32
        await self.client.post(live, json={"browser":browser,"id":self.run["id"],"opened":True})
        response = await self.client.post(live+"/drag", json={"browser":browser,"id":self.run["id"],
            "drag":drag,"joint":"elbow.L","rig_revision":0})
        self.assertEqual(response.status, 200)
        edit = {"action":"move","rig_revision":0,"request_id":"c"*32,"args":{"joint":"elbow.L","point":[.3,1,0]}}
        status, _ = await self.post("command", edit, agent=True)
        self.assertEqual(status,409)
        status, _ = await self.post("edit", {"action":"move","revision":0,"joint":"elbow.L","point":[.4,1,0]})
        self.assertEqual(status,409)
        status, updated = await self.post("command", {**edit,"browser":browser,"drag":drag})
        self.assertEqual(status,200)
        self.assertEqual(updated["joints"]["elbow.L"],[.3,1,0])
        status, _ = await self.post("command", {**edit,"request_id":"d"*32,"rig_revision":1}, agent=True)
        self.assertEqual(status,200)

    async def test_capture_pairs_image_with_verified_server_and_camera_state(self):
        import base64
        live = routes.PREFIX+"/live"
        browser = "a"*32
        await self.client.post(live, json={"browser":browser,"id":self.run["id"],"opened":True})
        waiting = asyncio.create_task(self.client.post(live+"/capture", json={"view":"oblique","format":"json"}))
        _, event = await asyncio.wait_for(self.events.get(), 1)
        self.assertEqual(event["view"],"oblique")
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jr9sAAAAASUVORK5CYII="
        matrix = [1 if i%5==0 else 0 for i in range(16)]
        result = await self.client.post(live+"/capture-result", json={
            "browser":browser, "token":event["token"], "revision":0,"png":png,
            "camera":{"world":matrix,"projection":matrix,"source_world":matrix,"revision":5,"type":"orthographic"},
            "visible_joints":["elbow.L"],
        })
        self.assertEqual(await result.json(),{"accepted":True})
        capture = await (await waiting).json()
        self.assertEqual(base64.b64decode(capture["png"]),base64.b64decode(png))
        self.assertEqual(capture["metadata"]["source_sha256"],self.run["source"]["sha256"])
        self.assertEqual(capture["metadata"]["camera"]["revision"],5)
        self.assertEqual(capture["metadata"]["visible_joints"],["elbow.L"])


if __name__=='__main__':
    unittest.main()
