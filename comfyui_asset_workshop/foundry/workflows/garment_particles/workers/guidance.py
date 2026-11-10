"""Invoke the pinned author's editing sampler without starting its server."""
import ast
from contextlib import redirect_stdout
import json
import re
import sys

import numpy as np
import torch

from matching import emd, one_way_chamfer

EDIT_FUNCTIONS = {
    'pattern': '_generate_from_pattern', 'silhouette': '_generate_from_silouette',
    'shape': '_generate_from_3d', 'completion': '_generate_from_3d', 'mix': '_generate_from_3d',
}


class Progress:
    def __init__(self, stream):
        self.stream = stream
        self.last = None
        self.awaiting_time = False

    def write(self, message):
        if message.startswith(('Generating', 'early_stop')):
            self.stream.write(message + '\n')
        if message.strip() == 't:':
            self.awaiting_time = True
        if self.awaiting_time and (match := re.match(r'^([0-9.]+)$', message)):
            self.awaiting_time = False
            progress = int(float(match[1]) * 20) * 5
            if progress != self.last:
                self.last = progress
                self.stream.write(f'Author guidance: {progress}% of sampling\n')
                self.stream.flush()
        return len(message)

    def flush(self):
        self.stream.flush()


def functions(source):
    path = source / 'tools' / 'run_server.py'
    names = set(EDIT_FUNCTIONS.values()) | {'torch_camera_from_angles', 'torch_project_from_angles',
                                           '_generate_from_silouette_streaming'}
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    selected = [item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name in names]
    if {item.name for item in selected} != names:
        raise ValueError('The pinned author editing functions are unavailable.')
    namespace = {'torch': torch, 'np': np, 'device': torch.device('cuda'),
                 'emd_distance': emd, 'one_way_chamfer': one_way_chamfer, 'json': json}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def edit(source, model, tokenizer, normalization, request):
    params = request['edit']
    operation = params['operation']
    expected = 2 if operation in ('pattern', 'silhouette') else 3
    guide = np.asarray(params['guide'], dtype=np.float32)
    if guide.ndim != 2 or guide.shape[1] != expected or not 8 <= len(guide) <= 4096:
        raise ValueError('Paint or select at least 8 guide points before applying the edit.')
    if not np.isfinite(guide).all():
        raise ValueError('Guide points must be finite.')
    count = request['points']
    guide_count = min(count, 2048)
    if len(guide) > guide_count:
        guide = guide[np.linspace(0, len(guide) - 1, guide_count, dtype=int)]
    limits = np.array([normalization.xlims, normalization.ylims])
    author = functions(source)
    editor = author[EDIT_FUNCTIONS[operation]]
    objective = params.get('objective', 'completion' if operation in ('completion', 'mix') else 'reconstruction')
    args = (request['prompt'], guide.copy(), params['strength'], params['rate'], params['iterations'],
            count, params['steps'])
    sampler = (model, tokenizer, None, limits, normalization)
    if operation == 'silhouette':
        camera = (np.eye(3), params['azimuth'], params['elevation'], 150.,
                  np.asarray(params['center'], dtype=np.float32))
        if objective == 'completion':
            # The authors expose silhouette completion in the streaming sampler.
            updates = author['_generate_from_silouette_streaming'](*args, objective, *camera, *sampler)
            for line in updates:
                update = json.loads(line)
                if update['type'] == 'result':
                    output = np.asarray(update['points'])
                    break
                if update['step'] % 5 == 0 or update['percent'] == 100:
                    print(f"Author guidance: {update['percent']}% of sampling", flush=True)
            else:
                raise ValueError('The author silhouette sampler returned no result.')
        else:
            # This entry point expects min/max rows at its output transform.
            with redirect_stdout(Progress(sys.stdout)):
                output = editor(*args, *camera, *sampler[:3], limits.T, normalization)
    else:
        with redirect_stdout(Progress(sys.stdout)):
            output = editor(*args, objective, *sampler)
    output[..., :2] = (output[..., :2] - limits[:, 0]) / (limits[:, 1] - limits[:, 0])
    return (output - np.array(normalization.pcd_mean)) / np.array(normalization.pcd_std)


def blend(sample, first, second, amount):
    """Align unordered noise particles using assignment over denoising snapshots."""
    from scipy.optimize import linear_sum_assignment

    if amount == 0:
        return first
    if amount == 1:
        return second
    with torch.inference_mode():
        a, b = sample(first), sample(second)
        schedule = np.linspace(0, len(a) - 1, 5, dtype=int)
        cost = torch.zeros((first.shape[1], second.shape[1]), device='cpu')
        for index in schedule:
            left = torch.from_numpy(a[index, 0]).float()
            right = torch.from_numpy(b[index, 0]).float()
            cost += torch.cdist(left, right).square_()
        left_ids, right_ids = linear_sum_assignment(cost.numpy())
        left, right = first[:, left_ids], second[:, right_ids]
        cosine = torch.nn.functional.cosine_similarity(left.flatten(), right.flatten(), dim=0)
        angle = cosine.clamp(-1., 1.).acos()
        if angle.sin().abs() < 1e-5:
            matched = left.lerp(right, amount)
        else:
            matched = (left * ((1 - amount) * angle).sin() + right * (amount * angle).sin()) / angle.sin()
        n, m = first.shape[1], second.shape[1]
        count = round(n * (1 - amount) + m * amount)
        missing = count - matched.shape[1]
        if missing:
            larger, used = (first, left_ids) if n > m else (second, right_ids)
            extra = np.setdiff1d(np.arange(larger.shape[1]), used, assume_unique=True)
            matched = torch.cat((matched, larger[:, extra[:missing]]), dim=1)
        return matched

