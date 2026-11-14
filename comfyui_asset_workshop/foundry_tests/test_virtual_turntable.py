"""Virtual Turntable graph and wizard contracts."""
import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.workflows.orbit_to_mesh.definition import defaults as pixal_defaults
from foundry.workflows.virtual_turntable.camera_validation import orbit_coverage
from foundry.workflows.virtual_turntable.definition import validated_settings
from foundry.workflows.virtual_turntable.graph import OFFSET, compile_stage


class VirtualTurntableTests(unittest.TestCase):
    def setUp(self):
        self.run = {"id": "a" * 32, "engine": "meshroom",
                    "references": [{"filename": "reference.png"}], "controls": validated_settings({}),
                    "checkpoints": {"sheet": "sheet.png [output]", "orbit": "orbit.mp4", "project": "project"}}

    def test_reconstruction_reuses_saved_orbit_and_only_queues_the_selected_engine(self):
        for engine, expected in (("meshroom", "FoundryV360Meshroom"),
                                 ("colmap-openmvs", "FoundryV360COLMAPOpenMVS")):
            with self.subTest(engine=engine):
                run = dict(self.run, engine=engine)
                graph = compile_stage("geometry", run)
                types = {node["class_type"] for node in graph.values()}
                self.assertEqual(types & {"FoundryV360Meshroom", "FoundryV360COLMAPOpenMVS"}, {expected})
                self.assertNotIn("UNETLoader", types)
                self.assertEqual(graph[str(OFFSET + 45)]["inputs"]["saved_video"], "orbit.mp4")
                self.assertLess(len(graph[str(OFFSET + 48)]["inputs"]["asset_name"]), 24)

    def test_shared_prompt_and_video_controls(self):
        self.assertEqual(self.run["controls"]["orbit"]["prompt"], pixal_defaults()["orbit"]["prompt"])
        self.run["controls"]["orbit"].update(denoise=.8, decode_overlap=32, chunk_threshold=8192)
        graph = compile_stage("orbit", self.run)
        self.assertEqual(graph[str(OFFSET + 39)]["inputs"]["denoise"], .8)
        self.assertEqual(graph[str(OFFSET + 41)]["inputs"]["overlap"], 32)
        with self.assertRaises(ValueError):
            validated_settings({"orbit": {"decode_tile": 128, "decode_overlap": 96}})

    def test_prepared_frames_are_reused_by_both_engines(self):
        frames = compile_stage("frames", self.run)
        self.assertEqual(frames[str(OFFSET + 48)]["inputs"]["source_timing"], [str(OFFSET + 45), 2])
        self.assertFalse(any(node["class_type"] in {"FoundryV360Meshroom", "FoundryV360COLMAPOpenMVS"}
                             for node in frames.values()))
        self.run["checkpoints"]["frame_set"] = "prepared"
        for engine in ("meshroom", "colmap-openmvs"):
            graph = compile_stage("geometry", dict(self.run, engine=engine))
            self.assertEqual(graph[str(OFFSET + 58)]["inputs"]["saved_folder"], "prepared")
            self.assertNotIn(str(OFFSET + 45), graph)

    def test_camera_gap_uses_measured_centers_and_preserves_source_timing(self):
        frame_set = {"count": 7, "source_indices": [2, 4, 6, 8, 10, 12, 14],
                     "source_video": {"timestamps_seconds": [.1, .2, .3, .4, .5, .6, .7]}}
        centers = {f"frame_{i:05d}.png": [2 + math.cos(math.radians(angle)),
                    4 + math.sin(math.radians(angle)), 3]
                   for i, angle in enumerate(range(0, 270, 45))}
        report = orbit_coverage(frame_set, centers)
        self.assertEqual(report["largest_gap_degrees"], 135)
        self.assertEqual(report["registered_frames"], 6)
        self.assertEqual(report["registered_timestamps_seconds"], [.1, .2, .3, .4, .5, .6])

    def test_243_frame_preset_and_invalid_frame_counts(self):
        self.assertEqual(validated_settings({"orbit": {"length": 243}})["orbit"]["length"], 243)
        with self.assertRaises(ValueError):
            validated_settings({"orbit": {"length": 80}})

    def test_openmvs_reduces_before_projection_and_can_keep_full_density(self):
        run = dict(self.run, engine="colmap-openmvs")
        graph = compile_stage("texture", run)
        reduction = graph[str(OFFSET + 75)]
        self.assertEqual(reduction["inputs"]["target_face_count"], 200000)
        self.assertEqual(graph[str(OFFSET + 72)]["inputs"]["mesh_obj"], [str(OFFSET + 76), 1])
        self.assertEqual(graph[str(OFFSET + 74)]["inputs"]["model"], [str(OFFSET + 69), 0])

        run["controls"]["openmvs_finish"]["texture_triangle_target"] = 0
        graph = compile_stage("texture", run)
        self.assertNotIn(str(OFFSET + 75), graph)
        self.assertEqual(graph[str(OFFSET + 72)]["inputs"]["mesh_obj"], [str(OFFSET + 69), 1])

    def test_refinement_is_optional_and_source_photo_projection_is_retained(self):
        self.assertNotIn("Hi3DRefine", {node["class_type"] for node in compile_stage("texture", self.run).values()})
        run = copy.deepcopy(self.run)
        run["controls"]["refinement"]["refine"] = True
        types = {node["class_type"] for node in compile_stage("texture", run).values()}
        self.assertIn("Hi3DRefine", types)
        self.assertIn("UnwrapMesh", types)
        self.assertIn("FoundryV360RetextureRefinement", types)


if __name__ == "__main__":
    unittest.main()
