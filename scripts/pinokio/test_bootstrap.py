import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bootstrap

class InstallationTests(unittest.TestCase):
    def test_download_identifies_client_and_verifies_checksum(self):
        import hashlib,io
        data=b'archive contents'
        class Response(io.BytesIO):
            headers={'Content-Length':str(len(data))}
        with tempfile.TemporaryDirectory() as directory, patch.object(bootstrap.urllib.request,'urlopen',side_effect=lambda *a,**k:Response(data)) as open_url:
            path=Path(directory)/'archive.zip'
            bootstrap.download('https://example.invalid/archive.zip',path,hashlib.sha256(data).hexdigest())
            request=open_url.call_args.args[0]
            self.assertIsInstance(request,bootstrap.urllib.request.Request)
            self.assertIn('Mumblebox-Foundry',request.get_header('User-agent'))
            self.assertEqual(path.read_bytes(),data)

    def test_verified_archive_cache_skips_the_network(self):
        import hashlib
        data=b'verified archive'
        with tempfile.TemporaryDirectory() as directory, patch.object(bootstrap.urllib.request,'urlopen') as open_url:
            path=Path(directory)/'archive.zip';path.write_bytes(data)
            bootstrap.download('https://example.invalid/archive.zip',path,hashlib.sha256(data).hexdigest())
            open_url.assert_not_called()
            self.assertEqual(path.read_bytes(),data)

    def test_bad_download_does_not_replace_existing_archive(self):
        import io
        class Response(io.BytesIO):
            headers={'Content-Length':'9'}
        with tempfile.TemporaryDirectory() as directory, patch.object(bootstrap.urllib.request,'urlopen',side_effect=lambda *a,**k:Response(b'incorrect')):
            path=Path(directory)/'archive.zip';path.write_bytes(b'previous archive')
            with self.assertRaisesRegex(ValueError,'checksum'):
                bootstrap.download('https://example.invalid/archive.zip',path,'0'*64)
            self.assertEqual(path.read_bytes(),b'previous archive')

    def test_managed_python_ignores_conflicting_pinokio_preference(self):
        with patch.dict(bootstrap.os.environ,{'UV_PYTHON_PREFERENCE':'only-system'}), patch.object(bootstrap,'capture',return_value='python310') as capture:
            self.assertEqual(bootstrap.managed_python('uv','3.10'),'python310')
            self.assertNotIn('UV_PYTHON_PREFERENCE',capture.call_args.kwargs['env'])
            self.assertEqual(bootstrap.os.environ['UV_PYTHON_PREFERENCE'],'only-system')

    def test_native_wheels_select_required_packages_among_extra_upstream_wheels(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            required=('cumesh','flex_gemm','nvdiffrast','nvdiffrec_render','o_voxel')
            for package in (*required,'custom_rasterizer','dcx_pkg','natten'):
                (root/f'{package}-1.0-cp313-cp313-win_amd64.whl').touch()
            (root/'cumesh-1.0-cp312-cp312-win_amd64.whl').touch()
            selected=bootstrap.native_wheels(root,'cp313-win_amd64')
            self.assertEqual([p.name.split('-')[0] for p in selected],list(required))
            selected[0].unlink()
            with self.assertRaisesRegex(ValueError,'cumesh'):
                bootstrap.native_wheels(root,'cp313-win_amd64')

    def test_source_retry_recovers_empty_clone_and_preserves_modified_checkout(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();upstream=root/'upstream';upstream.mkdir()
            def git(*args,cwd=upstream):
                return subprocess.check_output(['git',*args],cwd=cwd,text=True,stderr=subprocess.STDOUT).strip()
            git('init');git('config','user.name','Installer test');git('config','user.email','test@example.invalid')
            (upstream/'README.md').write_text('original')
            git('add','README.md');git('commit','-m','fixture')
            spec={'repository':str(upstream),'revision':git('rev-parse','HEAD')}
            target=root/'installed'
            git('clone','--no-checkout',str(upstream),str(target))
            bootstrap.checkout(spec,target)
            self.assertEqual((target/'README.md').read_text(),'original')
            (target/'README.md').write_text('user edit')
            with self.assertRaises(ValueError):bootstrap.checkout(spec,target)
            self.assertEqual((target/'README.md').read_text(),'user edit')

    def test_relocatable_paths_and_no_default_shared_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            layout=bootstrap.Layout(root)
            self.assertEqual(layout.data,root/'.pinokio'/'data')
            self.assertTrue(layout.worker_python.is_relative_to(root))
            self.assertTrue(layout.comfy.is_relative_to(root))

    def test_step_is_recorded_only_after_success_and_retries_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state=bootstrap.StepState(Path(directory)/'steps.json')
            with self.assertRaises(RuntimeError):
                state.run('host','v1',lambda: (_ for _ in ()).throw(RuntimeError('interrupted')))
            self.assertNotIn('host',state.values)
            calls=[]
            state.run('host','v1',lambda:calls.append(1))
            state.run('host','v1',lambda:calls.append(2))
            self.assertEqual(calls,[1])
            state.run('host','v2',lambda:calls.append(3))
            self.assertEqual(calls,[1,3])

    def test_archive_rejects_escape_paths(self):
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();archive=root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape','bad')
            with self.assertRaises(ValueError):bootstrap.extract_checked(archive,root/'destination')
            self.assertFalse((root/'escape').exists())

    def test_release_software_install_does_not_enable_model_downloads(self):
        root=Path(__file__).resolve().parents[2]
        manifest=json.loads((root/'dependencies.json').read_text())
        commands=bootstrap.hi3d_setup_commands(Path('hi3d'),Path('python310'))
        flat=[str(arg) for command in commands for arg in command]
        self.assertNotIn('-DownloadModels',flat)
        self.assertNotIn('hi3d_workbench.model_cli',flat)
        self.assertIn('torch==2.11.0+cu128',flat)
        self.assertFalse(manifest['hi3d_workbench']['download_models_during_install'])

if __name__=='__main__':unittest.main()
