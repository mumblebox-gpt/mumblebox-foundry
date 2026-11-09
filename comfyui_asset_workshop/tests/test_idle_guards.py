"""Library mutations must wait for coordinated jobs even between native prompts."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import sys
from unittest.mock import patch


def function(name, filename, context):
    tree = ast.parse((Path(__file__).parents[1] / filename).read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), context)
    return context[name]


class IdleGuardTests(unittest.TestCase):
    def idle(self, coordinated, guided=False, splat=False, ccore=False):
        check = function("idle", "routes.py", {
            "__name__": "_idle_test.routes", "__package__": "_idle_test",
            "queue": lambda: SimpleNamespace(get_tasks_remaining=lambda: 0),
            "description_helper": SimpleNamespace(STATE={}),
            "single_image_jobs_active": lambda: coordinated,
            "JobConflict": RuntimeError,
        })
        modules = {"_idle_test.foundry.workflows." + name + ".runs":
                   SimpleNamespace(busy=lambda active=active: active)
                   for name, active in (("image_to_3d", False), ("image_creation", False),
                                        ("hair_creation", False), ("guided_mesh", guided), ("splat_solid", splat), ("ccore_prop", ccore))}
        def run():
            with patch.dict(sys.modules, modules):
                return check()
        return run

    def test_library_mutations_rejected_between_native_stages(self):
        with self.assertRaisesRegex(RuntimeError, "Mumblebox job"):
            self.idle(True)()

    def test_idle_library_remains_available(self):
        self.idle(False)()

    def test_library_waits_for_guided_work_between_native_prompts(self):
        with self.assertRaisesRegex(RuntimeError, "Mumblebox job"):
            self.idle(False, guided=True)()

    def test_library_waits_for_splat_work_between_native_prompts(self):
        with self.assertRaisesRegex(RuntimeError, "Mumblebox job"):
            self.idle(False, splat=True)()

    def test_library_waits_for_ccore_package_publication(self):
        with self.assertRaisesRegex(RuntimeError, "Mumblebox job"):
            self.idle(False, ccore=True)()

    def test_active_job_check_uses_coordinator_tasks(self):
        context = {"COORDINATOR": None}
        check = function("has_active_jobs", "single_image_routes.py", context)
        self.assertFalse(check())
        context["COORDINATOR"] = SimpleNamespace(tasks={})
        self.assertFalse(check())
        context["COORDINATOR"].tasks["ownedjob"] = object()
        self.assertTrue(check())
