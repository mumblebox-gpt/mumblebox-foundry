import ast
import dis
import sys
import unittest
import importlib
import types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
namespace = types.ModuleType("portable_foundry")
namespace.__path__ = [str(ROOT)]
sys.modules.setdefault("portable_foundry", namespace)

class PortableFinishingTests(unittest.TestCase):
    def test_guided_camera_file_is_listed_once_in_readme(self):
        import re
        from finishing.package_catalog import PackageCatalog,FileRecord
        from finishing.package_readme import render_readme
        catalog=PackageCatalog('mumblebox.asset-package/1','Prop','test','2026-11-04','test',
            [FileRecord('Metadata/cameras.json','metadata',None,'Measured cameras','json','cameras')],[],[],{},
            production={'method':'3d-guided/v1','selected_view_ids':['front'],'reference_view_id':'front'})
        links=re.findall(r'\]\((Metadata/cameras\.json)\)',render_readme(catalog))
        self.assertEqual(links,['Metadata/cameras.json'])

    def test_quad_checkpoint_loading_does_not_shadow_mesh_extractor(self):
        from portable_foundry.finishing.quad_nodes import Hi3DQuadFinish
        reads=[op for op in dis.get_instructions(Hi3DQuadFinish.finish)
               if op.argval=='arrays' and op.opname.startswith('LOAD_')]
        self.assertEqual(reads[0].opname,'LOAD_GLOBAL',
                         'The mesh extractor must remain callable before loading baked arrays.')

    def test_finishing_is_shipped_without_developer_paths(self):
        folder=ROOT/'finishing'
        self.assertTrue((folder/'nodes.py').is_file())
        for path in folder.glob('*.py'):
            source=path.read_text(encoding='utf-8')
            ast.parse(source)
            self.assertNotIn('C:\\Dev\\',source,str(path))
            self.assertNotIn('Blender Foundation',source,str(path))

    def test_package_contract_loads_without_experiment_sys_path(self):
        from finishing.package_catalog import parse_selection
        from portable_foundry.finishing.quad_nodes import Hi3DExportBundle
        selection=Hi3DExportBundle.selection(True,saved_print='asset.stl')
        self.assertEqual(set(selection.variants),{'print'})

    def test_registry_uses_distributed_resource_file(self):
        from foundry.catalog import catalog
        result=catalog()
        self.assertTrue(result['resource_registry_available'])
        self.assertEqual(result['github'],'https://github.com/mumblebox-gpt')

if __name__=='__main__':unittest.main()
