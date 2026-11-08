"""HairDeck install must isolate shell compatibility fixes and retain current probes."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import install_hairdeck


class HairInstallTests(unittest.TestCase):
    def test_dependency_build_uses_bundled_distutils_without_changing_parent_environment(self):
        source=install_hairdeck.ROOT
        spec=json.loads((source/'dependencies.json').read_text(encoding='utf-8'))['hairdeck_wrapper']
        with tempfile.TemporaryDirectory() as directory:
            core=Path(directory)/'core'
            (core/'user/mumblebox-foundry/software/hairdeck/.git').mkdir(parents=True)
            python=Path(directory)/'python.exe'
            with patch.dict(os.environ,{'SETUPTOOLS_USE_DISTUTILS':'stdlib'}), \
                 patch.object(install_hairdeck.subprocess,'check_output',side_effect=[spec['revision'],'2.12.1+cu130']), \
                 patch.object(install_hairdeck,'run') as run:
                install_hairdeck.install(core,python,source)
                command,options=run.call_args_list[0]
                self.assertEqual(command[0][:3],['uv','pip','install'])
                self.assertEqual(options.get('env',{}).get('SETUPTOOLS_USE_DISTUTILS'),'local')
                self.assertEqual(os.environ['SETUPTOOLS_USE_DISTUTILS'],'stdlib')
                self.assertIn(source/spec['requirements'],command[0])
                self.assertIn('--constraint',command[0])
                constraints=core/'user/mumblebox-foundry/software/hair-host-constraints.txt'
                self.assertEqual(constraints.read_text(),'torch==2.12.1+cu130\n')
                probes=[call.args[0][1] for call in run.call_args_list[1:]]
                self.assertEqual(probes,[source/'scripts/probe_hairdeck.py',source/'scripts/probe_hair_color.py'])


if __name__=='__main__':unittest.main()
