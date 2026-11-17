"""Weight edits preserve locks, vertex normalization and the previous binding."""
import unittest

import test_rigging
from foundry.workflows.rigging.runtime import attach_output
from foundry.workflows.rigging.sessions import current_output
from foundry.workflows.rigging.weights import apply_target, brush_value


class WeightTests(unittest.TestCase):
    def test_rigid_assignment_preserves_locked_influence_and_limits_slots(self):
        old = {"locked": .25, "a": .33, "b": .24, "c": .18}
        self.assertEqual(apply_target(old, "new", 1, {"locked"}), {"locked":.25,"new":.75})
        result = apply_target(old, "new", .4, {"locked"})
        self.assertAlmostEqual(sum(result.values()), 1)
        self.assertEqual(len(result), 4)
        self.assertEqual(result["new"], .4)
        self.assertEqual(result["locked"], .25)
        self.assertEqual(apply_target(old, "locked", 1, {"locked"}), old)

    def test_brush_modes_limit_edits_to_selected_influence_target(self):
        cases = {"paint":.45,"smooth":.3,"add":.7,"subtract":.1,"rigid":1}
        for mode,wanted in cases.items():
            self.assertAlmostEqual(brush_value(mode,.4,.3,.5666666666666667,1/15),wanted)

    def test_weight_revision_stales_only_export_and_undo_restores_preview(self):
        fixture = test_rigging.RiggingTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        service = fixture.service
        run = service.create(fixture.id, service.sources(fixture.id)[0]["id"])
        run = attach_output(service, run, {"file":"rig.glb","report":{}}, "0"*32)
        args = {"bone_id":"elbow.L","mode":"paint","points":[run["joints"]["elbow.L"]],
                "radius":.05,"strength":.5,"target":.9}
        changed, receipt = service.command(run["id"],0,"b"*32,"weight_stroke",args)
        self.assertTrue(receipt["binding_stale"])
        self.assertIsNone(current_output(changed))
        self.assertEqual(changed["skeleton"],run["skeleton"])
        self.assertEqual(changed["step"],"review")
        undone,_ = service.command(run["id"],1,"c"*32,"undo",{})
        self.assertEqual(current_output(undone)["binding"],"0"*32)
