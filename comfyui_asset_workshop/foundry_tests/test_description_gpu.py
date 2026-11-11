"""Exercise the real helper function with a failed isolated CUDA worker, without weights."""
import ast
import copy
import os
import socket
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "description_helper.py"

class DescriptionGpuTests(unittest.TestCase):
    def environment(self, root, cuda=True):
        tree=ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="complete")
        memory=types.SimpleNamespace(get_torch_device=lambda:types.SimpleNamespace(type="cuda" if cuda else "cpu"),unload_all_models=Mock(),soft_empty_cache=Mock())
        models=types.SimpleNamespace(DOWNLOAD_LOCK=Mock(),DOWNLOAD={})
        activity=types.SimpleNamespace(update=Mock(),remove=Mock(),update_models=Mock())
        scope={"__name__":"translation_gpu_test.helper","__package__":"translation_gpu_test","SYSTEM":"system","PROCESS":None,"models":models,"memory":memory,
               "STATE":{},"runtime":lambda:root/"llama-server.exe","weights":lambda *args,**kwargs:[root/"model.gguf"],"check_cancelled":Mock(),
               "PromptServer":types.SimpleNamespace(instance=types.SimpleNamespace(prompt_queue=types.SimpleNamespace(get_tasks_remaining=lambda:0))),
               "psutil":types.SimpleNamespace(virtual_memory=lambda:types.SimpleNamespace(available=64*1024**3)),"socket":socket,"secrets":types.SimpleNamespace(token_urlsafe=lambda n:"test-key"),
               "os":os,"time":time,"subprocess":types.SimpleNamespace(Popen=Mock(),DEVNULL=-3,CREATE_NO_WINDOW=0,TimeoutExpired=TimeoutError)}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(SOURCE),"exec"),scope)
        return scope,activity

    def test_gpu_translation_rejects_cpu_before_downloading(self):
        with tempfile.TemporaryDirectory() as directory:
            scope,_=self.environment(Path(directory),cuda=False)
            with self.assertRaisesRegex(ValueError,"NVIDIA GPU"):
                scope["complete"]({"id":"test","settings":{}},[],gpu_only=True)
            scope["models"].DOWNLOAD_LOCK.acquire.assert_not_called()

    def test_cuda_load_failure_keeps_prompt_and_never_retries_on_cpu(self):
        with tempfile.TemporaryDirectory() as directory:
            scope,activity=self.environment(Path(directory));source={"id":"test","settings":{"helper_precision":"q4"}};before=copy.deepcopy(source)
            worker=Mock();worker.poll.return_value=1
            def start(command,**kwargs):
                kwargs['stdout'].write(b'CUDA out of memory\n');kwargs['stdout'].flush();return worker
            scope['subprocess'].Popen.side_effect=start
            package=types.ModuleType('translation_gpu_test');package.__path__=[]
            module=types.ModuleType('translation_gpu_test.pipeline_workers');module.activity=activity
            with patch.dict(sys.modules,{'translation_gpu_test':package,'translation_gpu_test.pipeline_workers':module}):
                with self.assertRaisesRegex(ValueError,'Choose Q4 or free GPU memory'):
                    scope['complete'](source,[],gpu_only=True,context_tokens=8192,use_vision=False)
            scope['subprocess'].Popen.assert_called_once()
            command=scope['subprocess'].Popen.call_args.args[0]
            for flag,value in [('--gpu-layers','all'),('--device','CUDA0'),('--fit','off'),('--ctx-size','8192')]:
                self.assertEqual(command[command.index(flag)+1],value)
            self.assertEqual(source,before)
            self.assertIsNone(scope['PROCESS']);activity.remove.assert_called_once()
            self.assertFalse((Path(directory)/'mumblebox-last-run.log').exists())

if __name__=='__main__':unittest.main()
