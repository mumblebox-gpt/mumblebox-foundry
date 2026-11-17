"""Keep binding and movement evidence attributable to the current rig."""
import unittest

import test_rigging
from foundry.workflows.rigging.diagnostics import findings, joint_pose


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        fixture = test_rigging.RiggingTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.run = fixture.service.create(fixture.id, fixture.service.sources(fixture.id)[0]["id"])
        self.service = fixture.service

    def test_leaving_review_clears_the_transient_joint_pose(self):
        from foundry.workflows.rigging.runtime import attach_output
        bound = attach_output(self.service,self.run,{"report":{"unweighted":0,"vertices":3}}, "f"*32)
        staged = self.service.edit(bound["id"],bound["revision"],"pose_joint",
            test_pose={"bone_id":"elbow.L","axis":"x","angle":.4})
        self.assertIsNotNone(staged["joint_pose"])
        exported = self.service.edit(staged["id"],staged["revision"],"step",step="export")
        self.assertIsNone(exported["joint_pose"])

    def test_pose_validation_rejects_unknown_bone_and_out_of_range_angle(self):
        for data in ({"bone_id": "missing", "axis": "x", "angle": .5},
                     {"bone_id": "elbow.L", "axis": "x", "angle": 7}):
            with self.assertRaises(ValueError):
                joint_pose(self.run, data)

    def test_neighbor_motion_and_stale_binding_are_distinct(self):
        selection = {"bone_id": "elbow.L", "neighbor_ids": ["elbow.R"]}
        pose = {"bone_id": "elbow.L", "axis": "x", "angle": .5}
        evidence = {"total": 300, "sampled": 11, "unweighted": 0, "max_influences": 4,
                    "invalid_weights": 0, "not_normalized": 1,
                    "target": {"samples": 6, "moved": 5, "max": .12},
                    "neighbors": {"samples": 4, "moved": 2, "max": .04}}
        stale = findings(self.run, selection, pose, evidence=None)
        self.assertIn("binding_required", [finding["code"] for finding in stale])
        # A current binding may report movement for a named comparison region.
        from foundry.workflows.rigging.sessions import skeleton_key
        self.run["output"] = {"skeleton": skeleton_key(self.run), "binding": "a"*32,
                              "report": {"unweighted": 0, "vertices": 300}}
        result = {finding["code"]:finding for finding in findings(self.run, selection, pose, evidence)}
        self.assertEqual(result["neighbor_motion"]["measure"]["moved"], 2)
        self.assertEqual(result["neighbor_motion"]["severity"], "warning")
        self.assertEqual(result["neighbor_motion"]["measure"]["sampled"], 11)
        self.assertEqual(result["weight_sample"]["severity"], "warning")
        self.assertEqual(result["weight_sample"]["measure"]["not_normalized"], 1)
