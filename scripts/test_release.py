"""Portable install contract: no downloads, preserved state, repeatability, rollback."""
import argparse, importlib.util, json, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
spec=importlib.util.spec_from_file_location("installer",Path(__file__).with_name("install_foundry.py"))
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class InstallTests(unittest.TestCase):
    def test_release_rejects_corrupted_interface_text(self):
        spec=importlib.util.spec_from_file_location('builder',Path(__file__).with_name('build_release.py'))
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'interface.js'
            for data in (b'Front details \x97 optional', 'Front details \u00c2\u00b7 optional'.encode('utf-8')):
                source.write_bytes(data)
                with self.assertRaises(ValueError):builder.validate_text_encoding([source])
            source.write_text('Front details \u00b7 optional',encoding='utf-8')
            builder.validate_text_encoding([source])
        builder.validate_text_encoding(builder.inventory())

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="foundry-install-")
        self.root=Path(self.temp.name);self.core=self.root/"core"
        (self.core/"custom_nodes").mkdir(parents=True)
        (self.core/"folder_paths.py").write_text("# host fixture")
        self.repo=self.root/"wrapper";self.repo.mkdir();(self.repo/"__init__.py").write_text("")
        self.models=self.root/"weights";self.models.mkdir();(self.models/"keep.txt").write_text("model sentinel")
        self.exe=self.root/"python.exe";self.exe.write_text("fixture")
        self.user=self.core/"user";self.user.mkdir()
        (self.user/"asset-workshop.json").write_text(json.dumps({"theme":"keep","pipeline_runtime":{"stable_materials":"preserve"}}))
        self.args=argparse.Namespace(comfy=str(self.core),user_directory=None,worker_python=str(self.exe),trellis_repo=str(self.repo),trellis_models=str(self.models),blender=str(self.exe),hi3d_url="http://127.0.0.1:8378",skip_hair_software=True)
    def tearDown(self):self.temp.cleanup()
    def test_release_inventory_contains_material_editor(self):
        spec=importlib.util.spec_from_file_location('builder',Path(__file__).with_name('build_release.py'))
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        names={p.relative_to(builder.ROOT).as_posix() for p in builder.inventory()}
        self.assertIn('comfyui_asset_workshop/material_lab/material_editor.html',names)
        for name in ('pinokio.js', 'pinokio.json', 'install.js', 'start.js', 'update.js',
                     'repair.js', 'icon.png', 'scripts/pinokio/bootstrap.py',
                     'scripts/pinokio/runtime.py', 'scripts/pinokio/maintenance.py',
                     'scripts/pinokio/connect_agent.py', 'docs/PINOKIO.md',
                     'scripts/requirements-hair-windows.txt','scripts/install_hairdeck.py',
                     'scripts/probe_hairdeck.py','scripts/probe_hair_color.py','docs/HAIR-WORKFLOW.md',
                     'comfyui_asset_workshop/web/assets/foundry/hair.png'):
            self.assertIn(name,names)
        for method in ('single','turnaround','guided','splat'):
            self.assertIn('comfyui_asset_workshop/web/assets/foundry/method-'+method+'.webp',names)
        self.assertIn('comfyui_asset_workshop/finishing/grounding.py',names)
        self.assertNotIn('scripts/pinokio/mcp.py',names)
        self.assertFalse(any(name.startswith(('.pinokio/', 'bench/')) for name in names))
    def test_install_and_repeat_preserve(self):
        installer.install(self.args)
        target=self.core/"custom_nodes/comfyui_asset_workshop"
        self.assertTrue((target/"foundry/routes.py").is_file())
        config=json.loads((self.user/"asset-workshop.json").read_text())
        self.assertEqual(config["theme"],"keep")
        self.assertEqual(config["pipeline_runtime"]["stable_materials"],"preserve")
        installer.install(self.args)
        changes=sorted((self.user/"mumblebox-foundry/install-backups").glob("*/changed-files.json"))
        self.assertEqual(json.loads(changes[-1].read_text()),[])
        self.assertEqual((self.models/"keep.txt").read_text(),"model sentinel")
        self.assertFalse(any(target.rglob("*.safetensors")))
    def test_changed_file_backup(self):
        target=self.core/"custom_nodes/comfyui_asset_workshop";target.mkdir()
        (target/"models.py").write_text("previous module")
        installer.install(self.args)
        backups=list((self.user/"mumblebox-foundry/install-backups").glob("*/custom-node/models.py"))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_text(),"previous module")
    def test_default_install_calls_hair_software_with_actual_host(self):
        self.args.skip_hair_software=False
        self.args.host_python=str(self.exe)
        with patch('install_hairdeck.install') as hair:
            installer.install(self.args)
        hair.assert_called_once_with(self.core.resolve(),self.exe.resolve(),installer.ROOT)
    def test_remote_service_rejected_before_writes(self):
        self.args.hi3d_url="http://example.com"
        with self.assertRaises(ValueError):installer.install(self.args)
        self.assertFalse((self.core/"custom_nodes/comfyui_asset_workshop").exists())
    def test_onedrive_runtime_rejected_before_writes(self):
        self.args.worker_python=str(self.root/"OneDrive/python.exe")
        with self.assertRaises(ValueError):installer.install(self.args)
        self.assertFalse((self.core/"custom_nodes/comfyui_asset_workshop").exists())

if __name__=="__main__":unittest.main()
