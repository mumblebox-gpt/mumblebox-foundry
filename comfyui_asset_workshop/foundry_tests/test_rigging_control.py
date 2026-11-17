"""Agent control uses the same commit boundary as the editable rig."""
import json
import unittest
from unittest.mock import patch

import test_rigging
from foundry.workflows.rigging.runtime import attach_output
from foundry.workflows.rigging.sessions import RigSessions


class AgentEditingTests(unittest.TestCase):
    def setUp(self):
        fixture = test_rigging.RiggingTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.service = fixture.service
        self.source = fixture.first
        self.record_id = fixture.id
        self.sources = self.service.sources(self.record_id)
        self.run = self.service.create(self.record_id, self.sources[0]["id"])
        self.run_id = self.run["id"]

    def admit_agent(self):
        return self.service.admit(self.run_id, self.run["rig_revision"], {
            "actor": "agent", "agent_session_id": "f" * 32,
        })

    def test_stop_survives_reload_and_run_change(self):
        stopped = self.service.control.stop("user")
        reopened = RigSessions(self.service.root, self.service.library)
        other = reopened.create(self.record_id, self.sources[1]["id"])
        self.assertEqual(reopened.control.status(), stopped)
        with self.assertRaisesRegex(ValueError, "stopped"):
            reopened.admit(other["id"], 0, {"actor": "agent", "agent_session_id": "e" * 32})

    def test_stop_epoch_rejects_late_result_after_resume(self):
        context = self.admit_agent()
        before = self.service.path(self.run_id).read_bytes()
        stopped = self.service.control.stop("user")
        capability = self.service.control.offer_resume("a" * 32)
        resumed = self.service.control.resume(capability, "a" * 32)
        self.assertGreater(resumed["epoch"], stopped["epoch"])
        with self.assertRaisesRegex(ValueError, "editing changed"):
            attach_output(self.service, self.run, {"file": "rig.glb"}, "b" * 32, context=context)
        self.assertEqual(self.service.path(self.run_id).read_bytes(), before)
        self.assertEqual(self.service.source_path(self.run).read_bytes(), self.source)

    def test_human_edit_survives_agent_stop(self):
        self.service.control.stop("user")
        edited, _ = self.service.command(
            self.run_id, 0, "1" * 32, "orient", {"bone_id": "elbow.L", "roll": 0.5},
            actor_context={"actor": "human", "active_browser_id": "a" * 32},
        )
        self.assertEqual(edited["rig_revision"], 1)
        self.assertFalse(self.service.control.status()["enabled"])

    def test_undo_does_not_resume_agent(self):
        self.service.command(self.run_id, 0, "1" * 32, "orient", {"bone_id": "elbow.L", "roll": 0.5})
        stopped = self.service.control.stop("user")
        undone, _ = self.service.command(self.run_id, 1, "2" * 32, "undo", {})
        self.assertEqual(undone["skeleton"], self.run["skeleton"])
        self.assertEqual(self.service.control.status(), stopped)

    def test_v2_migration_preserves_skin_and_arbitrary_roles(self):
        path = self.service.path(self.run_id)
        source = json.loads(path.read_bytes())
        source.pop("surface_landmarks", None)
        source["schema_version"] = 2
        source["skeleton"]["bones"][0].update(role="auxiliary_control", deform=False, roll=0.5)
        source["output"] = {"binding": "c" * 32, "material_count": 2}
        source["weight_locks"] = [source["skeleton"]["bones"][0]["id"]]
        original = json.dumps(source).encode()
        path.write_bytes(original)
        opened = self.service.get(self.run_id)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(opened["schema_version"], 3)
        self.assertEqual(opened["surface_landmarks"], [])
        for key in ("skeleton", "source", "output", "weight_locks"):
            self.assertEqual(opened[key], source[key])
        self.service.save(opened)
        self.assertEqual(path.with_suffix(".v2.json").read_bytes(), original)

    def test_batch_is_atomic_when_second_change_hits_a_pin(self):
        run, _ = self.service.command(self.run_id, 0, "a" * 32, "lock",
                                      {"bone_id": "elbow.R", "locked": True})
        context = self.service.admit(self.run_id, run["rig_revision"], {"actor": "human"})
        before = self.service.path(self.run_id).read_bytes()
        with self.assertRaisesRegex(ValueError, "Unlock"):
            self.service.preview_batch(context, [
                {"action": "orient", "args": {"bone_id": "elbow.L", "roll": 0.4}},
                {"action": "orient", "args": {"bone_id": "elbow.R", "roll": 0.6}},
            ])
        self.assertEqual(self.service.path(self.run_id).read_bytes(), before)

    def batch(self):
        context = self.admit_agent()
        preview = self.service.preview_batch(context, [
            {"action": "orient", "args": {"bone_id": "elbow.L", "roll": 0.4}},
            {"action": "label", "args": {"bone_id": "elbow.R", "label": "Right elbow"}},
        ])
        return context, preview

    def test_batch_undo_is_one_step_and_retry_is_idempotent(self):
        context, preview = self.batch()
        self.assertEqual(self.service.get(self.run_id), self.run)
        self.assertEqual(preview["changed_bone_ids"], ["elbow.L", "elbow.R"])
        new, first = self.service.commit_batch(context, preview["preview_id"], "d" * 32)
        self.assertEqual(first["applied_revision"], 1)
        self.assertEqual(len(new["undo"]), 1)
        self.service.control.stop("user")
        replay, receipt = self.service.commit_batch(context, preview["preview_id"], "d" * 32)
        self.assertEqual(new, replay)
        self.assertTrue(receipt["replayed"])
        self.assertTrue(receipt["applied_before_stop"])
        undone, _ = self.service.command(self.run_id, 1, "c" * 32, "undo", {})
        self.assertEqual(undone["skeleton"], self.run["skeleton"])

    def test_expired_preview(self):
        module = RigSessions.__module__
        with patch(f"{module}.time.monotonic", return_value=100):
            context, preview = self.batch()
        with patch(f"{module}.time.monotonic", return_value=221):
            with self.assertRaisesRegex(ValueError, "expired"):
                self.service.commit_batch(context, preview["preview_id"], "d" * 32)
        self.assertEqual(self.service.get(self.run_id), self.run)

    def test_human_edit_and_stop_invalidate_old_preview(self):
        context, preview = self.batch()
        self.service.command(self.run_id, 0, "c" * 32, "label", {"bone_id": "hips", "label": "Pelvis"})
        with self.assertRaisesRegex(ValueError, "rig changed"):
            self.service.commit_batch(context, preview["preview_id"], "d" * 32)
        context = self.service.admit(self.run_id, 1, {"actor": "agent", "agent_session_id": "f" * 32})
        preview = self.service.preview_batch(context, preview["commands"])
        self.service.control.stop("user")
        with self.assertRaisesRegex(ValueError, "stopped"):
            self.service.commit_batch(context, preview["preview_id"], "d" * 32)

    def test_branch_fit_and_undo_preserve_outside_bones_and_locks(self):
        run, _ = self.service.command(self.run_id, 0, "a"*32, "lock",
                                      {"bone_id":"elbow.L", "locked":True})
        before = {bone["id"]: bone for bone in run["skeleton"]["bones"]}
        tip = [a+b for a,b in zip(run["joints"]["fingers.L"],[.02, .01, .03])]
        args = {"root_id":"wrist.L","candidate_points":{"fingers.L":tip},"fixed_ids":["elbow.L"]}
        fitted, _ = self.service.command(self.run_id, 1, "b"*32, "refit_branch", args)
        after = {bone["id"]: bone for bone in fitted["skeleton"]["bones"]}
        self.assertEqual(fitted["joints"]["fingers.L"],tip)
        self.assertEqual(after["wrist.L"]["head"],before["wrist.L"]["head"])
        self.assertEqual({key:bone for key,bone in after.items() if key!="wrist.L"},
                         {key:bone for key,bone in before.items() if key!="wrist.L"})
        with self.assertRaisesRegex(ValueError, "attachment"):
            self.service.command(self.run_id, 2, "c"*32, "refit_branch",
                                 {**args,"candidate_points":{"wrist.L":tip}})
        reverted, _ = self.service.command(self.run_id, 2, "d"*32, "undo", {})
        self.assertEqual(reverted["skeleton"],run["skeleton"])
