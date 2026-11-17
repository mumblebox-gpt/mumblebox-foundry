from pathlib import Path
import json
import tempfile
import sys
import unittest

RIG = Path(__file__).resolve().parents[1] / "foundry/workflows/rigging"
sys.path.insert(0, str(RIG))


class RiggingMethodTests(unittest.TestCase):
    def test_neural_conditioning_keeps_stable_ids_with_out_of_order_branches(self):
        import tokenrig_worker
        self.assertTrue(hasattr(tokenrig_worker, "conditioning_order"), "Use the rig document as explicit input")
        supplied = [
            {"id":"finger","parent_id":"hand","head":[0,2,0]},
            {"id":"root","parent_id":None,"head":[0,0,0]},
            {"id":"hand","parent_id":"root","head":[0,1,0]},
            {"id":"tail","parent_id":"root","head":[0,0,1]},
        ]
        bones, parents = tokenrig_worker.conditioning_order(supplied)
        self.assertEqual([bone["id"] for bone in bones], ["root","hand","finger","tail"])
        self.assertEqual(parents, [-1,0,1,0])
        with self.assertRaisesRegex(ValueError, "one root"):
            tokenrig_worker.conditioning_order([*supplied,{"id":"other","parent_id":None,"head":[1,0,0]}])

    def test_prediction_retains_every_branch_and_rejects_missing_learned_weights(self):
        sys.path.insert(0, str(RIG.parents[2]))
        from foundry.workflows.rigging import document

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            result = {"source_sha256": "a"*64, "joints": [[0, 0, 0], [0, 1, 0], [.2, 1.2, 0], [-.2, 1.2, 0]],
                      "parents": [-1, 0, 1, 1], "samples": 128, "seconds": 4.1, "cuda_allocated_bytes": 4194304}
            (folder/"prediction.json").write_text(json.dumps(result), encoding="utf-8")
            self.assertTrue(hasattr(document, "read_prediction"), "Validate learned skin and retain raw hierarchy")
            with self.assertRaisesRegex(ValueError, "weights"):
                document.read_prediction(folder, "a"*64)
            (folder/"weights.npz").write_bytes(b"PK\x03\x04" + b"artifact placeholder")
            bones, receipt = document.read_prediction(folder, "a"*64)
            self.assertEqual([bone["parent_id"] for bone in bones], [None, "bone_0", "bone_1", "bone_1"])
            self.assertEqual(bones[3]["head"], [-.2, 1.2, 0])
            self.assertEqual(receipt["weight_samples"], 128)
            with self.assertRaisesRegex(ValueError, "source"):
                document.read_prediction(folder, "b"*64)

    def test_presets_resolve_and_custom_rejects_invalid_settings(self):
        from methods import bind_settings, fit_settings

        self.assertEqual(fit_settings("standard", {})["num_beams"], 10)
        self.assertLess(fit_settings("quick", {})["num_beams"], 10)
        self.assertEqual(fit_settings("custom", {"seed": 5, "top_p": 0.8})["seed"], 5)
        self.assertEqual(bind_settings("standard", {}), {"proxy_resolution": 110})
        self.assertEqual(bind_settings("custom", {"proxy_resolution": 96}), {"proxy_resolution": 96})
        for change in ({"num_beams": True}, {"top_p": float("nan")}, {"num_beams": 99}, {"fake": 0}):
            with self.assertRaises(ValueError):
                fit_settings("custom", change)
        with self.assertRaises(ValueError):
            fit_settings("standard", {"seed": 7})

    def test_fit_maps_a_complete_hierarchy_and_rejects_missing_arm(self):
        from fit_mapping import map_humanoid

        # Center, both legs, two separate shoulder branches and head.
        vertices = [[0, .5, 0], [0, .61, 0], [0, .75, 0], [0, .86, 0], [0, .94, 0]]
        parents = [-1, 0, 1, 2, 3]
        for side in (1, -1):
            first = len(vertices)
            vertices += [[side*.1,.49,0],[side*.13,.27,.03],[side*.14,.06,0],[side*.15,.025,.09]]
            parents += [0, first, first+1, first+2]
            first = len(vertices)
            vertices += [[side*.16,.78,0],[side*.27,.66,0],[side*.35,.54,0],[side*.40,.48,.02]]
            parents += [2, first, first+1, first+2]
        bounds = [[-.43,0,-.16],[.43,1,.16]]
        joints = map_humanoid(vertices, parents, bounds, 0)
        self.assertEqual(joints["elbow.L"], [.27,.66,0])
        self.assertEqual(joints["knee.R"], [-.13,.27,.03])
        self.assertEqual(len(joints), 22)
        rotated = [[p[2], p[1], -p[0]] for p in vertices]
        self.assertEqual(map_humanoid(rotated, parents, [[-.16,0,-.43],[.16,1,.43]], 1)["elbow.L"], [0,.66,-.27])
        with self.assertRaises(ValueError):
            map_humanoid(vertices[:-4], parents[:-4], bounds, 0)


if __name__ == "__main__":
    unittest.main()
