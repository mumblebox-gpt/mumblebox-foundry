import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image
import trimesh

ROOT = Path(__file__).parents[1] / "pipeline_workers"


class TextureTransferTests(unittest.TestCase):
    def test_worker_uvs_match_comfy_image_row_convention_without_mutating_baker_uvs(self):
        spec = importlib.util.spec_from_file_location('optimizer', ROOT / 'mesh_optimize_worker.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'comfy_uvs'), 'Worker must convert upward UVs at the native MESH boundary')
        upward = np.array([[.2, .15], [.8, .7]], dtype=np.float32)
        original = upward.copy()
        np.testing.assert_allclose(module.comfy_uvs(upward), [[.2, .85], [.8, .3]], atol=1e-7)
        np.testing.assert_array_equal(upward, original)

    def test_simplifier_preserves_separate_touching_closed_sheets(self):
        path = ROOT / 'mesh_optimize_worker.py'
        spec = importlib.util.spec_from_file_location('optimizer', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'simplify_mesh'), 'Topology-safe simplifier entry is missing')
        vertices = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],
                             [0,0,0],[1,0,0],[0,-1,0],[0,0,-1]], dtype=float)
        tetra = np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
        mesh = trimesh.Trimesh(vertices, np.concatenate([tetra, tetra+4]), process=False)
        result = module.simplify_mesh(mesh, 4)
        self.assertTrue(result.is_watertight)
        _, counts = np.unique(result.edges_sorted, axis=0, return_counts=True)
        self.assertEqual(int((counts > 2).sum()), 0)

    def test_uv_flip_keeps_color_and_material_channels_registered(self):
        path = ROOT / 'mesh_optimize_worker.py'
        self.assertTrue(path.exists(), 'Optimization texture-transfer implementation is missing')
        spec = importlib.util.spec_from_file_location('optimizer', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        vertices = np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]], dtype=float)
        faces = np.array([[0,1,2],[0,2,3]])
        uv = vertices[:, :2].copy()
        pixels = np.zeros((64,64,3), dtype=np.uint8)
        pixels[:32,:32] = [255,0,0]
        pixels[:32,32:] = [0,255,0]
        pixels[32:,:32] = [0,0,255]
        pixels[32:,32:] = [255,255,0]
        material = trimesh.visual.material.PBRMaterial(
            baseColorTexture=Image.fromarray(pixels),
            metallicRoughnessTexture=Image.new('RGB', (64,64), (0,80,200)))
        source = trimesh.Trimesh(vertices, faces, process=False,
                                 visual=trimesh.visual.TextureVisuals(uv=uv, material=material))
        low_uv = uv.copy()
        low_uv[:,0] = 1 - low_uv[:,0]
        target = trimesh.Trimesh(vertices, np.array([[0,1,3],[1,2,3]]), process=False,
                                 visual=trimesh.visual.TextureVisuals(uv=low_uv))
        with tempfile.TemporaryDirectory() as folder:
            cwd = Path.cwd()
            try:
                base, mr = module.rebake_maps(source, target, Path(folder), 64)
            finally:
                os.chdir(cwd)
            np.testing.assert_allclose(np.asarray(base)[16,16,:3], [0,255,0], atol=2)
            np.testing.assert_allclose(np.asarray(base)[48,16,:3], [255,255,0], atol=2)
            np.testing.assert_allclose(np.asarray(mr)[16,16,:3], [0,80,200], atol=2)

        # Photogrammetry can export base color with scalar glTF material factors.
        source.visual.material.metallicRoughnessTexture = None
        source.visual.material.metallicFactor = 0.0
        source.visual.material.roughnessFactor = 0.45
        with tempfile.TemporaryDirectory() as folder:
            cwd = Path.cwd()
            try:
                base, mr = module.rebake_maps(source, target, Path(folder), 64)
            finally:
                os.chdir(cwd)
            np.testing.assert_allclose(np.asarray(base)[16,16,:3], [0,255,0], atol=2)
            self.assertEqual(mr.size, (64, 64))
            self.assertEqual(mr.getpixel((16,16)), (0,115,0))
            self.assertTrue((Path(folder) / 'baked-metallic-roughness.png').is_file())


if __name__ == '__main__':
    unittest.main()
