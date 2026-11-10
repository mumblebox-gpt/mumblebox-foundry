"""Dataset-free, single-GPU adapter for the authors' Garment Particles models."""
import argparse
import ast
import gc
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType

# Keep the author operations eager in the Windows standalone runtime.
os.environ.setdefault('TORCH_COMPILE_DISABLE', '1')

import hydra
import numpy as np
from omegaconf import OmegaConf
from PIL import Image
import torch
from torch.distributed.checkpoint import load
import trimesh

from windows_runtime import configure_attention, PortableCheckpointReader
import guidance

GIB = 1024 ** 3
MODES = {'text': 'pgf_text', 'image': 'pgf_image', 'sketch': 'pgf_sketch'}


def configure_upstream(source):
    sys.path.insert(0, str(source))
    os.chdir(source)
    configure_attention()
    # Use the author's SVG exporter. Rasterize through resvg on Windows
    # instead of requiring a system Cairo installation for the worker.
    import resvg_py
    cairo = ModuleType('cairosvg')
    def svg2png(*, url, write_to, scale=1):
        image = resvg_py.svg_to_bytes(svg_path=str(url), zoom=scale)
        Path(write_to).write_bytes(image)
    cairo.svg2png = svg2png
    sys.modules['cairosvg'] = cairo


def author_reconstruction(source):
    from datasets.garment_edge_dataset import get_optimal_stitching_pairs
    from patterns.pattern_converter import NNSewingPattern
    path = source / 'tools' / 'run_server.py'
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'reconstruct']
    if len(functions) != 1:
        raise ValueError('The pinned author pattern reconstruction function is unavailable.')
    namespace = {'np': np, 'NNSewingPattern': NNSewingPattern,
                 'get_optimal_stitching_pairs': get_optimal_stitching_pairs}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['reconstruct']


def load_stage(config, checkpoint):
    model = hydra.utils.instantiate(config.model).eval().requires_grad_(False).to(dtype=torch.bfloat16)
    reader = PortableCheckpointReader(checkpoint)
    metadata = reader.read_metadata().state_dict_metadata
    weights = model.state_dict()
    names = {key.removeprefix('app.ema.'): value for key, value in metadata.items() if key.startswith('app.ema.')}
    missing = sorted(key for key in weights if key not in names and
                     not key.startswith(('text_encoder.', 'image_encoder.')))
    unexpected = sorted(set(names) - weights.keys())
    if missing or unexpected:
        raise ValueError(f'Garment checkpoint does not match its author config. Missing: {missing[:6]}, unexpected: {unexpected[:6]}')
    state = {key: weights[key] for key in names}
    load({'app': {'ema': state}}, storage_reader=reader, no_dist=True)
    size = sum(tensor.numel() * tensor.element_size() for tensor in model.parameters())
    free, _ = torch.cuda.mem_get_info()
    if free < size + 2 * GIB:
        raise RuntimeError(f'Garment stage needs more free GPU memory. Found {free / GIB:.1f} GiB free. Close GPU-heavy work and retry.')
    print(f'Loaded {checkpoint.name}: {len(state)} tensors, {size / GIB:.2f} GiB of BF16 parameters', flush=True)
    return model.cuda()


def sample(config, steps, model, noise, label, *, trajectory=False, **conditioning):
    from transport import Sampler
    transport = hydra.utils.instantiate(config.transport)
    settings = config.sample
    solve = Sampler(transport).sample_ode(
        sampling_method=settings.sampling_method, num_steps=steps, atol=settings.atol, rtol=settings.rtol,
        reverse=settings.reverse, timestep_shift=settings.timestep_shift)
    evaluations = 0
    def predict(*args, **kwargs):
        nonlocal evaluations
        evaluations += 1
        if evaluations == 1 or evaluations % 10 == 0:
            print(f'{label}: sampling evaluation {evaluations}', flush=True)
        return model(*args, **kwargs)
    with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
        result = solve(noise, predict, **conditioning)
        if trajectory:
            result = result[np.linspace(0, len(result) - 1, 5, dtype=int).tolist()]
        else:
            result = result[-1]
        return result.float().cpu().numpy()


def encoder_snapshot(repo, revision):
    root = Path(os.environ['HF_HOME']) / 'hub' / ('models--' + repo.replace('/', '--'))
    snapshot = root / 'snapshots' / revision
    if not (snapshot / 'model.safetensors').is_file():
        raise ValueError(f'The pinned Garment Particles encoder is missing: {repo}@{revision}.')
    return str(snapshot)


def resolve_encoders(config, mode):
    text = encoder_snapshot('openai/clip-vit-large-patch14', '32bd64288804d66eefd0ccbe215aa642df71cc41')
    config.model.text_encoder_name = text
    if mode == 'text':
        config.dataset.tokenizer_name = text
    else:
        image = encoder_snapshot('facebook/dinov2-large', '47b73eefe95e8d44ec3623f8890bd894b6ea2d6c')
        config.dataset.text_tokenizer_name = text
        config.dataset.image_processor_name = image
        config.model.image_encoder_name = image


def condition(config, request):
    from transformers import AutoImageProcessor, AutoTokenizer
    data = config.dataset
    tokenizer_name = data.get('tokenizer_name', data.get('text_tokenizer_name'))
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, use_fast=False, local_files_only=True)
    prompt = request['prompt'] if request['mode'] in ('text', 'surprise') else ''
    tokens = tokenizer(prompt, return_tensors='pt', max_length=77, padding='max_length', truncation=True)
    result = {'text_tokens': tokens.input_ids.cuda(), 'text_attn_mask': tokens.attention_mask.bool().cuda()}
    if request['mode'] in ('image', 'sketch'):
        processor = AutoImageProcessor.from_pretrained(data.image_processor_name, use_fast=False, local_files_only=True)
        images = []
        for name in ('image', 'back_image'):
            if request.get(name):
                with Image.open(request[name]) as image:
                    images.append(image.convert('RGB'))
        pixels = processor(images=images, return_tensors='pt')['pixel_values']
        result['pixel_values'] = pixels.unsqueeze(0).cuda()
    return result


def free_stage():
    gc.collect()
    torch.cuda.empty_cache()


def save_pattern(edge_output, config, source, out):
    shape = (1, config.model.n_panels, config.model.n_curves, config.model.in_channels)
    _, patterns = author_reconstruction(source)(edge_output.reshape(shape), config.dataset.normalization)
    if len(patterns) != 1 or not patterns[0].pattern.get('panels'):
        raise ValueError('The author pattern stage returned no valid sewing panels. Try a different seed or prompt.')
    pattern = patterns[0]
    pattern.name = 'garment'
    pattern.serialize(str(out), to_subfolder=False, view_ids=True, with_3d=True)
    return len(pattern.pattern['panels']), len(pattern.pattern.get('stitches', []))


def run(request, source, models, report_models=lambda names: None):
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError('Garment Particles requires a CUDA GPU with BF16 support.')
    mode, count, steps = request['mode'], request['points'], request['steps']
    if mode not in (*MODES, 'surprise') or not 100 <= count <= 8192 or not 2 <= steps <= 250:
        raise ValueError('Choose a supported garment mode, point count and sampling step count.')
    out = Path(request['output'])
    out.mkdir(parents=True, exist_ok=True)
    checkpoint_mode = 'text' if mode == 'surprise' else mode
    phase = MODES[checkpoint_mode]
    configs = source / 'configs' / 'pretrained'
    pgf_cfg = OmegaConf.load(configs / (phase + '.yaml'))
    resolve_encoders(pgf_cfg, checkpoint_mode)
    edge_cfg = OmegaConf.load(configs / 'edge.yaml')
    torch.manual_seed(request['seed'])
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()

    pgf = load_stage(pgf_cfg, models / phase)
    active = [f"Garment Particles · {checkpoint_mode.title()} generator"]
    if getattr(pgf, "text_encoder", None) is not None:
        active.append("CLIP ViT-L/14")
    if getattr(pgf, "image_encoder", None) is not None:
        active.append("DINOv2 Large")
    report_models(active)
    noise = torch.randn(1, count, 6, device='cuda')
    mask = torch.ones_like(noise[..., 0], dtype=torch.bool)
    operation = request.get('edit', {}).get('operation')
    if operation in guidance.EDIT_FUNCTIONS:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(pgf_cfg.dataset.tokenizer_name, use_fast=False, local_files_only=True)
        particle_values = guidance.edit(source, pgf, tokenizer, pgf_cfg.dataset.normalization, request)[None, ...]
    else:
        conditioning = condition(pgf_cfg, request)
        if operation == 'blend':
            settings = request['edit']
            generator = torch.Generator(device='cuda').manual_seed(settings['second_seed'])
            second = torch.randn((1, settings.get('second_points', count), 6), device='cuda', generator=generator)
            def trajectory(values):
                endpoint_mask = torch.ones_like(values[..., 0], dtype=torch.bool)
                return sample(pgf_cfg, min(steps, 40), pgf.forward_with_mask, values,
                              'Matching endpoint trajectories', trajectory=True, mask=endpoint_mask, **conditioning)
            noise = guidance.blend(trajectory, noise, second, settings['blend'])
            count = noise.shape[1]
            mask = torch.ones_like(noise[..., 0], dtype=torch.bool)
        particle_values = sample(pgf_cfg, steps, pgf.forward_with_mask, noise, 'Garment particles',
                                 mask=mask, **conditioning)
    del pgf, noise, mask
    free_stage()
    report_models([])
    print('Garment particles complete. Loading sewing-pattern stage.', flush=True)

    edge = load_stage(edge_cfg, models / 'edge')
    report_models(['Garment Particles · Sewing pattern model'])
    norm = pgf_cfg.dataset.normalization
    edge_norm = edge_cfg.dataset.normalization
    normalized = particle_values * np.array(norm.pcd_std) + np.array(norm.pcd_mean)
    edge_points = (normalized - np.array(edge_norm.pcd_mean)) / np.array(edge_norm.pcd_std)
    points = torch.as_tensor(edge_points, dtype=torch.float32, device='cuda')
    edge_noise = torch.randn(1, edge.n_panels * edge.n_curves, edge.in_channels, device='cuda')
    edge_output = sample(edge_cfg, steps, edge.forward, edge_noise, 'Sewing pattern',
                         panel_points=points, panel_points_mask=torch.ones_like(points[..., 0], dtype=torch.bool))
    del edge, points, edge_noise
    free_stage()
    report_models([])

    limits = np.array([norm.xlims, norm.ylims])
    normalized[..., :2] = normalized[..., :2] * (limits[:, 1] - limits[:, 0]) + limits[:, 0]
    if not np.isfinite(normalized).all() or not np.isfinite(edge_output).all():
        raise ValueError('The garment models returned non-finite geometry.')
    np.savez_compressed(out / 'particles.npz', particles=normalized[0], edge_predictions=edge_output[0])
    inside = normalized[0, :, 5] < .5
    colors = np.where(inside[:, None], [53, 170, 153, 255], [240, 171, 85, 255])
    # The author normalization uses centimeters and a Y-up garment frame.
    drape = trimesh.PointCloud(normalized[0, :, 2:5] * .01, colors=colors)
    drape.export(out / 'drape-particles.ply')
    drape.export(out / 'drape-particles.glb')
    panels, stitches = save_pattern(edge_output, edge_cfg, source, out)
    receipt = {'mode': mode, 'points': count, 'steps': steps, 'seed': request['seed'],
               'panels': panels, 'stitches': stitches, 'seconds': time.monotonic() - started,
               'peak_cuda_allocated_bytes': torch.cuda.max_memory_allocated(),
               'peak_cuda_reserved_bytes': torch.cuda.max_memory_reserved()}
    if operation:
        receipt['edit'] = operation
    if request.get('back_image'):
        receipt['reference_views'] = 2
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    source, models = args.source.resolve(), args.models.resolve()
    request = json.loads(args.request.read_text(encoding='utf-8')) if args.request else None
    configure_upstream(source)
    if args.probe:
        from models.sparse_lightningdit_v3_cross_attn_varlen import SparseLightningDiTV3CrossAttnVarlen
        from models.sparse_lightningdit_v3_cross_attn_varlen_img_text_v2 import SparseLightningDiTV3CrossAttnVarlenImgTextV2
        from models.lightningdit_edge_model_varlen import LightningCrossAttnDiTV3EdgeModelVarlen
        from transport import Sampler
        author_reconstruction(source)
        print('Garment Particles text, image, sketch and sewing-pattern worker imports passed.')
        return
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "pipeline_workers"))
    from worker_telemetry import monitor_stages
    with monitor_stages(args.request) as report_models:
        run(request, source, models, report_models)


if __name__ == '__main__':
    main()
