import tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pathlib import Path
from foundry.cache import CacheManager
class CacheTests(unittest.TestCase):
    def test_purge_is_scoped_and_changed_files_are_retained(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);scratch=root/'scratch';scratch.mkdir();(root/'model.safetensors').write_text('keep')
            a=scratch/'old.tmp';a.write_text('discard');b=scratch/'changed.tmp';b.write_text('before')
            owner=CacheManager([('Worker scratch',scratch,False)],lambda:False)
            preview=owner.preview();b.write_text('changed after preview')
            result=owner.purge(preview['token'])
            self.assertFalse(a.exists());self.assertTrue(b.exists());self.assertTrue((root/'model.safetensors').exists())
            self.assertEqual(result['removed'],1);self.assertEqual(result['skipped'],1)
    def test_busy_or_reused_token_never_deletes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'file.tmp';p.write_text('x');busy=[False]
            owner=CacheManager([('Temp',Path(d),False)],lambda:busy[0]);preview=owner.preview();busy[0]=True
            with self.assertRaises(ValueError):owner.purge(preview['token'])
            self.assertTrue(p.exists());busy[0]=False;owner.purge(preview['token'])
            with self.assertRaises(ValueError):owner.purge(preview['token'])
    def test_partial_download_scope_cannot_remove_installed_weights(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'hash.part').write_text('partial');(root/'model.safetensors').write_text('keep')
            owner=CacheManager([('Incomplete downloads',root,True)],lambda:False)
            preview=owner.preview();self.assertEqual(preview['count'],1);owner.purge(preview['token'])
            self.assertTrue((root/'model.safetensors').exists())

    def test_unselected_categories_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=root/'a';b=root/'b';a.mkdir();b.mkdir();(a/'scratch').write_text('x');(b/'partial.part').write_text('y')
            owner=CacheManager([('Scratch',a,False),('Downloads',b,True)],lambda:False);preview=owner.preview()
            owner.purge(preview['token'],['Downloads'])
            self.assertTrue((a/'scratch').exists());self.assertFalse((b/'partial.part').exists())
