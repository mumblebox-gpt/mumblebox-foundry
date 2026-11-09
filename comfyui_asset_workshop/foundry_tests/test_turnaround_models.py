"""No-inference checks of the selected turnaround and shared mesh boundary."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

class TurnaroundModels(unittest.TestCase):
    def refs(self, count=1):
        return [dict(id=str(i), filename=f"reference-{i}.png", role="primary" if i == 0 else "back",
                     description="" if i == 0 else "Rear of the same asset") for i in range(count)]

    def test_every_category_and_model_produces_only_the_selected_branch(self):
        from foundry.workflows.image_to_3d.turnaround import MODEL_IDS, model_spec
        from foundry.workflows.image_to_3d.definition import CATEGORIES, DEFAULTS
        from foundry.workflows.image_to_3d.graph import compile_stage
        for model in MODEL_IDS:
            for category in CATEGORIES:
                with self.subTest(model=model, category=category["id"]):
                    self.assertTrue(category["qualified"])
                    run=dict(name="Contract", slug="contract", id="a"*32, settings=copy.deepcopy(DEFAULTS),
                             category=category["id"], references=self.refs(2), turnaround_model=model)
                    graph=compile_stage("turnaround", run)
                    loaders=[n for n in graph.values() if n["class_type"] == "UNETLoader"]
                    self.assertEqual(len(loaders), 1)
                    self.assertEqual(loaders[0]["inputs"]["unet_name"], model_spec(model)["files"]["model"])
                    self.assertTrue(all(key in graph for key in ("412","340","344","343","346")))
                    self.assertFalse(any("Hi3D" in n["class_type"] for n in graph.values()))
                    self.assertEqual(graph["1556"]["inputs"]["width"],4096)
                    self.assertEqual(graph["1556"]["inputs"]["height"],1024)

    def test_reference_tokens_and_limits_match_the_encoder(self):
        from foundry.workflows.image_to_3d.prompts import bind_references, CHARACTER_PROMPT
        self.assertEqual(bind_references("characters",self.refs(),"qwen21")["prompt"], CHARACTER_PROMPT)
        for model, token in (("qwen21","<image2>"),("qwen2511","Picture 2"),
                             ("klein4","image 2"),("flux3_distilled","<ref_image_1>")):
            self.assertIn(token,bind_references("props",self.refs(2),model)["prompt"])
        with self.assertRaisesRegex(ValueError,"three|3"):
            bind_references("props",self.refs(4),"qwen2511")
        with self.assertRaises(ValueError):bind_references("props",self.refs(),"not-a-model")

    def test_nonhumanoid_instructions_do_not_impose_a_t_pose(self):
        from foundry.workflows.image_to_3d.prompts import bind_references
        for category, term in (("creatures","limb"),("vehicles","wheel"),("props","attached"),("environment","single")):
            prompt=bind_references(category,self.refs(),"qwen21")["prompt"]
            self.assertIn(term,prompt.lower())
            self.assertNotIn("T-pose",prompt)

    def test_model_dependencies_and_provenance_do_not_include_unselected_qwen(self):
        from foundry.workflows.image_to_3d.turnaround import model_spec, dependency_keys
        for model in ("qwen2511","klein4","flux3_base"):
            spec=model_spec(model)
            self.assertNotIn("qwen21",dependency_keys(model))
            self.assertNotIn("qwen21",spec["resources"])
            self.assertTrue(spec["license_url"].startswith("https://"))
            self.assertIn(model,dependency_keys(model))

    def test_every_exposed_resource_has_a_retained_notice_and_matching_terms(self):
        import json
        from foundry.workflows.image_to_3d.turnaround import MODEL_IDS, model_spec
        root=Path(__file__).resolve().parents[2]
        registry=json.loads((root/"comfyui_asset_workshop/finishing/package_resources.json").read_text(encoding="utf-8"))
        for model in MODEL_IDS:
            spec=model_spec(model)
            for key in spec["resources"]:
                with self.subTest(model=model,resource=key):
                    resource=registry[key]
                    self.assertTrue(resource["notices"])
                    for notice in resource["notices"]:
                        self.assertTrue((root/"comfyui_asset_workshop/licenses/pipeline"/notice).is_file())
            if model!="qwen21":
                self.assertEqual(registry[model]["license_url"],spec["license_url"])
                self.assertEqual(registry[model]["license"],spec["license"])

if __name__ == "__main__":unittest.main()
