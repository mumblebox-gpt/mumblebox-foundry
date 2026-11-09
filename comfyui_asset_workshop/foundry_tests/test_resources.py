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

    def test_sorting_is_global_before_pagination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested = root / "models"
            nested.mkdir()
            (root / "Zulu.gguf").write_bytes(b"large")
            (root / "alpha.gguf").write_bytes(b"a")
            (nested / "Beta.gguf").write_bytes(b"abc")
            inventory = self.inventory(root)
            self.assertEqual(inventory.list(limit=1, sort="name_asc")["items"][0]["name"], "alpha.gguf")
            self.assertEqual(inventory.list(limit=1, sort="name_desc")["items"][0]["name"], "Zulu.gguf")
            self.assertEqual(inventory.list(limit=1, sort="size_asc")["items"][0]["name"], "alpha.gguf")
            first = inventory.list(limit=1, sort="size_desc")
            self.assertEqual(first["items"][0]["name"], "Zulu.gguf")
            self.assertEqual(inventory.list(cursor=first["next_cursor"], limit=1, sort="size_desc")["items"][0]["name"], "Beta.gguf")
            with self.assertRaises(ValueError):
                inventory.list(sort="bad")

    def test_date_added_sort_keeps_unknown_dates_last_in_either_direction(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp:
            inventory = self.inventory(temp)
            rows = [dict(name=name, id=name, location="Models", relative_path=name, added_at=added)
                    for name, added in (("unknown.gguf", None), ("new.gguf", 200), ("old.gguf", 100))]
            with patch.object(inventory, "_scan", side_effect=lambda: {"items": list(rows), "truncated": False}):
                self.assertEqual([i["name"] for i in inventory.list(sort="date_asc")["items"]],
                                 ["old.gguf", "new.gguf", "unknown.gguf"])
                self.assertEqual([i["name"] for i in inventory.list(sort="date_desc")["items"]],
                                 ["new.gguf", "old.gguf", "unknown.gguf"])

    def test_windows_date_added_is_creation_time(self):
        import os
        if os.name != "nt":
            self.skipTest("Windows creation time")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "weights.gguf"
            path.write_bytes(b"model")
            os.utime(path, (978307200, 978307200))
            date_added = self.inventory(temp).list()["items"][0].get("added_at")
            self.assertEqual(date_added, os.path.getctime(path))
            self.assertNotEqual(date_added, path.stat().st_mtime)

if __name__=='__main__':unittest.main()
