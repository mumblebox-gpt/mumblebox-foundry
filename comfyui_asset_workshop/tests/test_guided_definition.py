"""Product contract for the independent measured-view method."""
import importlib.util
import sys
import types
import unittest
import asyncio
import copy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACKAGE='_guided_contract'
package=types.ModuleType(PACKAGE);package.__path__=[str(ROOT/'foundry/workflows/guided_mesh')]
sys.modules[PACKAGE]=package

class GuidedDefinitionTests(unittest.TestCase):
    def module(self,name):
        import importlib
        return importlib.import_module(PACKAGE+'.'+name)

    def test_objects_only_and_no_inherited_chest_prompt(self):
        d=self.module('definition')
        spec=d.initial_spec()
        self.assertEqual(spec['category'],'props')
        self.assertEqual(spec['asset_description'],'')
        self.assertEqual(spec['special_instructions'],'')
        self.assertEqual(spec['selected_view_ids'],['front','right','back','left'])
        self.assertEqual(spec['camera_convention'],'canonical_anchor')

    def test_selection_never_changes_camera_identity(self):
        d=self.module('definition')
        spec=d.resolve_spec({'asset_description':'A standalone box','selected_view_ids':['back','front'],'elevation_deg':0},'reference.png','')
        views=self.module('fvb.contracts').selected_views(spec)
        self.assertEqual([v['id'] for v in views],['front','back'])
        self.assertEqual([v['azimuth_deg'] for v in views],[0,180])
        self.assertEqual([v['elevation_deg'] for v in views],[0,0])
        with self.assertRaises(ValueError):d.resolve_spec({'include_top':True},'reference.png','')

    def test_native_recipe_has_independent_node_namespace(self):
        d=self.module('definition');r=self.module('fvb.recipes')
        graph=r.canonical_api(d.initial_spec())
        self.assertTrue(any(n['class_type']=='G3D_PixalViews' for n in graph.values()))
        self.assertFalse(any(n['class_type'].startswith('FVB_') for n in graph.values()))
        self.assertIn('WeldVertices',{n['class_type'] for n in graph.values()})
        self.assertIn('FillHoles',{n['class_type'] for n in graph.values()})

    def test_source_branch_is_pinned_and_portable(self):
        d=self.module('definition')
        self.assertEqual(d.METHOD_ID,'3d-guided/v1')
        self.assertEqual(d.GRAPH_OFFSET,100000)
        self.assertNotIn('C:\\Dev',d.initial_spec()['workflow_path'])

    def test_guided_export_policy_disables_quads(self):
        d=self.module('definition')
        self.assertFalse(d.QUAD_RETOPOLOGY_ENABLED)
        self.assertEqual(set(d.export_variants()),{'detailed','game_balanced','game_compact','print'})

    def test_guided_queue_retains_but_disables_quad_nodes(self):
        import ast
        tree=ast.parse((ROOT/'foundry/workflows/guided_mesh/finishing.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='NativeFinishingQueue')
        method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='submit')
        namespace={'__package__':PACKAGE,'copy':copy,'QUAD_RETOPOLOGY_ENABLED':False}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<guided queue>','exec'),namespace)
        seen=[]
        async def bind(graph,client):seen.append(copy.deepcopy(graph))
        async def submit(graph,ident,client):seen.append(graph)
        owner=types.SimpleNamespace(bind=bind,native=types.SimpleNamespace(submit=submit))
        graph={'3001':{'class_type':'Hi3DQuadFinish','inputs':{'enabled':True}}}
        asyncio.run(namespace['submit'](owner,graph,'run','client'))
        self.assertFalse(seen[0]['3001']['inputs']['enabled'])
        self.assertFalse(seen[1]['203001']['inputs']['enabled'])
        self.assertTrue(graph['3001']['inputs']['enabled'],'Do not mutate the shared Turnaround template')

    def test_concept_editor_binds_every_required_encoder_port(self):
        editor=self.module('editor');d=self.module('definition')
        graph=editor.graph({'id':'a'*32,'spec':d.initial_spec(),
            'concept_editor':{'prompt':'Keep the dark iron','seed':42,'steps':40}})
        encoder=self.module('fvb.sheet_nodes').SHEET_NODES['G3D_QwenSheetEncode']
        self.assertFalse(set(encoder.INPUT_TYPES()['required'])-graph['10']['inputs'].keys())

    def run_continuation_policy(self,guided):
        job={'id':'a'*32,'spec':{**self.module('definition').initial_spec(),'guided':guided},'completed':{},'status':'ready','cancelled':False}
        class Journal:
            def read(self,ident):return copy.deepcopy(job)
            def update(self,ident,**values):job.update(values);return self.read(ident)
            def event(self,*args):pass
            def reusable(self,*args):return False
            def publish(self,ident,stage,result,fingerprint):job['completed'][stage]=result
        called=[]
        async def execute(job,stage):called.append(stage);return {'requires_review':True}
        runner=self.module('fvb.runner').JobRunner(Journal(),execute)
        result=asyncio.run(runner.advance(job['id']))
        return result,called

    def test_rocket_never_pauses_at_optional_view_review(self):
        job,called=self.run_continuation_policy(False)
        self.assertEqual(job['status'],'complete')
        self.assertEqual(len(called),10)
        self.assertIn('split',called)
        self.assertEqual(called[-1],'texture')

    def test_manual_wizard_keeps_review_checkpoints(self):
        job,called=self.run_continuation_policy(True)
        self.assertEqual(job['status'],'awaiting_review')
        self.assertEqual(called,['concept'])

    def test_restart_rebinds_client_without_changing_inference_settings(self):
        d=self.module('definition');spec=d.initial_spec();spec['client_id']='old-client-connection'
        updated=d.reconnect_spec(spec,'new-client-connection','workflows/Foundry.json')
        self.assertEqual(updated['client_id'],'new-client-connection')
        self.assertEqual(updated['workflow_path'],'workflows/Foundry.json')
        self.assertEqual({k:v for k,v in updated.items() if k not in ('client_id','workflow_path')},
            {k:v for k,v in spec.items() if k not in ('client_id','workflow_path')})
        self.assertEqual(spec['client_id'],'old-client-connection')
        with self.assertRaises(ValueError):d.reconnect_spec(spec,'new-client-connection','../private.json')

    def test_concept_editor_preserves_a_wide_four_panel_canvas(self):
        from unittest.mock import patch
        editor=self.module('editor');seen={}
        native=types.ModuleType('comfy_extras.nodes_qwen')
        class Encoder:
            @classmethod
            def execute(cls,**options):
                seen.update(options)
                return ('positive','negative',{'samples':types.SimpleNamespace(shape=(1,16,64,256))})
        native.TextEncodeQwenImage21=Encoder
        canvas=types.SimpleNamespace(shape=(1,1024,4096,3))
        with patch.dict(sys.modules,{'comfy_extras':types.ModuleType('comfy_extras'),'comfy_extras.nodes_qwen':native}):
            result=editor.ConceptCanvasEncode().encode(None,None,'Edit the metal','',False,image_1=canvas,image_2=canvas,image_3=canvas)
        self.assertEqual(result[2]['samples'].shape[-2:],(64,256))
        self.assertIs(seen['images']['image_1'],canvas)
        self.assertEqual(seen['resolution'],0)

    def test_cancelling_finishing_preserves_completed_generation(self):
        routes=self.module('routes');handlers={};cancelled=[]
        job={'id':'a'*32,'status':'complete','export_run_id':'b'*32}
        class Routes:
            def route(self,path):
                def register(fn):handlers[path]=fn;return fn
                return register
            get=post=patch=route
        async def read(limit):return b'{"operation":"cancel"}'
        svc=types.SimpleNamespace(get=lambda ident:job,public=copy.deepcopy,
            engine=types.SimpleNamespace(runner=types.SimpleNamespace(cancel=lambda ident:job.update(status='cancelled'))),
            finisher=types.SimpleNamespace(cancel=cancelled.append))
        routes.register(Routes(),lambda:svc,lambda fn:fn)
        request=types.SimpleNamespace(match_info={'id':job['id']},content=types.SimpleNamespace(read=read))
        result=asyncio.run(handlers[routes.PREFIX+'/runs/{id}/action'](request))
        self.assertEqual(result['status'],'complete')
        self.assertEqual(cancelled,['b'*32])

    def test_resume_clears_cancel_before_resource_preparation(self):
        import ast
        tree=ast.parse((ROOT/'foundry/workflows/guided_mesh/runs.py').read_text(encoding='utf-8'))
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='GuidedRuns')
        start=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='start')
        namespace={'asyncio':asyncio,'busy':lambda:False,'time':types.SimpleNamespace(time=lambda:1234.5)}
        exec(compile(ast.Module(body=[start],type_ignores=[]),'<guided start>','exec'),namespace)
        job={'cancelled':True};seen=[]
        async def prepare(ident,operation):seen.append(job['cancelled'])
        svc=types.SimpleNamespace(other_busy=lambda:False,tasks={},get=lambda ident:job,
            public=copy.deepcopy,prepare_start=prepare,
            engine=types.SimpleNamespace(store=types.SimpleNamespace(update=lambda ident,**kw:job.update(kw))))
        async def run():
            namespace['start'](svc,'a'*32,'resume')
            await svc.tasks['a'*32]
        asyncio.run(run())
        self.assertEqual(seen,[False])
        self.assertEqual(job['started_at'],1234.5)

if __name__=='__main__':unittest.main()
