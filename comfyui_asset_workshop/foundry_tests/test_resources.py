import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

class ResourcesTests(unittest.TestCase):
    def inventory(self, root, busy=lambda:False):
        from foundry.resources import ResourceInventory
        return ResourceInventory(root,busy)

    def test_lists_models_and_loras_separately_and_removes_only_confirmed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'loras').mkdir();(root/'diffusion_models').mkdir()
            a=root/'loras/a.safetensors';a.write_bytes(b'fixture')
            b=root/'diffusion_models/b.safetensors';b.write_bytes(b'preserve')
            inventory=self.inventory(root);items=inventory.list()['items']
            self.assertEqual({i['kind'] for i in items},{'lora','image_model'})
            item=next(i for i in items if i['kind']=='lora')
            preview=inventory.preview(item['id']);inventory.remove(preview['token'])
            self.assertFalse(a.exists());self.assertTrue(b.exists())
            with self.assertRaises(ValueError):inventory.remove(preview['token'])

    def test_busy_or_changed_file_refuses_deletion(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'loras').mkdir();p=root/'loras/a.safetensors';p.write_bytes(b'one')
            busy=[False];inventory=self.inventory(root,lambda:busy[0]);item=inventory.list()['items'][0]
            preview=inventory.preview(item['id']);p.write_bytes(b'changed')
            with self.assertRaises(ValueError):inventory.remove(preview['token'])
            busy[0]=True
            with self.assertRaises(ValueError):inventory.preview(item['id'])
            self.assertTrue(p.exists())

    def test_shared_file_is_explicitly_removable_without_deleting_other_links(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'loras').mkdir();p=root/'outside.safetensors';p.write_bytes(b'preserve')
            linked=root/'loras/shared.safetensors';os.link(p,linked)
            inventory=self.inventory(root);item=next(i for i in inventory.list()['items'] if i['name']=='shared.safetensors')
            self.assertTrue(item['deletable'])
            with self.assertRaises(ValueError):inventory.preview(str(p))
            preview=inventory.preview(item['id']);self.assertEqual(preview['shared_links'],2)
            inventory.remove(preview['token']);self.assertTrue(p.exists());self.assertFalse(linked.exists())

    def test_runtime_components_and_pagination(self):
        from foundry.resources import ResourceInventory
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'comfy';b=root/'worker';a.mkdir();b.mkdir()
            (a/'vae.safetensors').write_bytes(b'one');(b/'model.onnx').write_bytes(b'two')
            inventory=ResourceInventory(a,lambda:False,lambda:[dict(path=str(b),label='Hi3D',workflows=['Hi3D'])])
            first=inventory.list(limit=1);self.assertEqual(first['total'],2)
            second=inventory.list(first['next_cursor'],1);self.assertEqual(len(second['items']),1)
            item=next(i for i in inventory.list()['items'] if i['name']=='model.onnx')
            inventory.remove(inventory.preview(item['id'])['token']);self.assertFalse((b/'model.onnx').exists());self.assertTrue((a/'vae.safetensors').exists())

if __name__=='__main__':unittest.main()
