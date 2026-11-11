"""Verify a fresh CCORE request reaches its existing native-job owner."""
import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / "foundry/workflows/ccore_prop/runs.py"

class CcoreStartTests(unittest.TestCase):
    def test_fresh_asset_start_queues_its_native_job(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PropRuns")
        function = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == "start")
        create_task = Mock(return_value="native-task")
        config = {"prompt": "A static olive field radio"}
        scope = {"options": lambda data: config,
                 "asyncio": types.SimpleNamespace(create_task=create_task),
                 "uuid": types.SimpleNamespace(uuid4=lambda: "native-prompt-id"),
                 "time": types.SimpleNamespace(time=lambda: 123)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), scope)
        path = Mock(); path.exists.return_value = False
        owner = types.SimpleNamespace(path=Mock(return_value=path), tasks={}, records={}, enhancement=None,
                                      native=types.SimpleNamespace(active_ids=lambda: []), other_busy=lambda: False,
                                      save=Mock(), execute=Mock(return_value="native-coroutine"), public=lambda run: run)
        result = scope["start"](owner, {"request_id": "a" * 32, "client_id": "foundry-test"})
        self.assertEqual(result["config"], config)
        self.assertEqual(result["status"], "running")
        owner.save.assert_called_once_with(result)
        owner.execute.assert_called_once_with(result, "foundry-test")
        create_task.assert_called_once_with("native-coroutine")
        self.assertEqual(owner.tasks[result["id"]], "native-task")
        self.assertIs(owner.records[result["id"]], result)

if __name__ == "__main__":
    unittest.main()
