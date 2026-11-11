"""Single-image ancestry, input and finishing contracts (no model inference)."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.workflows.image_to_3d.definition import resolve_settings

class SingleImageMethod(unittest.TestCase):
    def recipe(self):
        from foundry.workflows.single_image import graph
        return graph
    def run_data(self):
        return dict(method='single-image',id='a'*32,slug='test',name='Test',references=[dict(filename='test.png',role='primary',description='')],
                    settings=resolve_settings('default',{}),checkpoints={'decoded':'raw.glb','clean':'clean.glb','front':'test.png','texture':'texture.glb'},selection={'variants':{'detailed':{'formats':['glb']}}})
    def test_geometry_is_official_single_image_not_multiview_or_texture(self):
        g=self.recipe().compile_stage('geometry',self.run_data())
        kinds={n['class_type'] for n in g.values()}
        self.assertIn('Pixal3DConditioning',kinds)
        self.assertNotIn('Pixal3DMultiViewConditioning',kinds)
        self.assertNotIn('Trellis2TextureStage',kinds)
        self.assertNotIn('TextEncodeQwenImage21',kinds)
        self.assertEqual(g['319']['inputs']['unet_name'],'pixal3d_bf16.safetensors')
        self.assertEqual(g['3']['inputs']['steps'],12)
        self.assertEqual(g['18']['inputs']['steps'],20)
        self.assertEqual(g['23']['inputs']['steps'],12)
        self.assertEqual(g['312']['inputs']['background'],'#000000')
        self.assertEqual(g['56']['inputs']['batch_size'],1)
        self.assertEqual(g['55']['inputs']['model_name'],'moge_2_vitl_normal_fp16.safetensors')
        self.assertEqual(g['119']['inputs']['resolution'],'32')
        self.assertEqual(g['242']['inputs']['axis'],'horizontal')
    def test_first_run_prepares_the_checkpoint_required_by_the_moge_loader(self):
        from foundry.workflows.image_to_3d.readiness import MODELS
        lock = Path(__file__).resolve().parents[1] / 'models.lock.json'
        catalog = json.loads(lock.read_text(encoding='utf-8'))['models']
        graph = self.recipe().compile_stage('geometry', self.run_data())
        requested = {node['inputs']['model_name'] for node in graph.values()
                     if node['class_type'] == 'LoadMoGeModel'}
        prepared = {catalog[key]['name'] for key in MODELS['single_geometry']
                    if catalog[key]['category'] == 'geometry_estimation'}
        self.assertEqual(prepared, requested)

    def test_refinement_and_texture_use_original_and_checkpoint_not_regeneration(self):
        for stage in ('refinement','texture'):
            g=self.recipe().compile_stage(stage,self.run_data())
            self.assertEqual(g['9101']['inputs']['image'],'test.png')
            self.assertNotIn('Pixal3DConditioning',{n['class_type'] for n in g.values()})
    def test_namespace_does_not_overlap_existing_methods(self):
        from foundry.workflows.single_image.definition import OFFSET
        self.assertGreaterEqual(OFFSET,500000)

    def test_one_reference_is_required(self):
        from foundry.workflows.single_image.definition import validate_references
        for refs in ([],[{'filename':'a.png'}]*2):
            with self.assertRaises(ValueError):validate_references(refs)
        validate_references([{'filename':'a.png','role':'primary','description':''}])
    def test_selected_dependencies_do_not_prepare_turnaround(self):
        from foundry.workflows.single_image.definition import required_stages
        self.assertEqual(required_stages('rocket',{'variants':{'print':{}}}),['single_geometry','refinement'])
        self.assertEqual(required_stages('finish',{'variants':{'detailed':{}}}),['texture'])
    def test_independent_canvas_has_no_old_conditioning_and_all_exports(self):
        g=self.recipe().canvas_recipe()
        self.assertIn('3001',g)
        self.assertIn('3010',g)
        self.assertNotIn('324',g)
        self.assertNotIn('1558',g)
        self.assertEqual(g['2022']['inputs']['image'],['122',0])

class GroundingPolicy(unittest.TestCase):
    def test_only_package_changes_when_floor_choice_changes(self):
        import tempfile
        from foundry.workflows.single_image.policy import fingerprint
        from foundry.workflows.single_image.definition import resolve_settings
        with tempfile.TemporaryDirectory() as d:
            Path(d,'test.png').write_bytes(b'unchanged reference')
            r=SingleImageMethod().run_data();r['settings']=resolve_settings('default',{})
            stages=('geometry','refinement','texture','compact','quads','package')
            before={k:fingerprint(r,k,Path(d)) for k in stages}
            r['settings']['export_grounding']='original'
            after={k:fingerprint(r,k,Path(d)) for k in stages}
            for k in stages:self.assertEqual(before[k]==after[k],k!='package')
    def test_package_plan_uses_saved_clean_and_canvas_has_own_node(self):
        from foundry.workflows.single_image.graph import compile_stage,canvas_recipe
        g=compile_stage('package',SingleImageMethod().run_data())
        self.assertEqual(g['3011']['inputs']['mesh'],['9100',0])
        self.assertEqual(g['3010']['inputs']['grounding_json'],['3011',0])
        self.assertEqual(canvas_recipe()['3011']['class_type'],'Hi3DGroundingFrame')

if __name__=='__main__':unittest.main()
