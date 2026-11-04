"""Only allocate high-resolution features consumed by the requested stages."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import torch

spec = importlib.util.spec_from_file_location("aw_pixal_conditioning", Path(__file__).parents[1] / "pixal_conditioning.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DraftConditioningTests(unittest.TestCase):
    def setUp(self):
        self.condition = {"batch_size": 2, "global_512": torch.arange(8.).reshape(2, 2, 2),
                          "global_1024": torch.arange(8., 16.).reshape(2, 2, 2),
                          "patches_512": torch.ones(2, 2, 2, 2),
                          "patches_1024": torch.ones(2, 2, 4, 4), "composites": [1, 2]}
        self.native = types.SimpleNamespace(
            _dino_encode_batch=Mock(return_value=self.condition),
            _naf_upsample=Mock(side_effect=lambda *args: torch.ones(2, 2, 2, 2) * args[3]),
            compute_stage_proj_feats=Mock(return_value="projected"),
            _build_pixal3d_conditioning=Mock(return_value="full native"),
            IO=types.SimpleNamespace(NodeOutput=lambda *values: values),
            comfy=types.SimpleNamespace(model_management=types.SimpleNamespace(
                intermediate_device=lambda: "cpu", get_torch_device=lambda: "cpu")))
        self.args = (types.SimpleNamespace(naf="naf"), "images", torch.eye(4).repeat(2, 1, 1),
                     torch.tensor([.3, .3]), torch.ones(1))

    def run_scope(self, scope):
        with patch.dict(sys.modules, {"comfy_extras": types.ModuleType("comfy_extras"),
                                     "comfy_extras.nodes_trellis2": self.native}):
            return module.build_conditioning(*self.args, num_views=2, scope=scope)

    def test_geometry_keeps_native_shape_features_and_global_averaging(self):
        positive, negative = self.run_scope("geometry_draft")
        stages = positive[0][1]["proj_feat_pack"]["stages"]
        self.assertEqual(set(stages), {"ss", "shape_512"})
        self.assertEqual(self.native._naf_upsample.call_count, 1)
        self.assertEqual(self.native._naf_upsample.call_args.args[3:5], (512, (512, 512)))
        self.assertIs(stages["shape_512"]["feature_map"], self.condition["patches_512"])
        torch.testing.assert_close(positive[0][0], self.condition["global_512"].mean(0, keepdim=True))
        torch.testing.assert_close(positive[0][1]["embeds"], self.condition["global_1024"].mean(0, keepdim=True))
        self.assertEqual(positive[0][1]["trellis2_proj_feats"], "projected")
        self.assertIs(negative[0][1]["proj_feat_pack"], positive[0][1]["proj_feat_pack"])
        self.assertEqual(torch.count_nonzero(negative[0][0]).item(), 0)

    def test_color_keeps_texture_but_not_unused_refinement(self):
        positive, _ = self.run_scope("color_draft")
        stages = positive[0][1]["proj_feat_pack"]["stages"]
        self.assertEqual(set(stages), {"ss", "shape_512", "tex_1024"})
        self.assertEqual([c.args[3:5] for c in self.native._naf_upsample.call_args_list],
                         [(512, (512, 512)), (1024, (1024, 1024))])

    def test_full_route_stays_native_and_unknown_scope_fails_before_allocation(self):
        self.assertEqual(self.run_scope("full"), "full native")
        self.native._dino_encode_batch.assert_not_called()
        with self.assertRaisesRegex(ValueError, "conditioning scope"):
            self.run_scope("typo")


if __name__ == "__main__":
    unittest.main()
