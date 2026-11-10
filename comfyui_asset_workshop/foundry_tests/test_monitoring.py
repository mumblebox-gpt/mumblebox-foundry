import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline_workers import activity
from pipeline_workers.worker_telemetry import residency
from foundry.preferences import Preferences

class MonitoringTests(unittest.TestCase):
    def tearDown(self):
        activity.remove('test')

    def test_worker_exit_and_exception_clear_residency(self):
        with self.assertRaises(RuntimeError):
            with activity.tracked('test','Hi3D'):
                activity.update('test','Hi3D','loaded',device='CUDA')
                self.assertEqual(activity.snapshot()[0]['state'],'loaded')
                raise RuntimeError('cancelled')
        self.assertEqual(activity.snapshot(),[])

    def test_stale_or_wrong_pid_never_reports_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model-residency.json'
            for pid,stamp,expected in [(os.getpid(),time.time(),'loaded'),(0,time.time(),'unknown'),(os.getpid(),0,'unknown')]:
                path.write_text(json.dumps({'pid':pid,'time':stamp,'state':'loaded','device':'CUDA'}))
                activity.read_worker('test','TRELLIS.2',path,os.getpid())
                self.assertEqual(activity.snapshot()[0]['state'],expected)

    def test_cpu_gpu_meta_and_empty_pipelines_are_distinct(self):
        def pipeline(devices):
            class Model:
                def __init__(self,device):self.device=device
                def parameters(self):return iter([SimpleNamespace(device=self.device)])
            return SimpleNamespace(models={str(i):Model(d) for i,d in enumerate(devices)})
        self.assertEqual(residency(pipeline(['cuda:0','cpu']))['state'],'loaded')
        self.assertEqual(residency(pipeline(['cpu']))['state'],'offloaded')
        self.assertEqual(residency(pipeline(['meta']))['state'],'unknown')
        self.assertEqual(residency(pipeline([]))['state'],'unknown')

    def test_comfy_offloaded_patcher_is_not_gpu_loaded(self):
        patcher=SimpleNamespace(loaded_size=lambda:0,load_device='cuda:0')
        self.assertEqual(activity.host_residency([SimpleNamespace(model=patcher)])[0]['state'],'offloaded')

    def test_native_checkpoint_names_and_worker_stage_replacement(self):
        patcher=SimpleNamespace(loaded_size=lambda:123,load_device='cuda:0',
                                cached_patcher_init=(None,([r'C:\\models\\Shape.safetensors'],)))
        with activity.tracked('test', 'Garment Particles'):
            activity.update_models('test',[{'name':'Text generator','state':'loaded','device':'GPU'}])
            self.assertEqual([row['name'] for row in activity.model_snapshot([SimpleNamespace(model=patcher)])],
                             ['Shape.safetensors','Text generator'])
            activity.update_models('test',[{'name':'Sewing pattern','state':'loaded','device':'GPU'}])
            self.assertEqual([row['name'] for row in activity.snapshot()],['Sewing pattern'])
            activity.update_models('test',[])
            self.assertEqual(activity.snapshot(),[])

    def test_explicit_motion_choice_is_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Preferences(Path(tmp)/'preferences.json')
            self.assertEqual(p.read()['busy_motion'],'system')
            self.assertEqual(p.update({'busy_motion':'full'})['busy_motion'],'full')
            with self.assertRaises(ValueError):p.update({'busy_motion':'invalid'})

if __name__=='__main__':unittest.main()
