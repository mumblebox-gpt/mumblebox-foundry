"""Smoke-check the standalone branch and GUI/MCP settings handoff."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.model_names import model_name
from foundry.workflows.orbit_to_mesh.definition import METHOD, OFFSET, SELECTION, defaults, settings, validate
from foundry.workflows.orbit_to_mesh.graph import compile_stage, template
from foundry.workflows.orbit_to_mesh.runs import OPERATIONS
from foundry.workflows.virtual_turntable.graph import template as turntable_template


class OrbitToMeshTests(unittest.TestCase):
    def setUp(self):
        controls = defaults()
        self.run = dict(id="smoke", name="Orbit smoke", method=METHOD, slug=METHOD, controls=controls,
                        settings=settings(controls, {}), selection=SELECTION,
                        references=[{"filename": "reference.png"}], exclude_views=[24],
                        checkpoints={"sheet": "sheet.png [output]", "orbit": "orbit.mp4",
                                     "cameras": "cameras.json", "views_manifest": "transforms.json",
                                     "decoded": "rough.glb", "front": "reference.png [output]",
                                     "clean": "clean.glb", "texture": "texture.glb", "balanced": "balanced.glb"})

    def test_native_canvas_is_independent(self):
        graph = template()
        self.assertFalse(set(graph) & set(turntable_template()))
        for item in graph.values():
            for value in item["inputs"].values():
                if isinstance(value, list):
                    self.assertIn(value[0], graph)
        self.assertEqual(graph[str(OFFSET + 64)]["inputs"]["manifest"], [str(OFFSET + 62), 0])

    def test_gui_number_round_trip_keeps_the_same_checkpoints(self):
        before = defaults()
        wire = {name: {key: int(value) if type(value) is float and value.is_integer() else value
                       for key, value in group.items()} for name, group in before.items()}
        self.assertEqual(json.dumps(validate(wire), sort_keys=True), json.dumps(before, sort_keys=True))

    def test_frames_remain_attached_to_saved_cameras(self):
        camera_graph = compile_stage("cameras", self.run)
        view_graph = compile_stage("views", self.run)
        mesh_graph = compile_stage("geometry", self.run)
        self.assertNotIn("MiniMaxH3ImageToVideo", {node["class_type"] for node in camera_graph.values()})
        self.assertEqual(view_graph[str(OFFSET + 61)]["inputs"]["manifest"], "cameras.json")
        self.assertEqual(mesh_graph[str(OFFSET + 64)]["inputs"]["manifest"], "transforms.json")
        self.assertEqual(mesh_graph[str(OFFSET + 64)]["inputs"]["exclude_source_frames"], "24")
        self.assertEqual(mesh_graph[str(OFFSET + 340)]["inputs"]["images"], [str(OFFSET + 2), 0])

    def test_rocket_and_package_finish_from_saved_stages(self):
        self.assertEqual(OPERATIONS["rocket"], ("turnaround", "orbit", "cameras", "views", "geometry", "refinement", "texture"))
        refine = compile_stage("refinement", self.run)
        self.assertEqual(refine[str(OFFSET + 2002)]["inputs"]["target_face_count"], 1_000_000)
        self.assertEqual(refine[str(OFFSET + 9101)]["inputs"]["image"], "reference.png [output]")
        package = compile_stage("package", self.run)
        self.assertEqual(package[str(OFFSET + 3010)]["inputs"]["saved_balanced"], "balanced.glb")
        self.assertIn(str(OFFSET + 3011), package)

    def test_cached_model_uses_repository_label(self):
        path = Path("models--example--clean-model/snapshots") / ("a" * 40) / "model.safetensors"
        self.assertEqual(model_name(None, {}, path), "clean model")


if __name__ == "__main__":
    unittest.main()
