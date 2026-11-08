import asyncio
import copy
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.workflows.image_creation.library import ImageLibrary
from foundry.workflows.image_creation.runs import ImageRuns

class Native:
    def __init__(self,library):self.library=library;self.calls=[];self.results={};self.fail_back=False
    def active_ids(self):return set()
    def history(self,ident):return self.results.get(ident)
    async def submit(self,graph,ident,client):
        assert ident==str(uuid.UUID(ident)), 'Comfy requires canonical prompt UUIDs'
        self.calls.append(graph)
        if self.fail_back and graph['side']=='back':raise ValueError('back failed')
        record=self.library.get(graph['id']);path=self.library.directory(record['id'])/(ident+'.png')
        Image.new('RGB',(16,16),'blue').save(path)
        self.results[ident]={'status':{'status_str':'success'},'outputs':{'out':{'images':[{
            'filename':path.name,'subfolder':f"foundry-images/{record['id']}",'type':'output'}]}}}
        return ident
    async def wait(self,ident,*args):return self.results[ident]
    def cancel(self,ident):pass

class ImageRunTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);self.input=root/'input';self.input.mkdir()
        self.library=ImageLibrary(root/'state',root/'output');self.native=Native(self.library);self.released=[]
        outer=self
        class Lifecycle:
            async def barrier(self):pass
            async def release(self,reason):outer.released.append(reason);return {'status':'released'}
        def compiler(record,side,seed,refs,attempt,edit=None):
            return {'graph':{'id':record['id'],'side':side,'references':copy.deepcopy(refs)},'output_node':'out',
                    'provenance':{'seed':seed},'bindings':[]}
        self.service=ImageRuns(self.library,self.input,self.native,lambda:Lifecycle(),lambda:False,
                              prepare=lambda *args:None,compiler=compiler)
    async def asyncTearDown(self):
        for task in self.service.tasks.values():task.cancel()
        self.temp.cleanup()
    def create(self,**changes):return self.service.create({'name':'Explorer','description':'A blue explorer',**changes})
    async def run_job(self,ident,request='request-one'):
        result=self.service.start(ident,{'request_id':request});await self.service.tasks[ident];return self.service.get(ident)
    async def test_pair_front_is_conditioning_for_back_and_duplicate_is_idle(self):
        creation=self.create();run=await self.run_job(creation['id'])
        self.assertEqual(run['status'],'complete');self.assertEqual(len(self.native.calls),2)
        self.assertEqual(self.native.calls[1]['references'][0]['role'],'front of this exact subject')
        self.assertTrue(self.native.calls[1]['references'][0]['filename'].endswith(' [output]'))
        self.service.start(creation['id'],{'request_id':'request-one'})
        self.assertFalse(self.service.tasks);self.assertTrue(self.released)
    async def test_retry_keeps_front_after_back_failure(self):
        creation=self.create();self.native.fail_back=True
        failed=await self.run_job(creation['id']);front=failed['accepted']['front']
        self.assertEqual(failed['status'],'failed');self.assertNotIn('back',failed['accepted'])
        self.native.fail_back=False;result=await self.run_job(creation['id'],'retry-back')
        self.assertEqual(result['accepted']['front'],front)
        self.assertEqual([c['side'] for c in self.native.calls],['front','back','back'])
    async def test_single_never_generates_back_or_hands_off(self):
        creation=self.create(category='general');run=await self.run_job(creation['id'])
        self.assertEqual(list(run['accepted']),['single'])
        with self.assertRaisesRegex(ValueError,'standalone'):self.service.handoff(creation['id'])
    async def test_single_image_handoff_copies_one_reference_and_binds_lineage(self):
        creation=self.create(category='general');await self.run_job(creation['id'])
        handoff=self.service.handoff(creation['id'],single=True)
        self.assertEqual(len(handoff['references']),1)
        self.assertEqual(handoff['references'][0]['id'],'single')
        from foundry.workflows.image_creation.lineage import resolve_handoff
        from foundry.artifacts import digest
        refs=[{**r,'sha256':digest(self.input/r['filename'])} for r in handoff['references']]
        self.assertEqual(resolve_handoff(self.library.state_root,handoff['image_creation'],refs)['images'][0]['side'],'single')

    async def test_handoff_copies_pair_and_retains_roles(self):
        creation=self.create();run=await self.run_job(creation['id']);handoff=self.service.handoff(creation['id'])
        self.assertEqual([r['role'] for r in handoff['references']],['primary','back'])
        for ref in handoff['references']:self.assertTrue((self.input/ref['filename']).is_file())
        from foundry.workflows.image_creation.lineage import resolve_handoff
        from foundry.artifacts import digest
        refs=[{**r,'sha256':digest(self.input/r['filename'])} for r in handoff['references']]
        lineage=resolve_handoff(self.library.state_root,handoff['image_creation'],refs)
        self.assertEqual(lineage['id'],creation['id']);self.assertEqual(len(lineage['images']),2)
        removal=self.library.preview_removal([creation['id']],True);self.library.remove(removal['token'])
        self.assertEqual(resolve_handoff(self.library.state_root,handoff['image_creation'],refs),lineage)
        for ref in refs:self.assertTrue((self.input/ref['filename']).exists())
    async def test_other_workflow_activity_prevents_parallel_gpu_job(self):
        creation=self.create();self.service.other_busy=lambda:True
        with self.assertRaisesRegex(ValueError,'running'):self.service.start(creation['id'],{'request_id':'busy'})
        self.assertFalse(self.native.calls)

if __name__=='__main__':unittest.main()
