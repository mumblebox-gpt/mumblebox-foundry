"""One owner for the pinned TextureMesh runtime and its supported controls."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def texture_runtime(runtime):
    executable = Path(runtime.get('openmvs_texture', str(Path(runtime['openmvs']) / 'TextureMesh.exe')))
    if not executable.is_file():
        raise RuntimeError(f'Missing configured OpenMVS texture runtime: {executable}')
    with executable.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return executable, dict(revision=runtime.get('openmvs_texture_revision', runtime['openmvs_version']),
                            sha256=sha, cuda=runtime.get('openmvs_texture_cuda', True))


def texture_options(base, extra, runtime_info, preserve_geometry=False):
    allowed = json.loads((ROOT / 'native-options.json').read_text(encoding='utf-8'))['texture']
    owned = {'input-file', 'mesh-file', 'output-file', 'working-folder', 'config-file', 'help', 'export-type'}
    for key, value in extra.items():
        if key not in allowed or key in owned:
            raise ValueError(f'Unknown or adapter-owned TextureMesh option: {key}')
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError('TextureMesh options must be scalar values')
    if preserve_geometry:
        for key, expected in {'decimate': 1, 'close-holes': 0, 'remove-unseen-faces': 0}.items():
            if key in extra and extra[key] != expected:
                raise ValueError(f'{key} changes the saved clean geometry; use the geometry stage instead')
    if extra.get('vertex-colors', False):
        raise ValueError('Vertex colors require the separate native PLY export mode; this path preserves OBJ/GLB UV textures')
    result = {**base, **extra}
    if not runtime_info['cuda']:
        if 'cuda-device' in extra:
            raise ValueError('This fixed TextureMesh build uses the CPU; CUDA remains available for depth and refinement')
        result.pop('cuda-device', None)
    return result
