"""Hair workflow boundaries: supported controls, independent graph and immutable results."""
import sys
import unittest
import tempfile
import asyncio
import importlib
import json
import types
import zipfile
from unittest.mock import patch
from PIL import Image
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class HairContractTests(unittest.TestCase):
    def test_review_manifest_uses_actual_artifacts_with_english_labels(self):
        from foundry.workflows.hair_creation.review import displays
        files=[dict(filename=n,subfolder='saved') for n in ('preview_00001_.png','preprocess_00001_.png','uv_layout.png','cards.json')]
        result=displays(files)
        self.assertEqual([x['group'] for x in result],['result','input','material'])
        self.assertEqual(result[1]['label'],'HairDeck processing sheet')
        self.assertEqual(result[2]['path'],'saved/uv_layout.png')

    def test_card_color_interpolation_preserves_root_tip_and_caps(self):
        from foundry.workflows.hair_creation.appearance import color_rows
        import numpy as np
        colors=np.tile([[1.,0.,0.],[0.,0.,1.]],(8,1))
        surface=color_rows(colors,32,'surface')
        np.testing.assert_array_equal(surface[0],[0.,0.,1.])
        np.testing.assert_array_equal(surface[-1],[1.,0.,0.])
        np.testing.assert_array_equal(color_rows(colors,2,'root'),[[1.,0.,0.]]*2)
        np.testing.assert_array_equal(color_rows(colors,2,'tip'),[[0.,0.,1.]]*2)

    def test_hair_owner_exists_and_rejects_invalid_options(self):
        from foundry.workflows.hair_creation.definition import validate
        config = validate({'name': 'Copper hair', 'image': 'hair.png'})
        self.assertEqual((config['steps'], config['cfg'], config['variations']), (50, 2., 1))
        self.assertTrue(config['bones'])
        for change in ({'image': '../secret.png'}, {'seed': True}, {'cfg': float('nan')},
                       {'variations': 5}, {'bones': False, 'vrm': True}, {'scale': 0}, {'texture_size': '8K'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate({'image': 'hair.png', **change})

    def test_graph_uses_approved_reference_and_preserves_variant_identity(self):
        from foundry.workflows.hair_creation.definition import validate
        from foundry.workflows.hair_creation.graph import generate, export
        record = {'id': 'a'*32, 'config': validate({'image': 'hair.png'}), 'source_sha256': 'f'*64}
        graph = generate(record, 2)
        self.assertEqual(graph['70000']['inputs']['filename'], 'hair.png')
        self.assertEqual(graph['70002']['inputs']['seed'], 2)
        self.assertEqual(graph['70003']['inputs']['variant'], 2)
        saved = export(record, 'foundry-hair/'+'a'*32+'/variant-2/checkpoint.json')
        self.assertEqual(saved['70004']['inputs']['checkpoint'], 'foundry-hair/'+'a'*32+'/variant-2/checkpoint.json')
        self.assertNotIn('Hi3D', str(saved))


class HairRunTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from foundry.workflows.hair_creation.runs import HairRuns
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.input=self.root/'input';self.input.mkdir();Image.new('RGB',(16,16),'blue').save(self.input/'hair.png')
        class Native:
            def active_ids(self):return set()
            def cancel(self,ident):pass
        class Lifecycle:
            async def barrier(self):pass
            async def release(self,reason):return {'status':'released'}
        def prepare(*args):
            import time
            cancelled=args[1]
            for _ in range(20):
                if cancelled():raise InterruptedError('Cancelled before loading models.')
                time.sleep(.01)
            raise RuntimeError('Fixture stops before native model execution.')
        self.service=HairRuns(self.root/'state',self.input,self.root/'output',Native(),lambda:Lifecycle(),lambda:False,None,prepare)
    async def asyncTearDown(self):
        for task in list(self.service.tasks.values()):task.cancel()
        if self.service.tasks:await asyncio.gather(*self.service.tasks.values(),return_exceptions=True)
        self.temp.cleanup()

    async def test_export_options_preserve_matching_generations(self):
        created=self.service.create({'image':'hair.png'});record=self.service.get(created['id'])
        record['variants']=[{'checkpoint':'saved'}]
        config={**record['config'],'color':'#884422','uv_mode':'unique','scale':1.02}
        self.service.update(record['id'],config)
        self.assertEqual(record['variants'],[{'checkpoint':'saved'}])
        self.service.update(record['id'],{**config,'seed':3})
        self.assertEqual(record['variants'],[])

    async def test_adding_chains_and_more_variations_does_not_destroy_saved_cards(self):
        created=self.service.create({'image':'hair.png','bones':False,'vrm':False});record=self.service.get(created['id'])
        record['variants']=[{'checkpoint':'immutable-saved-cards'}]
        self.service.update(record['id'],{**record['config'],'bones':True,'variations':4})
        self.assertEqual(record['variants'][0]['checkpoint'],'immutable-saved-cards')
        from foundry.workflows.hair_creation.graph import rig
        prompt=rig(record,0)
        self.assertEqual(prompt['70005']['inputs']['checkpoint'],'immutable-saved-cards')
        self.assertNotIn('HairDeckGenerate',str(prompt))

    async def test_view_files_are_owned_but_unlisted_artifacts_are_denied(self):
        created=self.service.create({'image':'hair.png'});record=self.service.get(created['id'])
        self.service.output_root.mkdir();path=self.service.output_root/'hair-nohead.glb';path.write_bytes(b'glb')
        record['variants']=[{'views':{'hair':'hair-nohead.glb'}}]
        self.assertEqual(self.service.file(record['id'],'hair-nohead.glb'),path)
        with self.assertRaises(ValueError):self.service.file(record['id'],'not-owned.glb')

    async def test_appearance_change_invalidates_stale_media_but_preserves_cards(self):
        record=self.service.get(self.service.create({'image':'hair.png'})['id'])
        record['variants']=[{'checkpoint':'saved','reviews':{'preview':{'model':'old.glb'}}}]
        record['motion_preview']={'model':'old.mp4'}
        self.service.update(record['id'],{**record['config'],'color':'#AA2211'})
        self.assertEqual(record['variants'],[{'checkpoint':'saved'}])
        self.assertNotIn('motion_preview',record)

    async def test_avatar_and_motion_previews_prepare_blender_before_running(self):
        captured=[]
        self.service.prepare=lambda config,*args:captured.append(config.copy()) or {}
        record=self.service.get(self.service.create({'image':'hair.png','vrm':False,'motion':False})['id'])
        for operation in ('avatar_preview','motion_preview'):
            record['operation']=operation
            await self.service.prepare_resources(record)
            self.assertTrue(captured[-1]['vrm'])
        self.assertFalse(record['config']['vrm'])

    async def test_cancel_before_models_keeps_existing_results_and_releases_owner(self):
        record=self.service.create({'image':'hair.png'});ident=record['id']
        self.service.start(ident,{'request_id':'same','operation':'generate'})
        self.service.cancel(ident)
        await asyncio.gather(*list(self.service.tasks.values()))
        result=self.service.get(ident)
        self.assertEqual(result['status'],'cancelled');self.assertFalse(self.service.tasks)
        self.assertEqual(result['cleanup']['status'],'released')

    async def test_retry_identity_and_cross_operation_guard(self):
        record=self.service.create({'image':'hair.png'});ident=record['id']
        self.service.start(ident,{'request_id':'same','operation':'generate'})
        self.service.start(ident,{'request_id':'same','operation':'generate'})
        self.assertEqual(len(self.service.tasks),1)
        with self.assertRaisesRegex(ValueError,'another operation'):
            self.service.start(ident,{'request_id':'same','operation':'export'})
        self.service.cancel(ident);await asyncio.gather(*list(self.service.tasks.values()))

    async def test_changed_source_and_unowned_files_are_denied(self):
        record=self.service.create({'image':'hair.png'});ident=record['id']
        with self.assertRaises(ValueError):self.service.file(ident,'../private.txt')
        Image.new('RGB',(16,16),'red').save(self.input/'hair.png')
        with self.assertRaisesRegex(ValueError,'reference changed'):
            self.service.start(ident,{'request_id':'same','operation':'generate'})

class HairPackageTests(unittest.TestCase):
    def test_unselected_outputs_are_absent_from_archive_and_readme(self):
        # Exercise the real catalog/ZIP owner without rerunning neural inference.
        root=Path(__file__).resolve().parents[1]
        package=types.ModuleType('comfyui_asset_workshop');package.__path__=[str(root)]
        with patch.dict(sys.modules,{'comfyui_asset_workshop':package}):
            module=importlib.import_module('comfyui_asset_workshop.foundry.workflows.hair_creation.package')
            from foundry.workflows.hair_creation.definition import validate
            with tempfile.TemporaryDirectory() as temp:
                output=Path(temp).resolve();source=output/'saved';source.mkdir();native=output/'native';native.mkdir()
                for name in ('LICENSE','THIRD_PARTY_NOTICES.md','_vendor/hairdeck_sam3/LICENSE',
                             '_vendor/hairdeck_dinov3/LICENSE.md','_vendor/hairdeck_birefnet/LICENSE',
                             '_vendor/hairdeck_pyrender/LICENSE'):
                    p=native/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Fixture notice',encoding='utf-8')
                entries=[]
                for name in ('hair.glb','avatar.vrm','motion.mp4','preview.png','cards.json','textures/base_color.png'):
                    p=source/name;p.parent.mkdir(exist_ok=True);p.write_bytes(b'fixture')
                    entries.append({'filename':p.name,'subfolder':p.parent.relative_to(output).as_posix()})
                service=types.SimpleNamespace(output_root=output,check=lambda record:None,
                    library=types.SimpleNamespace(import_package=lambda path:{'id':'fixture-history'}))
                for static in (True,False):
                    config=validate({'image':'hair.png','glb':static,'vrm':not static,'motion':False,
                                     'diagnostics':False,'source_data':False})
                    record={'config':config,'source_sha256':'f'*64,'selected':0,'export':{
                        'files':entries,'measurements':{'seed':0,'generated_chains':2,'geometry':{'vertices':12,'triangles':8}}}}
                    with patch.object(module,'upstream',return_value=types.SimpleNamespace(__file__=str(native/'nodes.py'))):
                        result=module.build(service,record)
                    with zipfile.ZipFile(output/result['path']) as archive:
                        names=archive.namelist();manifest=json.loads(archive.read('Metadata/manifest.json'))
                        self.assertEqual(any(n.startswith('Static/') for n in names),static)
                        self.assertEqual(any(n.startswith('Rigged/') for n in names),not static)
                        self.assertFalse(any(n.startswith(('Motion/','Diagnostics/','Source/')) for n in names))
                        self.assertIn('Metadata/preview.png',names)
                        self.assertEqual({v['id'] for v in manifest['variants']},{'static' if static else 'rigged','textures'})
                        doc=archive.read('README.md').decode('utf-8')
                        self.assertNotIn('### Motion/',doc);self.assertNotIn('### Source/',doc)


if __name__ == '__main__': unittest.main()
