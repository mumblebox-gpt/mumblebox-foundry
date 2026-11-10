import sys,unittest,tempfile,asyncio,types,importlib,json,zipfile,threading,hashlib
from unittest.mock import patch
from PIL import Image
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.workflows.splat_solid.definition import validate,DEFAULTS
from foundry.workflows.splat_solid.graph import compile_stage,ROLES

class SplatContracts(unittest.TestCase):
    def record(self,**changes):return dict(id='a'*32,source_sha256='b'*64,config=validate({'image':'reference.png',**changes}),artifacts={'raw':{'relative':'raw.glb'},'refined':{'relative':'refined.glb'}})
    def test_defaults_are_proven_and_bounded(self):
        c=self.record()['config'];self.assertEqual((c['master_resolution'],c['master_smoothing'],c['master_band']),(384,3,1.))
        for data in [{'steps':0},{'image':'../secret.png'},{'cpu_offload':'yes'},{'outputs':{'fake':True}}]:
            with self.assertRaises(ValueError):self.record(**data)
        self.assertEqual(DEFAULTS['image'],'')
    def test_idol_turbo_uses_both_experts_in_one_euler_schedule(self):
        standard = compile_stage(self.record(), 'generation')
        self.assertEqual(sum(n['class_type'] == 'KSampler' for n in standard.values()), 1)
        turbo = compile_stage(self.record(generation_mode='turbo'), 'generation')
        phases = sorted((n['inputs'] for n in turbo.values() if n['class_type'] == 'KSamplerAdvanced'),
                        key=lambda p: p['start_at_step'])
        self.assertEqual([(p['start_at_step'], p['end_at_step'], p['add_noise'],
                           p['return_with_leftover_noise']) for p in phases],
                         [(0, 4, 'enable', 'enable'), (4, 5, 'disable', 'disable')])
        for phase, expert in zip(phases, ('slow', 'fast')):
            self.assertEqual((phase['steps'], phase['cfg'], phase['sampler_name'], phase['scheduler']),
                             (5, 1.0, 'euler', 'simple'))
            lora = turbo[phase['model'][0]]
            self.assertEqual(lora['class_type'], 'LoraLoaderModelOnly')
            self.assertEqual(lora['inputs']['lora_name'], f'idol_turbo_{expert}_comfy.safetensors')
            self.assertEqual(lora['inputs']['strength_model'], 1.0)
        self.assertIs(turbo[phases[1]['latent_image'][0]]['inputs'], phases[0])
        for node in turbo.values():
            for value in node['inputs'].values():
                if isinstance(value, list):
                    self.assertIn(value[0], turbo)
        with self.assertRaisesRegex(ValueError, 'generation mode'):
            self.record(generation_mode='unknown')

    def test_saved_standard_signature_survives_the_new_mode(self):
        from foundry.workflows.splat_solid.runs import SplatRuns, signature
        record = self.record()
        config = record['config']
        legacy_keys = ('image', 'seed', 'steps', 'cfg', 'image_size', 'gaussians',
                       'decoder_seed', 'mesh_resolution', 'orbit_size', 'orbit_frames', 'orbit_fps')
        legacy_signature = signature([record['source_sha256'],
                                      {key: config[key] for key in legacy_keys}, config['outputs']['orbit']])
        self.assertEqual(SplatRuns.fingerprint(None, record, 'generation'), legacy_signature)
        config['generation_mode'] = 'turbo'
        turbo = SplatRuns.fingerprint(None, record, 'generation')
        self.assertNotEqual(turbo, legacy_signature)
        config.update(steps=42, cfg=5)
        self.assertEqual(SplatRuns.fingerprint(None, record, 'generation'), turbo)

    def test_cleanup_has_no_generator_or_foreign_graph_dependency(self):
        g=compile_stage(self.record(),'cleanup')
        self.assertFalse(any(n['class_type'] in ('KSampler','Hi3DRefine') for n in g.values()))
        for n in g.values():
            for v in n['inputs'].values():
                if isinstance(v,list):self.assertIn(v[0],g)
    def test_full_graph_self_contained_and_supports_no_refiner(self):
        for refine in [True,False]:
            g=compile_stage(self.record(refine=refine),'generation',full=True)
            for n in g.values():
                for v in n['inputs'].values():
                    if isinstance(v,list):self.assertIn(v[0],g)
            self.assertEqual(any(n['class_type']=='Hi3DRefine' for n in g.values()),refine)
            self.assertIn(ROLES['splat'],g);self.assertIn(ROLES['companion'],g)
    def test_stage_paths_are_owned_and_user_name_not_a_path(self):
        g=compile_stage(self.record(name='../../harmless title'),'generation')
        for n in g.values():
            if 'filename_prefix' in n['inputs']:self.assertTrue(n['inputs']['filename_prefix'].startswith('foundry-splat/'+'a'*32+'/'))

class SplatRunTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from foundry.workflows.splat_solid.runs import SplatRuns
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.input=self.root/'input';self.input.mkdir()
        Image.new('RGB',(16,16),'blue').save(self.input/'reference.png')
        class Native:
            def active_ids(self):return set()
            def history(self,ident):return None
            def cancel(self,ident):pass
        class Lifecycle:
            async def barrier(self):pass
            async def release(self,reason):return {'released':True}
        self.service=SplatRuns(self.root/'state',self.input,self.root/'output',Native(),lambda:Lifecycle(),lambda:False,None)
        async def no_inference(record):raise InterruptedError('Fixture cancels before inference.')
        self.service.prepare=no_inference
    async def asyncTearDown(self):
        if self.service.tasks:await asyncio.gather(*self.service.tasks.values(),return_exceptions=True)
        self.temp.cleanup()
    async def test_request_retry_is_idempotent_and_cancel_releases_owner(self):
        r=self.service.create({'image':'reference.png'});ident=r['id']
        self.service.start(ident,{'operation':'rocket','request_id':'retry'})
        self.service.start(ident,{'operation':'rocket','request_id':'retry'})
        self.assertEqual(len(self.service.tasks),1)
        with self.assertRaises(ValueError):self.service.start(ident,{'operation':'cleanup','request_id':'retry'})
        await asyncio.gather(*self.service.tasks.values())
        self.assertFalse(self.service.tasks);self.assertEqual(self.service.get(ident)['status'],'cancelled')
    async def test_upstream_settings_invalidate_downstream_but_export_choices_do_not(self):
        r=self.service.get(self.service.create({'image':'reference.png'})['id'])
        r['completed']['generation']={'signature':self.service.fingerprint(r,'generation'),'roles':['raw']}
        (self.root/'output').mkdir();(self.root/'output/raw.glb').write_bytes(b'fixture')
        r['artifacts']['raw']={'relative':'raw.glb'}
        self.assertTrue(self.service.fresh(r,'generation'))
        self.service.update(r['id'],{**r['config'],'outputs':{**r['config']['outputs'],'raw':True}})
        self.assertTrue(self.service.fresh(r,'generation'))
        self.service.update(r['id'],{**r['config'],'seed':10})
        self.assertFalse(self.service.fresh(r,'generation'))
        with self.assertRaises(ValueError):self.service.file(r['id'],'../private')
    async def test_restart_preserves_completed_artifacts_without_replaying_inference(self):
        r=self.service.get(self.service.create({'image':'reference.png'})['id']);r.update(status='running',artifacts={'raw':{'relative':'saved.glb'}});self.service.save(r)
        self.service.records.clear();recovered=self.service.get(r['id'])
        self.assertEqual(recovered['status'],'interrupted');self.assertEqual(recovered['artifacts']['raw']['relative'],'saved.glb');self.assertFalse(self.service.tasks)
    async def test_cancel_targets_only_this_runs_first_use_download(self):
        r=self.service.create({'image':'reference.png'})
        with patch('foundry.workflows.image_to_3d.readiness.cancel_download') as cancel:
            self.service.cancel(r['id']);cancel.assert_called_once_with(r['id'])
        self.assertTrue(self.service.get(r['id'])['cancel'])

class SplatPackageTests(unittest.TestCase):
    def test_selection_catalog_notices_and_history_are_real(self):
        root=Path(__file__).resolve().parents[1];pack=types.ModuleType('comfyui_asset_workshop');pack.__path__=[str(root)]
        with patch.dict(sys.modules,{'comfyui_asset_workshop':pack}):
            module=importlib.import_module('comfyui_asset_workshop.foundry.workflows.splat_solid.package')
            with tempfile.TemporaryDirectory() as temp:
                output=Path(temp);(output/'splat.spz').write_bytes(b'fixture')
                service=types.SimpleNamespace(output_root=output,check=lambda r:None,artifact_path=lambda r,k:output/r['artifacts'][k]['relative'],library=types.SimpleNamespace(import_package=lambda p:{'id':'history'}))
                r=dict(id='a'*32,config=validate({'image':'reference.png','outputs':dict(splat=True,raw=False,master=False,companion=False,presentation=False,orbit=False,previews=False,zip=True)}),source_sha256='b'*64,artifacts={'splat':{'relative':'splat.spz'}},completed={'generation':{'signature':'test'}})
                result=module.build(service,r)
                with zipfile.ZipFile(output/result['path']) as z:
                    self.assertIn('Splat/splat.spz',z.namelist());self.assertNotIn('Clean_Master/master.glb',z.namelist())
                    self.assertIn('Licenses/DINOv3-LICENSE.md',z.namelist());self.assertIn('Licenses/Idol-model-card.md',z.namelist())
                    doc=z.read('README.md').decode();self.assertIn('Idol',doc);self.assertNotIn('### Clean_Master/',doc)
                    self.assertEqual(json.loads(z.read('Metadata/manifest.json'))['production']['workflow_title'],'Splat & Solid · Idol')
                r['config']['outputs']['master']=True
                with self.assertRaisesRegex(ValueError,'Selected output is missing'):module.build(service,r)

class MissingModelRecoveryTests(unittest.TestCase):
    def test_deleted_model_is_restored_even_with_a_previous_verification_receipt(self):
        from foundry.resources import ResourceInventory
        root=Path(__file__).resolve().parents[1];pack=types.ModuleType('comfyui_asset_workshop');pack.__path__=[str(root)]
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);weight=folder/'model.safetensors';payload=b'fixture model';weight.write_bytes(payload);downloads=[]
            model=dict(name=weight.name,category='vae',size=len(payload),sha256=hashlib.sha256(payload).hexdigest())
            def download(m):downloads.append(m['name']);weight.write_bytes(payload)
            models=types.ModuleType('comfyui_asset_workshop.models');models.MODELS={'fixture':model};models.DOWNLOAD_LOCK=threading.Lock();models.DOWNLOAD={};models.download_one=download
            paths=types.SimpleNamespace(get_full_path=lambda category,name:str(weight) if weight.exists() else None)
            with patch.dict(sys.modules,{'comfyui_asset_workshop':pack,'comfyui_asset_workshop.models':models,'folder_paths':paths}):
                module=importlib.import_module('comfyui_asset_workshop.foundry.workflows.image_to_3d.readiness')
                with patch.dict(module.MODELS,{'fixture':('fixture',)}):
                    module.ensure('fixture',folder/'state')
                    inventory=ResourceInventory(folder,lambda:False);item=inventory.list()['items'][0];inventory.remove(inventory.preview(item['id'])['token'])
                    self.assertFalse(weight.exists());module.ensure('fixture',folder/'state')
                    self.assertEqual(downloads,[weight.name]);self.assertEqual(weight.read_bytes(),payload)

if __name__=='__main__':unittest.main()
