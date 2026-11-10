# SPDX-License-Identifier: Apache-2.0
"""SMD-TRELLIS.2 texture student for the isolated finished-mesh worker.

Adapted from the authors' inference_utils.py and infer.py at b5671808.
https://huggingface.co/zjwfufu/SMD-TRELLIS.2/tree/b56718082a05d18df01dc34c2b6e88189c5d5c74
"""
import json
from pathlib import Path
from types import SimpleNamespace

import torch
from safetensors.torch import load_file

BASE_COMPONENT = 'ckpts/slat_flow_imgshape2tex_dit_1_3B_1024_bf16'
BASE_REVISION = 'af44b45f2e35a493886929c6d786e563ec68364d'
SMD_REVISION = 'b56718082a05d18df01dc34c2b6e88189c5d5c74'
TEXTURE_FLOW = 'tex_slat_flow_model_1024'


def texture_grid():
    """The released 4-step uniform grid with a single TRELLIS flow shift."""
    raw = torch.linspace(1.0, 0.0, 5, dtype=torch.float64)
    return 3.0 * raw / (1.0 + 2.0 * raw)


@torch.no_grad()
def fuse_texture_adapter(model, tensors, alpha):
    """Validate all tensors before merging the pinned texture release."""
    parameters = dict(model.named_parameters())
    pairs = {}
    for name, a in tensors.items():
        if '.lora_A' not in name:
            continue
        prefix, suffix = name.split('.lora_A', 1)
        b_name = prefix + '.lora_B' + suffix
        b = tensors.get(b_name)
        weight = parameters.get(prefix + '.weight')
        if (b is None or weight is None or a.ndim != 2 or b.ndim != 2
                or a.shape[0] != b.shape[1] or tuple(weight.shape) != (b.shape[0], a.shape[1])):
            raise ValueError('SMD adapter/base mismatch at ' + prefix)
        if prefix in pairs:
            raise ValueError('Multiple SMD adapter pairs for ' + prefix)
        pairs[prefix] = (weight, a, b)
    # The exact published texture adapter declares no replacement tensors.
    if not pairs or len(tensors) != 2 * len(pairs):
        raise ValueError('Unexpected SMD adapter tensor or incomplete pair.')
    for weight, a, b in pairs.values():
        delta = (b.to(weight.device, torch.float32) @ a.to(weight.device, torch.float32)) * (alpha / a.shape[0])
        weight.copy_((weight.bfloat16().float() + delta).to(weight.dtype))
    return len(pairs)


class SmdTextureSampler:
    @torch.no_grad()
    def sample(self, model, noise, cond, concat_cond, **kwargs):
        grid = texture_grid().to(noise.device)
        state = noise.replace(noise.feats.bfloat16())
        shape = concat_cond.replace(concat_cond.feats.bfloat16())
        for index, (current, following) in enumerate(zip(grid[:-1], grid[1:]), 1):
            print(f'SMD texture sampling {index}/4', flush=True)
            timestep = (current * 1000).expand(state.shape[0]).float()
            with torch.autocast('cuda', dtype=torch.bfloat16):
                velocity = model(state, timestep, cond, concat_cond=shape)
            delta = (following - current).to(state.feats.dtype)
            state = state.replace(state.feats + velocity.feats.to(state.feats.dtype) * delta)
        return SimpleNamespace(samples=state)


def enable_smd_texture(pipeline, models_root):
    directory = Path(models_root) / 'zjwfufu' / 'SMD-TRELLIS.2' / 'texture'
    adapter = json.loads((directory / 'lora' / 'adapter_config.json').read_text(encoding='utf-8'))
    schedule = json.loads((directory / 'sampling.json').read_text(encoding='utf-8'))
    expected = {'type': 'flow_match_euler_student', 'student_sample_steps': 4,
                'final_step_size_scale': 1.0, 'input_shape': [32]}
    noise = {'type': 'trellis_flow', 'shift': 3.0, 'sigma_min': 1e-5,
             'dynamic_shift': False, 'min_t': 0.0, 'max_t': 1.0}
    if (adapter.get('base_component') != BASE_COMPONENT
            or adapter.get('saved_replacements') != []
            or adapter.get('merge_precision') != 'bfloat16'
            or adapter.get('delta_precision') != 'float32'
            or schedule.get('precision') != 'bfloat16'
            or schedule.get('base_model_revision') != BASE_REVISION
            or schedule.get('sampler') != expected or schedule.get('noise_scheduler') != noise
            or pipeline._pretrained_args['models'].get(TEXTURE_FLOW) != BASE_COMPONENT):
        raise ValueError('The installed SMD adapter does not match the released texture recipe.')

    load_base = pipeline.load_tex_slat_flow_model_1024

    def load_student():
        load_base()
        model = pipeline.models[TEXTURE_FLOW]
        if not getattr(model, '_foundry_smd_loaded', False):
            model.to(device=pipeline.device, dtype=torch.bfloat16)
            model.convert_to(torch.bfloat16)
            tensors = load_file(str(directory / 'lora' / 'lora.safetensors'))
            pairs = fuse_texture_adapter(model, tensors, adapter['lora_alpha'])
            model._foundry_smd_loaded = True
            print(f'Loaded SMD texture student with {pairs} adapter pairs', flush=True)
        # The upstream texture entry point selects the Standard sampler first.
        # Bind the student after that selection, just before this flow is used.
        pipeline.tex_slat_sampler = SmdTextureSampler()

    pipeline.load_tex_slat_flow_model_1024 = load_student
