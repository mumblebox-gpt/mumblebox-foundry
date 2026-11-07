import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import maintenance
from bootstrap import Layout


class MaintenanceTests(unittest.TestCase):
    def test_stop_owned_runtime_rejects_an_unrelated_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.pinokio').mkdir()
            (root/'.pinokio'/'runtime.json').write_text('{"pid":123,"instance":"owned"}')
            with patch('psutil.Process') as lookup:
                process=lookup.return_value
                process.cmdline.return_value=['python','unrelated.py'];process.cwd.return_value=str(root)
                with self.assertRaisesRegex(ValueError,'not this Foundry runtime'):
                    maintenance.stop_owned_runtime(root)
                process.terminate.assert_not_called()

    def test_stop_owned_runtime_checks_idle_and_waits_for_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.pinokio').mkdir()
            runtime=root/'.pinokio'/'runtime.json';runtime.write_text('{"pid":123,"instance":"owned"}')
            with patch('psutil.Process') as lookup,patch.object(maintenance,'require_idle') as idle:
                process=lookup.return_value
                process.cmdline.return_value=['python','scripts/pinokio/runtime.py','--root','.']
                process.cwd.return_value=str(root)
                maintenance.stop_owned_runtime(root)
                idle.assert_called_once_with(root.resolve())
                process.terminate.assert_called_once();process.wait.assert_called_once_with(timeout=20)
                self.assertFalse(runtime.exists())

    def test_running_or_queued_jobs_prevent_the_update_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.pinokio').mkdir()
            (root/'.pinokio'/'runtime.json').write_text('{"comfy_url":"http://127.0.0.1:12345"}')
            for status,queue in [({'running':True},{}),({}, {'queue_pending':[[1]]}),({}, {'queue_running':[[1]]})]:
                with self.assertRaisesRegex(ValueError,'generation is active or queued'):
                    maintenance.require_idle(root,read=lambda path:status if path.endswith('status') else queue)
            maintenance.require_idle(root,read=lambda path:{})

    def test_bundle_rejects_tampering_and_unlisted_or_user_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'README.md';file.write_text('release')
            manifest={'README.md':hashlib.sha256(file.read_bytes()).hexdigest()}
            inventory=root/'SHA256SUMS.json';inventory.write_text(json.dumps(manifest))
            self.assertEqual(maintenance.verify_bundle(root),manifest)
            file.write_text('tampered')
            with self.assertRaisesRegex(ValueError,'checksum'):maintenance.verify_bundle(root)
            file.write_text('release');(root/'extra.py').touch()
            with self.assertRaisesRegex(ValueError,'unlisted'):maintenance.verify_bundle(root)
            inventory.write_text(json.dumps({'.pinokio/data/output/asset.glb':'0'*64}))
            with self.assertRaisesRegex(ValueError,'ownership'):maintenance.verify_bundle(root)

    def test_full_release_inventory_is_accepted_by_existing_update_policy(self):
        # Older published updaters allow application directories but only their
        # original root filenames. Keep new installer resources under scripts/.
        import importlib.util,shutil
        source=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('release_builder',source/'scripts/build_release.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory);hashes={}
            for file in builder.inventory():
                name=file.relative_to(source).as_posix();dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
                hashes[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
            (target/'SHA256SUMS.json').write_text(json.dumps(hashes),encoding='utf-8')
            self.assertEqual(maintenance.verify_bundle(target),hashes)
            self.assertIn('scripts/requirements-hair-windows.txt',hashes)
            self.assertNotIn('requirements-hair-windows.txt',hashes)

    def test_local_source_changes_prevent_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.git').mkdir()
            with patch.object(maintenance,'capture',side_effect=[maintenance.REPOSITORY,' M start.js']):
                with self.assertRaisesRegex(ValueError,'local source changes'):
                    maintenance.require_clean_checkout(root)

    def test_failed_staged_install_restores_app_and_config_not_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            layout=Layout(directory)
            app=layout.comfy/'custom_nodes'/'comfyui_asset_workshop';app.mkdir(parents=True)
            (app/'old.py').write_text('working')
            config=layout.data/'user'/'asset-workshop.json';config.parent.mkdir(parents=True);config.write_text('{"keep":true}')
            output=layout.data/'output'/'asset.glb';output.parent.mkdir();output.write_bytes(b'preserved asset')
            def fail(root,source):
                (app/'old.py').write_text('changed');(app/'new.py').write_text('new')
                config.write_text('{}');raise RuntimeError('deliberate staged failure')
            with self.assertRaisesRegex(RuntimeError,'deliberate'):
                maintenance.apply_staged(layout,Path(directory)/'candidate','v2','previous',installer=fail)
            self.assertEqual((app/'old.py').read_text(),'working')
            self.assertFalse((app/'new.py').exists())
            self.assertEqual(json.loads(config.read_text()),{'keep':True})
            self.assertEqual(output.read_bytes(),b'preserved asset')
            self.assertTrue((layout.state/'repair-required.json').exists())

    def test_successful_staged_install_switches_to_verified_tag_and_clears_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            layout=Layout(directory);layout.state.mkdir()
            (layout.state/'repair-required.json').write_text('{}')
            calls=[]
            with patch.object(maintenance,'run') as run:
                maintenance.apply_staged(layout,Path(directory)/'candidate','v2','previous',installer=lambda *a:calls.append(a))
                self.assertEqual(calls[0][0],layout.root)
                run.assert_called_once_with(['git','checkout','--detach','v2'],layout.root)
            self.assertFalse((layout.state/'repair-required.json').exists())


if __name__=='__main__':unittest.main()
