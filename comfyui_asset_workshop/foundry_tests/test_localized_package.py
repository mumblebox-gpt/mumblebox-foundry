import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finishing.package_catalog import PackageCatalog, FileRecord, VariantRecord
from finishing.package_readme import render_readme
from finishing.package_archive import publish_archive, validate_archive

class LocalizedPackageTests(unittest.TestCase):
    def fixture(self):
        return PackageCatalog('mumblebox.asset-package/1','Settings','test','2026-11-10','test',
            [FileRecord('Detailed/mesh.glb','mesh','detailed','Original mesh','glb','runtime'),FileRecord('Metadata/manifest.json','metadata',None,'Package inventory','json','catalog')],
            [VariantRecord('detailed','Detailed/','Original mesh','',["Detailed/mesh.glb"],{'geometry':{'triangles':123,'watertight':True}})],
            [{'name':'Upstream Model','license':'Apache-2.0','license_summary':'Original retained license summary'}],{'name':'Mumblebox'})
    def test_localized_readme_preserves_machine_data_and_user_names(self):
        catalog=self.fixture();before=copy.deepcopy(catalog.to_dict())
        en=render_readme(catalog);zh=render_readme(catalog,'zh-CN')
        self.assertIn('Directory index',en);self.assertIn('目录索引',zh)
        self.assertIn('Settings',zh);self.assertNotIn('设置 —',zh)
        self.assertIn('Apache-2.0',zh);self.assertIn('Original retained license summary',zh)
        self.assertIn('Detailed/mesh.glb',zh);self.assertIn('123',zh)
        self.assertEqual(catalog.to_dict(),before)
    def test_chinese_archive_keeps_inventory_links_and_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'asset';(root/'Detailed').mkdir(parents=True)
            (root/'Detailed/mesh.glb').write_bytes(b'unchanged mesh fixture')
            archive=publish_archive(self.fixture(),root,Path(directory)/'asset.zip',lambda:None,locale='zh-CN')
            self.assertEqual(validate_archive(archive)['file_count'],3)
            self.assertIn('资产包信息',(root/'README.md').read_text(encoding='utf-8'))
            self.assertEqual((root/'Detailed/mesh.glb').read_bytes(),b'unchanged mesh fixture')

if __name__=='__main__':unittest.main()
