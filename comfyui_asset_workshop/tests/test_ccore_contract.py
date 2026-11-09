"""Boundaries for model-authored GLB entering Foundry's trusted viewer."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

path = Path(__file__).parents[1] / "foundry/workflows/ccore_prop/contract.py"
spec = importlib.util.spec_from_file_location("ccore_contract", path)


def load_contract():
    if not path.is_file():
        raise AssertionError("The CCORE asset validation boundary is missing.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def glb(document):
    payload = json.dumps(document).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    data = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    return (struct.pack("<4sII", b"glTF", 2, 28 + len(payload) + len(data))
            + struct.pack("<I4s", len(payload), b"JSON") + payload
            + struct.pack("<I4s", len(data), b"BIN\0") + data)


class CcoreContractTests(unittest.TestCase):
    def validate(self, document):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "prop.glb"
            target.write_bytes(glb(document))
            return load_contract().inspect_glb(target)

    def triangle(self):
        return {
            "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
            "buffers": [{"byteLength": 36}],
            "bufferViews": [{"buffer": 0, "byteLength": 36}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
        }

    def test_generation_preserves_edited_prompt(self):
        contract = load_contract()
        prompt = "  Create one green case.\nPut the handle on top.  "
        self.assertEqual(contract.options({"prompt": prompt})["prompt"], prompt)

    def test_measures_self_contained_scene(self):
        self.assertEqual(self.validate(self.triangle())["triangles"], 1)

    def test_rejects_external_uri_and_cycles(self):
        document = self.triangle()
        document["images"] = [{"uri": "http://127.0.0.1/private"}]
        with self.assertRaisesRegex(ValueError, "external"):
            self.validate(document)
        document = self.triangle()
        document["nodes"][0]["children"] = [0]
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.validate(document)

    def test_rejects_declared_buffer_outside_file(self):
        document = self.triangle()
        document["bufferViews"][0]["byteLength"] = 120
        with self.assertRaisesRegex(ValueError, "buffer"):
            self.validate(document)
