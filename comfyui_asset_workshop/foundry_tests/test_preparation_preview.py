"""Preview the selected wizard dependencies without creating a run or loading models."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.workflows.image_to_3d import readiness, worker_models
from foundry.workflows.image_to_3d.runs import WizardRuns
from finishing.package_catalog import VARIANTS, parse_selection


class PreparationPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = WizardRuns(self.root / "state", self.root / "input", self.root / "output",
                                  None, None, None, parse_selection, VARIANTS)
        self.config = {
            "method": "single-image", "overrides": {},
            "selection": {"schema": "mumblebox.export-selection/1",
                          "variants": {"detailed": {"formats": ["glb"]}}},
        }

    def test_single_mesh_preview_has_downstream_resources_and_does_not_touch_files(self):
        with patch.object(readiness, "native_model_path", return_value=None), \
                patch.object(worker_models, "texture_model_root", return_value=self.root / "worker"), \
                patch.object(readiness, "ensure") as ensure, \
                patch.object(self.service, "fresh") as fresh:
            result = self.service.preparation_preview(self.config, "mesh")
        self.assertEqual([stage["id"] for stage in result["stages"]], ["single_geometry", "refinement", "texture"])
        resources = {item["id"]: item for item in result["resources"]}
        self.assertIn("pixal_single", resources)
        self.assertNotIn("qwen21", resources)
        self.assertEqual(len(result["resources"]), len(resources))
        self.assertTrue(any(item["stage"] == "texture" for item in result["resources"]))
        self.assertGreater(result["known_download_bytes"], 0)
        self.assertEqual(result["unknown_download_count"], 1)
        self.assertEqual(resources["hi3d"]["status"], "unknown")
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertFalse(self.service.runs)
        self.assertFalse(self.service.tasks)
        ensure.assert_not_called()
        fresh.assert_not_called()

    def test_turnaround_and_print_only_use_the_selected_resources(self):
        self.config["method"] = "turnaround"
        self.config["selection"]["variants"] = {"print": {"formats": ["stl"]}}
        with patch.object(readiness, "native_model_path", return_value=None), \
                patch.object(worker_models, "texture_model_root") as texture_root:
            result = self.service.preparation_preview(self.config, "turnaround")
            finish = self.service.preparation_preview(self.config, "finish")
        self.assertEqual([stage["id"] for stage in result["stages"]], ["turnaround", "geometry", "refinement"])
        self.assertIn("qwen21", {item["id"] for item in result["resources"]})
        self.assertEqual(finish["resources"], [])
        texture_root.assert_not_called()

    def test_present_models_require_no_estimated_download_and_restricted_models_are_flagged(self):
        installed = self.root / "model"
        installed.write_bytes(b"x")
        catalog = {
            key: {"name": key, "size": 1, "gated": key == "shape_vae"}
            for key in readiness.MODELS["single_geometry"]
        }
        self.config["selection"]["variants"] = {"print": {"formats": ["stl"]}}
        with patch("foundry.workflows.image_to_3d.turnaround.model_lock", return_value=catalog), \
                patch.object(readiness, "native_model_path",
                             side_effect=lambda item: installed if item["name"] == "pixal_single" else None):
            result = self.service.preparation_preview(self.config, "mesh")
        resources = {item["id"]: item for item in result["resources"]}
        self.assertEqual(resources["pixal_single"]["status"], "present")
        self.assertEqual(resources["pixal_single"]["download_bytes"], 0)
        self.assertEqual(resources["shape_vae"]["status"], "access_required")

    def test_invalid_requests_never_probe_installed_models(self):
        with patch.object(readiness, "native_model_path") as probe:
            for operation in ("delete", "turnaround"):
                with self.assertRaises(ValueError):
                    self.service.preparation_preview(self.config, operation)
            with self.assertRaises(ValueError):
                self.service.preparation_preview({**self.config, "overrides": {"texture_mode": "bad"}}, "mesh")
        probe.assert_not_called()
