"""Shared rig state, exact source ownership and conflict behavior."""
import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.library import Library
from foundry.workflows.rigging.sessions import RevisionConflict, RigSessions, current_output, public_state
from foundry.workflows.rigging.runtime import attach_output, wait_for_binding


def make_glb(low, high):
    data = {"accessors": [{"min": low, "max": high, "count": 3, "type": "VEC3"}],
            "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}
    payload = json.dumps(data).encode()
    payload += b" " * (-len(payload) % 4)
    return struct.pack("<4sIII4s", b"glTF", 2, 20 + len(payload), len(payload), b"JSON") + payload


class RiggingTests(unittest.TestCase):
    def test_rig_package_preserves_bone_document_and_metadata_revision(self):
        from foundry.workflows.rigging.runtime import binding_path

        module = types.ModuleType("rig_export_test")
        module.__path__ = [str(Path(__file__).resolve().parents[1])]
        with patch.dict(sys.modules, {module.__name__:module}):
            publish = importlib.import_module("rig_export_test.foundry.workflows.rigging.package").publish

        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        binding = "f" * 32
        stage = binding_path(self.service, run["id"], binding)
        stage.mkdir(parents=True)
        (stage/"rig.glb").write_bytes(self.first)
        bound = attach_output(self.service, run, {"glb_sha256":hashlib.sha256(self.first).hexdigest(), "report":{
            "bones":17,"triangles":1,"vertices":3,"unweighted":0,"nearest_segment_vertices":0,
            "pose_seconds":{"rest":0},"blender":"5.2.2",
        }}, binding)
        first = publish(self.service, bound)
        with ZipFile(next(stage.glob("*.zip"))) as archive:
            data = json.loads(archive.read("Metadata/rig.json"))
            self.assertEqual(data["bones"], bound["skeleton"]["bones"])
            self.assertEqual(data["bone_count"], 17)
        edited, _ = self.service.command(run["id"], bound["rig_revision"], "d"*32, "label",
                                         {"bone_id":"hips", "label":"Pelvis"})
        second = publish(self.service, edited)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(publish(self.service, edited)["id"], second["id"])
        (stage/"rig.glb").write_bytes(b"corrupt")
        edited, _ = self.service.command(run["id"], edited["rig_revision"], "e"*32, "label",
                                         {"bone_id":"hips", "label":"Pelvis moved"})
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            publish(self.service, edited)

    def test_detailed_hierarchy_round_trips_with_same_bone_identities(self):
        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        bones = [
            {"id": f"bone_{i}", "label": f"Bone {i}", "parent_id": f"bone_{i-1}" if i else None,
             "head": [0, i / 50, 0], "tail": [0, (i+1) / 50, 0], "roll": .3 if i == 51 else 0,
             "deform": True, "connected": bool(i)}
            for i in range(52)
        ]
        self.assertTrue(hasattr(self.service, "replace_skeleton"), "Detailed predictions need a lossless save path")
        updated = self.service.replace_skeleton(run["id"], run["revision"], bones, {"method": "local_ai"})
        reopened = RigSessions(self.service.root, self.library).get(updated["id"])
        self.assertEqual(reopened["schema_version"], 3)
        self.assertEqual(len(reopened["skeleton"]["bones"]), 52)
        self.assertEqual(reopened["skeleton"]["bones"][-1], bones[-1])
        self.assertEqual(reopened["source"]["sha256"], run["source"]["sha256"])
        state = public_state(reopened)
        self.assertEqual(state["joints"]["bone_51"], [0, 1.02, 0])
        self.assertEqual(state["chains"][-1][2], "bone_50")

    def test_invalid_replacement_leaves_original_saved_state(self):
        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        self.assertTrue(hasattr(self.service, "replace_skeleton"), "Detailed predictions need a validated save path")
        invalid = [{"id": "root", "parent_id": "root", "head": [0, 0, 0], "tail": [0, 1, 0]}]
        before = self.service.path(run["id"]).read_bytes()
        with self.assertRaises(ValueError):
            self.service.replace_skeleton(run["id"], run["revision"], invalid, {"method": "local_ai"})
        self.assertEqual(self.service.path(run["id"]).read_bytes(), before)

    def test_learned_weight_domain_stays_valid_only_for_the_predicted_geometry(self):
        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        bones = [{"id": "root", "head": [0, 0, 0], "tail": [0, 1, 0], "parent_id": None}]
        fit = {"method": "local_ai", "prediction_id": "a"*32, "weights_sha256": "b"*64}
        detailed = self.service.replace_skeleton(run["id"], run["revision"], bones, fit)
        from foundry.workflows.rigging import runtime
        self.assertTrue(hasattr(runtime, "binding_method"), "Keep learned weights with their predicted geometry")
        self.assertEqual(runtime.binding_method(detailed), "learned")
        edited = self.service.edit(run["id"], detailed["revision"], "move", joint="root", point=[0, .1, 0])
        self.assertEqual(runtime.binding_method(edited), "voxel")
        restored = self.service.edit(run["id"], edited["revision"], "undo")
        self.assertEqual(runtime.binding_method(restored), "learned")

    def test_exported_skin_must_retain_parentage_and_every_bone(self):
        from foundry.workflows.rigging import runtime
        self.assertTrue(hasattr(runtime, "verify_exported_skeleton"), "Validate actual GLB hierarchy before attaching")
        expected = [{"id": "root", "parent_id": None, "head": [0,0,0], "tail": [0,1,0]},
                    {"id": "finger", "parent_id": "root", "head": [0,1,0], "tail": [0,2,0]}]
        gltf = {"nodes": [{"name": "root", "children": [1]}, {"name": "finger", "translation": [0,1,0]}],
                "skins": [{"joints": [0, 1]}]}
        runtime.verify_exported_skeleton(gltf, expected)
        gltf['nodes'][1]['translation'] = [0,1,.1]
        with self.assertRaisesRegex(ValueError, 'rest position'):
            runtime.verify_exported_skeleton(gltf, expected)
        gltf['nodes'][1]['translation'] = [0,1,0]
        gltf['nodes'][1]['rotation'] = [.70710678,0,0,.70710678]
        with self.assertRaisesRegex(ValueError, 'rest direction'):
            runtime.verify_exported_skeleton(gltf, expected)
        gltf['nodes'][1].pop('rotation')
        gltf["nodes"][0].pop("children")
        with self.assertRaises(ValueError):
            runtime.verify_exported_skeleton(gltf, expected)
        gltf["nodes"][0]["children"] = [1]
        gltf["skins"][0]["joints"].pop()
        with self.assertRaises(ValueError):
            runtime.verify_exported_skeleton(gltf, expected)

    def test_shared_add_chain_replays_once_across_reload_and_undo_restores_ids(self):
        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        self.assertTrue(hasattr(self.service, "command"), "Structural edits need a shared transactional API")
        args = {"parent_id": "hips", "points": [[0, 1, 0], [0, 1, .2], [0, 1, .4]], "part": "tail"}
        key = "a" * 32
        added, receipt = self.service.command(run["id"], 0, key, "add_chain", args)
        self.assertEqual(len(added["skeleton"]["bones"]), 19)
        chain_ids = [bone["id"] for bone in added["skeleton"]["bones"][-2:]]
        self.assertEqual(added["skeleton"]["bones"][-1]["parent_id"], chain_ids[0])
        restarted = RigSessions(self.service.root, self.library)
        replayed, same_receipt = restarted.command(run["id"], 0, key, "add_chain", args)
        self.assertEqual(receipt, same_receipt)
        self.assertEqual(len(replayed["skeleton"]["bones"]), 19)
        with self.assertRaises(ValueError):
            restarted.command(run["id"], 0, key, "add_chain", {**args, "part": "wing"})
        with self.assertRaises(RevisionConflict):
            restarted.command(run["id"], 0, "b"*32, "remove_chain", {"bone_id": chain_ids[0]})
        undone, _ = restarted.command(run["id"], 1, "c"*32, "undo", {})
        self.assertEqual(len(undone["skeleton"]["bones"]), 17)
        redone, _ = restarted.command(run["id"], 2, "d"*32, "redo", {})
        self.assertEqual([bone["id"] for bone in redone["skeleton"]["bones"][-2:]], chain_ids)

    def test_legacy_session_is_projected_without_rewriting_on_read(self):
        from foundry.workflows.rigging.geometry import template
        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        legacy = {key: run[key] for key in ("id", "source", "bounds", "vertices", "orientation",
                                            "selected_joint", "pose", "step", "undo", "output", "revision")}
        legacy["joints"] = template(run["bounds"])
        legacy["joints"]["elbow.L"][2] = .125
        path = self.service.path(run["id"])
        original = json.dumps(legacy).encode()
        path.write_bytes(original)
        state = self.service.get(run["id"])
        self.assertEqual(state.get("schema_version"), 3)
        self.assertEqual(len(state["skeleton"]["bones"]), 17)
        self.assertEqual(state["joints"]["elbow.L"][2], .125)
        self.assertEqual(path.read_bytes(), original)
        self.service.edit(run["id"], state["revision"], "select", joint="knee.L")
        self.assertEqual(path.with_suffix(".v1.json").read_bytes(), original)

    def test_binding_cancel_stops_only_its_worker_and_timeout_is_bounded(self):
        worker=Mock()
        with self.assertRaisesRegex(InterruptedError, 'preserved'):
            wait_for_binding(worker, cancelled=lambda:True)
        worker.stop.assert_called_once()
        worker.process.wait.assert_not_called()
        worker=Mock()
        with patch('foundry.workflows.rigging.runtime.time.monotonic',side_effect=[10,251]):
            with self.assertRaisesRegex(ValueError,'lighter mesh'):
                wait_for_binding(worker)
        worker.stop.assert_called_once()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.library = Library(root / "state", root / "output")
        self.service = RigSessions(self.library.root / "rigging", self.library)
        package = self.library.output_root / "work"
        (package / "Metadata").mkdir(parents=True)
        self.first = make_glb([-1, 0, -.2], [1, 2, .2])
        self.second = make_glb([-1, 3, -.2], [1, 6, .2])
        self.sources = {"first.glb": self.first, "second.glb": self.second}
        manifest = {"schema": "mumblebox.asset-catalog/2", "export_id": "mesh1",
                    "asset_name": "Character", "created_utc": "2026-11-16T00:00:00Z",
                    "files": [], "variants": []}
        for name, data in self.sources.items():
            (package / name).write_bytes(data)
            manifest["files"].append({"path": name, "kind": "mesh", "format": "glb", "variant_id": name})
        (package / "Metadata/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with ZipFile(package.with_suffix(".zip"), "w") as archive:
            for path in package.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(package).as_posix())
        self.id = self.library.import_package(package.with_suffix(".zip"))["id"]

    def test_exact_file_and_undo_survive_new_service_instance(self):
        choices = self.service.sources(self.id)
        run = self.service.create(self.id, choices[1]["id"])
        self.assertEqual(run["source"]["name"], "second.glb")
        self.assertEqual(run["bounds"][0][1], 3)
        previous = run["joints"]["elbow.L"]
        position = [previous[0] + .1, previous[1], previous[2]]
        edited = self.service.edit(run["id"], run["revision"], "move", joint="elbow.L", point=position, mirror=True)
        self.assertAlmostEqual(edited["joints"]["elbow.R"][0], -position[0])
        restarted = RigSessions(self.service.root, self.library)
        self.assertEqual(restarted.get(run["id"])["joints"]["elbow.L"], position)
        result = restarted.edit(run["id"], edited["revision"], "undo")
        self.assertEqual(result["joints"]["elbow.L"], previous)
        self.assertEqual(self.service.source_path(result).read_bytes(), self.second)

    def test_interrupted_atomic_save_keeps_rig_and_allows_retry(self):
        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        target = self.service.path(run["id"])
        before = target.read_bytes()
        request_id = "2" * 32
        with patch.object(type(target), "replace", side_effect=OSError("interrupted before rename")):
            with self.assertRaises(OSError):
                self.service.command(run["id"], run["rig_revision"], request_id, "label",
                                     {"bone_id":"hips", "label":"Pelvis"})
        self.assertEqual(target.read_bytes(), before)
        saved, receipt = self.service.command(run["id"], run["rig_revision"], request_id, "label",
                                              {"bone_id":"hips", "label":"Pelvis"})
        self.assertEqual(saved["skeleton"]["bones"][0]["label"], "Pelvis")
        self.assertEqual(receipt["rig_revision"], run["rig_revision"] + 1)

    def test_role_edit_requires_new_pose_output_without_changing_fitted_geometry(self):
        from foundry.workflows.rigging.sessions import skeleton_key

        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        bound = attach_output(self.service, run, {"report": {}}, "f"*32)
        edited, receipt = self.service.command(run["id"], bound["rig_revision"], "3"*32, "role",
                                               {"bone_id":"hips", "role":"finger", "digit":"thumb"})
        self.assertEqual(skeleton_key(edited), skeleton_key(bound))
        self.assertEqual(edited["skeleton"]["bones"][0]["anatomical_name"], "thumb")
        self.assertTrue(receipt["binding_stale"])
        restored, _ = self.service.command(run["id"], edited["rig_revision"], "4"*32, "undo", {})
        self.assertIsNotNone(current_output(restored))

    def test_invalid_source_and_stale_agent_edit_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.create(self.id, "archive")
        file_id = hashlib.sha256(b"first.glb").hexdigest()[:24]
        first = self.service.create(self.id, file_id)
        second = self.service.edit(first["id"], 0, "select", joint="knee.L")
        with self.assertRaises(RevisionConflict):
            self.service.edit(first["id"], 0, "move", joint="elbow.L", point=[0, 1, 0])
        self.assertEqual(self.service.get(first["id"]), second)

    def test_binding_stays_current_across_selection_but_not_joint_edits(self):
        first = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        result = attach_output(self.service, first, {"file": "rig.glb", "report": {}}, "binding")
        selected = self.service.edit(first["id"], result["revision"], "select", joint="knee.L")
        self.assertEqual(current_output(selected)["binding"], "binding")
        changed = self.service.edit(first["id"], selected["revision"], "move",
                                    joint="knee.L", point=[.1, 1, 0])
        self.assertIsNone(current_output(changed))
        with self.assertRaises(RevisionConflict):
            attach_output(self.service, selected, {"file": "old.glb", "report": {}}, "old")
        restored = self.service.edit(first["id"], changed["revision"], "undo")
        self.assertEqual(current_output(restored)["binding"], "binding")

    def test_wizard_step_persists_and_export_requires_current_binding(self):
        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        self.assertEqual(public_state(run)["step"], "fit")
        with self.assertRaisesRegex(ValueError, "Bind"):
            self.service.edit(run["id"], run["revision"], "step", step="export")
        review = self.service.edit(run["id"], run["revision"], "step", step="review")
        restarted = RigSessions(self.service.root, self.library)
        self.assertEqual(public_state(restarted.get(run["id"]))["step"], "review")
        bound = attach_output(self.service, review, {"file":"rig.glb", "report":{}}, "binding")
        exported = self.service.edit(run["id"], bound["revision"], "step", step="export")
        self.assertEqual(public_state(exported)["step"], "export")
        moved = self.service.edit(run["id"], exported["revision"], "move", joint="elbow.L", point=[.1,1,0])
        self.assertEqual(public_state(moved)["step"], "fit")
        self.assertIsNone(current_output(moved))

    def test_return_to_fitting_restores_rest_pose_and_guards_revision(self):
        run = self.service.create(self.id, self.service.sources(self.id)[0]["id"])
        bound = attach_output(self.service, run, {"file":"rig.glb", "report":{}}, "binding")
        posed = self.service.edit(run["id"], bound["revision"], "pose", pose="elbow")
        fitting = self.service.edit(run["id"], posed["revision"], "step", step="fit")
        self.assertEqual(fitting["pose"], "rest")
        self.assertIsNotNone(current_output(fitting))
        with self.assertRaises(RevisionConflict):
            self.service.edit(run["id"], posed["revision"], "step", step="export")
        with self.assertRaisesRegex(ValueError, "step"):
            self.service.edit(run["id"], fitting["revision"], "step", step="anything")


if __name__ == "__main__":
    unittest.main()
