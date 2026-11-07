"""The software probe must cover generation's lazy DINO hub imports."""
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class HairProbeTests(unittest.TestCase):
    def run_probe(self, backbone_error=None, renderer_error=None):
        with tempfile.TemporaryDirectory() as folder:
            core = Path(folder)
            pack = core / 'pack'
            pack.mkdir()
            (pack / '__init__.py').write_text('''
class Node:
    def __init__(self, name): self.name = name
    def define_schema(self): return type('Schema', (), {'node_id': self.name})()
class Extension:
    async def get_node_list(self):
        return [Node(n) for n in ('HairDeckLoader', 'HairDeckGenerate', 'HairDeckSave')]
async def comfy_entrypoint(): return Extension()
''', encoding='utf-8')
            hub = Mock()
            hub.load.side_effect = backbone_error
            torch = types.SimpleNamespace(hub=hub, __version__='test')
            paths = types.SimpleNamespace(dinov3_repo=lambda: str(pack / '_vendor/dinov3_hub'))
            renderer = types.ModuleType('hairdeck_core.vrm.render')
            renderer._pyrender = Mock(side_effect=renderer_error)
            modules = {'torch': torch, 'hairdeck_core': types.SimpleNamespace(paths=paths),
                       'hairdeck_core.vrm.render': renderer}
            probe = Path(__file__).with_name('probe_hairdeck.py')
            with patch.dict(sys.modules, modules), patch.object(sys, 'argv', [str(probe), str(core), str(pack)]):
                runpy.run_path(str(probe), run_name='__main__')
            hub.load.assert_called_once_with(paths.dinov3_repo(), 'dinov3_vitl16', source='local', pretrained=False, device='meta')
            return renderer._pyrender

    def test_lazy_backbone_import_failure_rejects_installation(self):
        with self.assertRaisesRegex(ModuleNotFoundError, 'termcolor'):
            self.run_probe(backbone_error=ModuleNotFoundError("No module named 'termcolor'"))

    def test_lazy_review_renderer_import_failure_rejects_installation(self):
        with self.assertRaisesRegex(ModuleNotFoundError, 'six'):
            self.run_probe(renderer_error=ModuleNotFoundError("No module named 'six'"))

    def test_complete_probe_uses_meta_backbone_and_imports_review_renderer(self):
        self.run_probe().assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
