"""Invoke the upstream ComfyUI-Trellis2 texture node with compatible GPU libraries."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).parent


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    request_path = Path(sys.argv[1])
    probe_only = '--probe' in sys.argv[2:]
    sys.argv = [sys.argv[0]]
    core = Path(request['comfy_core'])
    sys.path.extend([str(core), str(core / '.venv' / 'Lib' / 'site-packages')])
    os.environ.update(ATTN_BACKEND='sdpa', SPARSE_ATTN_BACKEND='sdpa',
                      SPARSE_CONV_BACKEND='flex_gemm', HF_HUB_OFFLINE='1',
                      HF_HUB_DISABLE_TELEMETRY='1')
    import numpy as np
    import torch
    import trimesh
    import folder_paths
    from PIL import Image
    from scipy.spatial import cKDTree
    from trellis_bridge_runtime import mesh_frame, restore_vertices, texture_reference_rgb
    from worker_telemetry import monitor

    folder_paths.models_dir = request['trellis_models']
    repo = Path(request['trellis_repo'])
    spec = importlib.util.spec_from_file_location('trellis2_wrapper', repo / '__init__.py',
                                                 submodule_search_locations=[str(repo)])
    pack = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pack
    spec.loader.exec_module(pack)
    from trellis2_wrapper.trellis2.pipelines import Trellis2ImageTo3DPipeline
    from trellis2_wrapper.trellis2.modules.attention import config
    from trellis2_wrapper.trellis2.modules.sparse import config as sparseconfig
    config.set_backend('sdpa')
    sparseconfig.set_attn_backend('sdpa')
    sparseconfig.set_conv_backend('flex_gemm')

    if probe_only:
        print('Texture worker imports OK; no model weights loaded', flush=True)
        return

    arrays = np.load(request['mesh'])
    mesh = trimesh.Trimesh(vertices=arrays['vertices'], faces=arrays['faces'], process=False)
    frame = mesh_frame(mesh.vertices)
    reference = Image.open(request['image'])
    reference_has_alpha = 'A' in reference.getbands()
    prepared_reference = texture_reference_rgb(reference)
    prepared_reference.save(Path(request['image']).with_name('reference-conditioned.png'))
    image = np.asarray(prepared_reference, dtype=np.float32) / 255
    image = torch.from_numpy(image.copy()).unsqueeze(0)
    model = Path(request['trellis_models']) / 'microsoft' / 'TRELLIS.2-4B'
    pipeline = Trellis2ImageTo3DPipeline.from_pretrained(str(model), keep_models_loaded=False)
    pipeline.low_vram = True
    pipeline.cuda()
    texture_mode = request.get('texture_mode', 'standard')
    if texture_mode not in ('standard', 'smd'):
        raise ValueError('Choose Standard or SMD texturing.')
    slot_names = {}
    if texture_mode == 'smd':
        if request['resolution'] != 1024:
            raise ValueError('SMD texturing needs the 1024 TRELLIS.2 texture model.')
        from smd_texture import TEXTURE_FLOW, enable_smd_texture
        enable_smd_texture(pipeline, request['trellis_models'])
        slot_names[TEXTURE_FLOW] = "SMD-TRELLIS.2 · Texture flow"
    telemetry = monitor(pipeline, request_path, slot_names)

    node = pack.NODE_CLASS_MAPPINGS['Trellis2MeshTexturing']()
    params = {}
    for key, schema in node.INPUT_TYPES()['required'].items():
        options = schema[1] if len(schema) > 1 else {}
        if 'default' in options:
            params[key] = options['default']
    params.update(pipeline=pipeline, image=image, trimesh=mesh, seed=request['seed'],
                  texture_steps=request['steps'], resolution=request['resolution'],
                  texture_size=request['texture_size'], texture_guidance_strength=request['guidance'],
                  use_custom_normals=True, max_views=1,
                  sampler=request.get('sampler', 'euler'),
                  texture_guidance_rescale=request.get('guidance_rescale', .2),
                  dino_lock=request.get('reference_lock', 0.),
                  dino_substeps=request.get('reference_substeps', 2), dino_foundation_cap=.92)
    if texture_mode == 'smd':
        params.update(texture_steps=4, texture_guidance_strength=1.0, texture_guidance_rescale=0.0,
                      sampler='euler', dino_lock=0.0)
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    print('TEXTURING FINISHED MESH', len(mesh.vertices), len(mesh.faces), params['resolution'], flush=True)
    with torch.inference_mode():
        output, base_color, material = node.process(**params)
    output.vertices = restore_vertices(output.vertices, frame)
    if len(output.faces) != len(mesh.faces):
        raise RuntimeError(f'Texturing changed triangle count: {len(mesh.faces)} -> {len(output.faces)}')
    distances, _ = cKDTree(mesh.vertices).query(output.vertices, workers=4)
    geometry_error = float(distances.max())
    if geometry_error > max(float(np.ptp(mesh.vertices, axis=0).max()) * 1e-5, 1e-7):
        raise RuntimeError(f'Texturing moved mesh geometry by {geometry_error}')
    destination = Path(request['output'])
    output.export(destination)
    for tensor, suffix in ((base_color, '.base-color.png'), (material, '.metallic-roughness.png')):
        pixels = (tensor[0].detach().cpu().clamp(0, 1).numpy() * 255).round().astype(np.uint8)
        Image.fromarray(pixels).save(destination.with_suffix(suffix))
    report = {'implementation': 'visualbruno/ComfyUI-Trellis2',
              'revision': 'b0e84c0f29857a444e8bcb5b9be2ea218e96efd0',
              'node': 'Trellis2MeshTexturing', 'torch': torch.__version__,
              'texture_mode': texture_mode,
              'sampling': {'steps': params['texture_steps'], 'sampler': params['sampler'],
                           'guidance': 'distilled' if texture_mode == 'smd' else params['texture_guidance_strength']},
              'seconds': time.monotonic() - started,
              'peak_cuda_allocated_bytes': torch.cuda.max_memory_allocated(),
              'peak_cuda_reserved_bytes': torch.cuda.max_memory_reserved(),
              'input_vertices': len(mesh.vertices), 'input_faces': len(mesh.faces),
              'output_vertices': len(output.vertices), 'output_faces': len(output.faces),
              'max_vertex_position_error': geometry_error,
              'reference_alpha_composited': reference_has_alpha,
              'reference_background': 'black',
              'settings': {k: request[k] for k in ('seed', 'steps', 'resolution', 'texture_size', 'guidance',
                                                 'sampler', 'guidance_rescale', 'reference_lock', 'reference_substeps') if k in request},
              'output': str(destination)}
    destination.with_suffix('.report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
