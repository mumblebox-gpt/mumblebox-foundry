"""Localization contracts that protect stored inputs and locale compatibility."""
from collections import Counter
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foundry.localization import MANIFEST, PLACEHOLDER, ROOT, catalog, locale_name, source_message, translate
from foundry.preferences import Preferences


class LocalizationTests(unittest.TestCase):
    def test_shared_catalogs_have_the_same_keys_and_placeholders(self):
        for domain, relative in MANIFEST["domains"].items():
            directory = ROOT / relative
            english = json.loads((directory / "en.json").read_text(encoding="utf-8-sig"))
            for language in MANIFEST["languages"]:
                locale = language["id"]
                with self.subTest(domain=domain, locale=locale):
                    translated = json.loads((directory / (locale + ".json")).read_text(encoding="utf-8-sig"))
                    self.assertEqual(english.keys(), translated.keys())
                    for key, text in translated.items():
                        self.assertIsInstance(text, str, key)
                        self.assertTrue(text.strip(), key)
                        self.assertEqual(Counter(PLACEHOLDER.findall(english[key])),
                                         Counter(PLACEHOLDER.findall(text)), key)

    def test_named_values_preserve_user_text(self):
        reference = "<script>Settings</script> 发型"
        actual = translate("hair.hairdeck_reference", {"label": reference}, "zh-CN")
        self.assertIn(reference, actual)
        self.assertEqual(translate("unknown.message", locale="zh-CN"), "unknown.message")
        with self.assertRaises(ValueError):
            translate("hair.hairdeck_reference", locale="zh-CN")

    def test_language_preference_preserves_existing_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = Preferences(Path(directory) / "preferences.json")
            owner.update({"theme": "dark", "font_size": "200", "model_sort": "size_desc"})
            owner.update({"language": "zh-CN"})
            saved = owner.read()
            self.assertEqual(saved["language"], "zh-CN")
            self.assertEqual(saved["theme"], "dark")
            self.assertEqual(saved["font_size"], "200")
            self.assertEqual(saved["model_sort"], "size_desc")
            with self.assertRaises(ValueError):
                owner.update({"language": "../../bad"})
            self.assertEqual(owner.read(), saved)

    def test_older_unknown_locales_fall_back_to_english(self):
        self.assertEqual(locale_name("zh"), "en")
        self.assertEqual(locale_name(None), "en")

    def test_error_metadata_does_not_rewrite_original_diagnostics(self):
        original = "Choose an available generation budget."
        token = source_message(original)
        self.assertIsNotNone(token)
        self.assertNotEqual(translate(token["key"], token["values"], "zh-CN"), original)
        self.assertEqual(original, "Choose an available generation budget.")

    def test_unknown_diagnostics_are_not_captured_by_parameter_only_messages(self):
        self.assertIsNone(source_message("unrecognized diagnostic /data/file.glb"))

    def test_translation_memory_guidance_is_localized(self):
        for source in ("Choose Q4 or Q8 for translation.", "Preparing description assistant"):
            token=source_message(source)
            self.assertIsNotNone(token)
            self.assertNotEqual(translate(token["key"], token["values"], "zh-CN"),source)

    def test_builtin_presets_mirror_the_authoritative_english_examples(self):
        source = Path(__file__).resolve().parents[1] / "foundry/workflows/ccore_prop/examples.json"
        examples = json.loads(source.read_text(encoding="utf-8-sig"))
        for example in examples:
            for field in ("name", "category", "prompt"):
                key = "ccore.preset_" + example["id"] + "_" + field
                self.assertEqual(translate(key), example[field])
                for language in MANIFEST["languages"]:
                    locale = language["id"]
                    if locale != "en":
                        with self.subTest(locale=locale, key=key):
                            self.assertNotEqual(translate(key, locale=locale), example[field])

    def test_generation_instruction_is_outside_the_ui_catalog(self):
        self.assertNotIn("Preserve this exact subject and its proportions.", catalog("en").values())


if __name__ == "__main__":
    unittest.main()
