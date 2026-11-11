"""CCORE creative brief schema and accepted text."""
import importlib.util
import json
from pathlib import Path
import unittest

path = Path(__file__).parents[1] / "foundry/workflows/ccore_prop/enhancement.py"


def module():
    if not path.is_file():
        raise AssertionError("The CCORE creative brief contract is missing.")
    spec = importlib.util.spec_from_file_location("ccore_enhancement", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def brief(contract):
    value = {key: "" for key in contract.BRIEF_FIELDS}
    value.update(subject="A static lantern", shape="Tapered cage", style="Nautical",
                 requirements=["Exactly four copper ribs"],
                 parts=[dict.fromkeys(contract.PART_FIELDS, "")],
                 enhanced_prompt="Create a static tapered lantern with exactly four copper ribs.")
    value["parts"][0].update(name="Cage ribs", count="4", material="Copper")
    return value


class CcoreEnhancementTests(unittest.TestCase):
    def test_returns_complete_editable_description(self):
        contract = module()
        value = brief(contract)
        self.assertEqual(contract.parse_brief(json.dumps(value)), value["enhanced_prompt"])

    def test_rejects_incomplete_or_malformed_briefs(self):
        contract = module()
        value = brief(contract)
        for bad in ("not JSON", json.dumps({"enhanced_prompt": "A lantern"}),
                    json.dumps(dict(value, enhanced_prompt=" ")),
                    json.dumps(dict(value, enhanced_prompt="x" * 5001)),
                    json.dumps(dict(value, parts=[{"material": "Copper"}]))):
            with self.subTest(bad=bad[:80]), self.assertRaisesRegex(ValueError, "usable"):
                contract.parse_brief(bad)

    def test_translation_has_a_separate_literal_contract(self):
        contract = module()
        result = "An olive radio with exactly two cream dials and no lettering."
        self.assertEqual(contract.parse_translation(json.dumps({"translated_prompt": result})), result)
        for bad in ("not JSON", json.dumps({"enhanced_prompt": result}),
                    json.dumps({"translated_prompt": " "}),
                    json.dumps({"translated_prompt": "<think>text</think>"}),
                    json.dumps({"translated_prompt": result, "extra": "invented"})):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                contract.parse_translation(bad)
        self.assertIn("Do not add", contract.TRANSLATION_SYSTEM)
        self.assertIn("counts", contract.TRANSLATION_SYSTEM)

    def test_translation_precision_is_explicit_and_has_one_default_owner(self):
        contract = module()
        base = {"request_id": "a" * 32, "prompt": "橄榄绿色的电台"}
        self.assertEqual(contract.default_translation_precision(), "q4")
        self.assertEqual(contract.translation_input(base)[2], "q4")
        for precision in ("q4", "q8"):
            self.assertEqual(contract.translation_input(dict(base, precision=precision))[2], precision)
        for invalid in ("q2", "cpu", None, 4):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                contract.translation_input(dict(base, precision=invalid))

    def test_validates_request_before_model_work(self):
        contract = module()
        ident = "a" * 32
        self.assertEqual(contract.enhancement_input({"request_id": ident, "prompt": "   A lantern  "}),
                         (ident, "A lantern"))
        for value in ("", "  ", "x" * 5001, None):
            with self.subTest(value=str(value)[:10]), self.assertRaises(ValueError):
                contract.enhancement_input({"request_id": ident, "prompt": value})
        with self.assertRaises(ValueError):
            contract.enhancement_input({"request_id": "wrong", "prompt": "A lantern"})
