"""A native graph bridge to the upstream TRELLIS.2 mesh-texturing node."""
import importlib.util
import json
from pathlib import Path
import uuid

from .runtime import WORKERS, work_root, worker_python, settings
from ..pipeline_workers import trellis_bridge_runtime as runtime


class Hi3DTrellis2TextureMesh:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'mesh': ('MESH',), 'image': ('IMAGE',),
            'seed': ('INT', {'default': 42, 'min': 0, 'max': 2147483647}),
            'steps': ('INT', {'default': 20, 'min': 1, 'max': 100}),
            'resolution': ([1024],),
            'texture_size': ('INT', {'default': 4096, 'min': 512, 'max': 8192, 'step': 512}),
            'guidance': ('FLOAT', {'default': 3., 'min': 0., 'max': 20., 'step': .1}),
            'filename_prefix': ('STRING', {'default': '3d/Trellis2Frog/finished-frog'}),
        }, 'optional': {
            'texture_mode': (['standard', 'smd'], {'default': 'standard'}),
            'sampler': (['euler', 'heun'], {'default': 'euler'}),
            'guidance_rescale': ('FLOAT', {'default': .2, 'min': 0., 'max': 1., 'step': .01}),
            'reference_lock': ('FLOAT', {'default': 0., 'min': 0., 'max': 1., 'step': .01}),
            'reference_substeps': ('INT', {'default': 2, 'min': 1, 'max': 8}),
        }}
    RETURN_TYPES = ('FILE_3D', 'IMAGE', 'IMAGE', 'STRING')
    RETURN_NAMES = ('textured_glb', 'base_color', 'metallic_roughness', 'report')
    FUNCTION = 'texture'
    CATEGORY = 'Hi3D/TRELLIS.2'
    DESCRIPTION = 'Texture the finished mesh with the upstream TRELLIS.2 node in its compatible isolated PyTorch environment.'
    OUTPUT_NODE = True

    def texture(self, mesh, image, seed, steps, resolution, texture_size, guidance, filename_prefix,
                sampler='euler', guidance_rescale=.2, reference_lock=0., reference_substeps=2,
                texture_mode='standard'):
        import numpy as np
        import torch
        from PIL import Image
        import folder_paths
        import comfy.model_management as mm
        from comfy_api.latest import Types
        from ..pipeline_workers.refine_client import arrays

        from ..foundry.workflows.image_to_3d.worker_models import ensure_texture
        def cancelled():
            mm.throw_exception_if_processing_interrupted()
            return False
        ensure_texture(Path(folder_paths.get_user_directory())/"mumblebox-foundry"/"models",
                       cancelled,owner="native-texture",texture_mode=texture_mode)
        vertices, faces = arrays(mesh)
        job = work_root() / 'trellis-jobs' / uuid.uuid4().hex
        job.mkdir(parents=True)
        np.savez(job / 'mesh.npz', vertices=vertices, faces=faces)
        pixels = (image[0].detach().cpu().clamp(0, 1).numpy() * 255).round().astype(np.uint8)
        Image.fromarray(pixels).save(job / 'reference.png')
        folder, name, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, folder_paths.get_output_directory())
        output = Path(folder) / f'{name}_{counter:05}_.glb'
        output.parent.mkdir(parents=True, exist_ok=True)
        request = {'mesh': str(job / 'mesh.npz'), 'image': str(job / 'reference.png'),
                   'output': str(output), 'comfy_core': str(Path(folder_paths.__file__).parent),
                   'seed': seed, 'steps': steps, 'resolution': resolution,
                   'texture_size': texture_size, 'guidance': guidance,
                   'texture_mode': texture_mode, 'sampler': sampler, 'guidance_rescale': guidance_rescale,
                   'reference_lock': reference_lock, 'reference_substeps': reference_substeps}
        request.update(settings())
        (job / 'request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
        mm.unload_all_models()
        mm.soft_empty_cache()
        runtime.run_worker([worker_python(), '-u',
                            str(WORKERS / 'trellis_texture_worker.py'), str(job / 'request.json')],
                           job / 'worker.log', mm.throw_exception_if_processing_interrupted)
        report = output.with_suffix('.report.json').read_text(encoding='utf-8')
        def texture_image(suffix):
            return torch.from_numpy(np.asarray(Image.open(output.with_suffix(suffix))).copy().astype(np.float32) / 255).unsqueeze(0)
        return {'ui': {'text': [report]},
                'result': (Types.File3D(str(output)), texture_image('.base-color.png'),
                           texture_image('.metallic-roughness.png'), report)}


NODE_CLASS_MAPPINGS = {'Hi3DTrellis2TextureMesh': Hi3DTrellis2TextureMesh}
NODE_DISPLAY_NAME_MAPPINGS = {'Hi3DTrellis2TextureMesh': 'TRELLIS.2 — Texture Finished Mesh (Isolated)'}
