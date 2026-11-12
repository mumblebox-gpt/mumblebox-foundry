"""Experiment-owned preparation, coordinate restoration and durable checkpoints.

Inference/registration/cleanup are existing graph nodes, not duplicated here.
"""
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import torch
import trimesh
from PIL import Image
import folder_paths
from comfy_api.latest import Types
from .references import CATEGORY
from .refinement_geometry import prepare_frame, restore_frame, project_obj


def arrays(mesh):
    v, f = mesh.vertices, mesh.faces
    v = v.detach().cpu().numpy() if hasattr(v, 'detach') else np.asarray(v)
    f = f.detach().cpu().numpy() if hasattr(f, 'detach') else np.asarray(f)
    if v.ndim == 3:
        v = v[0, :int(mesh.vertex_counts[0])] if getattr(mesh, 'vertex_counts', None) is not None else v[0]
        f = f[0, :int(mesh.face_counts[0])] if getattr(mesh, 'face_counts', None) is not None else f[0]
    return v, f


def mesh_value(v, f):
    from comfy_api.latest._util.geometry_types import MESH
    return MESH(vertices=torch.from_numpy(np.asarray(v, dtype=np.float32)).unsqueeze(0),
                      faces=torch.from_numpy(np.asarray(f, dtype=np.int64)).unsqueeze(0))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_mesh(mesh, root, name):
    v, f = arrays(mesh)
    item = trimesh.Trimesh(v, f, process=False)
    saved = dict(vertices=v, faces=f)
    if getattr(mesh, 'uvs', None) is not None:
        uv = mesh.uvs.detach().cpu().numpy()
        uv = uv[0, :len(v)] if uv.ndim == 3 else uv
        if uv.shape != (len(v), 2) or not np.isfinite(uv).all():
            raise ValueError('UV coordinates must be finite and match the mesh vertices')
        saved['uvs'] = uv
        # Native Comfy MESH uses glTF UVs; trimesh/OBJ use bottom-left origin.
        uv_obj = uv.copy()
        uv_obj[:, 1] = 1 - uv_obj[:, 1]
        item.visual = trimesh.visual.TextureVisuals(uv=uv_obj)
    item.export(root / (name + '.obj'))
    item.export(root / (name + '.glb'))
    np.savez_compressed(root / (name + '.npz'), **saved)
    return str(root / (name + '.glb'))


class PrepareRefinement:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'project_folder': ('STRING', {'default': '', 'tooltip': 'Completed native Meshroom job, including original asset and camera cache.'}),
            'reference_frame': ('INT', {'default': -1, 'min': -1, 'max': 1000, 'tooltip': 'Index in the saved selected frame set, not the original video index. Match an unobstructed front view.'}),
            'run_name': ('STRING', {'default': 'jade-guardian-refine-20261112'}),
        }}
    RETURN_TYPES = ('MESH', 'IMAGE', 'MASK', 'V360_REFINEMENT')
    RETURN_NAMES = ('camera_aligned_mesh', 'orbit_reference', 'background_mask', 'source_context')
    FUNCTION = 'prepare'
    CATEGORY = CATEGORY

    def prepare(self, project_folder, reference_frame, run_name):
        project = Path(project_folder).resolve()
        original = project / 'asset/texturedMesh.obj'
        camera_files = list((project / 'MeshroomCache/StructureFromMotion').glob('*/cameras.sfm'))
        if len(camera_files) != 1 or not original.is_file():
            raise ValueError('Choose one completed Meshroom project with its original cameras and OBJ')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', run_name):
            raise ValueError('Run name may contain letters, numbers, dashes and underscores')
        source_frames = project.parent
        camera_data = json.loads(camera_files[0].read_text(encoding='utf-8-sig'))
        if reference_frame < 0:
            posed = {pose['poseId'] for pose in camera_data['poses']}
            names = sorted(Path(view['path']).name for view in camera_data['views'] if view['poseId'] in posed)
            if not names:
                raise ValueError('No registered view is available for finishing.')
            reference_frame = int(Path(names[0]).stem.removeprefix('frame_'))
        name = f'frame_{reference_frame:05d}.png'
        image_path, mask_path = source_frames / 'frames' / name, source_frames / 'masks' / name
        view = next((x for x in camera_data['views'] if Path(x['path']).name == name), None)
        if view is None:
            raise ValueError('Selected frame has no registered camera')
        pose = next(p['pose']['transform'] for p in camera_data['poses'] if p['poseId'] == view['poseId'])
        intrinsic = next(i for i in camera_data['intrinsics'] if i['intrinsicId'] == view['intrinsicId'])
        rotation = np.array(pose['rotation'], dtype=float).reshape(3, 3)
        original_mesh = trimesh.load(original, force='mesh', process=False, skip_materials=True)
        original_mesh.merge_vertices()
        if len(original_mesh.faces) > 5_000_000:
            raise ValueError('Hi3D workbench accepts at most 5 million input triangles; add the native Decimate Mesh node first')
        rgb = np.array(Image.open(image_path).convert('RGB')) / 255.
        foreground = np.array(Image.open(mask_path).convert('L')) / 255.
        if rgb.shape[:2] != foreground.shape or foreground.max() == 0:
            raise ValueError('Reference and foreground mask must match and contain a subject')
        focal = float(intrinsic['focalLength']) / float(intrinsic['sensorWidth']) * int(view['width'])
        sample = original_mesh.vertices[::max(1, len(original_mesh.vertices) // 30000)]
        xy = project_obj(sample, rotation, np.array(pose['center'], dtype=float), focal, int(view['width']), int(view['height']))
        pixels = np.rint(xy).astype(int)
        valid = (pixels[:, 0] >= 0) & (pixels[:, 0] < rgb.shape[1]) & (pixels[:, 1] >= 0) & (pixels[:, 1] < rgb.shape[0])
        overlap = float(np.sum(foreground[pixels[valid, 1], pixels[valid, 0]] > .25) / len(pixels))
        if overlap < .8:
            raise ValueError(f'Camera/mesh projection only overlaps the foreground at {overlap:.1%}; inspect coordinate alignment before refining')
        prepared, transform = prepare_frame(original_mesh.vertices, rotation)
        root = Path(folder_paths.get_output_directory()).resolve() / 'foundry/vt' / run_name
        root.mkdir(parents=True, exist_ok=True)
        context = {'root': str(root), 'project_folder': str(project), 'transform': transform,
                   'original_obj': str(original), 'original_sha256': digest(original),
                   'reference_frame': reference_frame, 'reference_path': str(image_path), 'reference_sha256': digest(image_path),
                   'camera_file': str(camera_files[0]), 'camera_sha256': digest(camera_files[0]),
                   'projection_foreground_fraction': overlap, 'view_id': view['viewId'],
                   'roundtrip_max_error': float(np.abs(restore_frame(prepared, transform) - original_mesh.vertices).max())}
        previous = root / 'source.json'
        if previous.exists() and json.loads(previous.read_text(encoding='utf-8')) != context:
            raise ValueError('Run name already belongs to a different source/reference. Choose another run name to preserve it')
        previous.write_text(json.dumps(context, indent=2), encoding='utf-8')
        rgba = np.dstack([(rgb * 255).astype('uint8'), (foreground * 255).astype('uint8')])
        Image.fromarray(rgba).save(root / 'reference.png')
        mesh = mesh_value(prepared, original_mesh.faces)
        save_mesh(mesh, root, 'prepared-source')
        return mesh, torch.from_numpy(rgb.astype('float32')).unsqueeze(0), torch.from_numpy((1 - foreground).astype('float32')).unsqueeze(0), context


class RestoreRefinement:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'mesh': ('MESH',), 'context': ('V360_REFINEMENT',),
                             'alignment_report': ('STRING', {'forceInput': True}), 'inference_report': ('STRING', {'forceInput': True})}}
    RETURN_TYPES = ('MESH', 'FILE_3D', 'V360_REFINEMENT')
    RETURN_NAMES = ('refined_original_frame', 'refined_preview', 'source_context')
    FUNCTION = 'restore'
    CATEGORY = CATEGORY

    def restore(self, mesh, context, alignment_report, inference_report):
        v, f = arrays(mesh)
        restored = mesh_value(restore_frame(v, context['transform']), f)
        root = Path(context['root'])
        path = save_mesh(restored, root, 'refined')
        (root / 'alignment.json').write_text(alignment_report, encoding='utf-8')
        (root / 'inference.json').write_text(inference_report, encoding='utf-8')
        return restored, Types.File3D(path), context


class RefinementCheckpoint:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'mesh': ('MESH',), 'context': ('V360_REFINEMENT',), 'name': ('STRING', {'default': 'clean'})}}
    RETURN_TYPES = ('FILE_3D', 'STRING', 'V360_REFINEMENT')
    RETURN_NAMES = ('mesh_preview', 'mesh_obj', 'source_context')
    FUNCTION = 'save'
    CATEGORY = CATEGORY

    def save(self, mesh, context, name):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', name) or name in ('prepared-source', 'texturedMesh'):
            raise ValueError('Use a simple unique checkpoint name')
        root = Path(context['root'])
        path = save_mesh(mesh, root, name)
        return Types.File3D(path), str(root / (name + '.obj')), context


class ResumeRefinement:
    """Resume a durable geometry checkpoint without running inference again."""
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'source': (['Completed clean checkpoint', 'Refine source mesh'], {'default': 'Completed clean checkpoint', 'tooltip': 'Resume skips inference and cleanup. Refine source mesh requests the connected full Hi3D and cleanup chain.'}),
            'run_folder': ('STRING', {'default': '', 'tooltip': 'Existing Virtual 360 refinement output folder containing source.json.'}),
            'checkpoint': (['clean', 'refined'], {'default': 'clean'}),
        }, 'optional': {'fresh_mesh': ('MESH', {'lazy': True}), 'fresh_context': ('V360_REFINEMENT', {'lazy': True})}}
    RETURN_TYPES = ('MESH', 'V360_REFINEMENT', 'FILE_3D', 'STRING')
    RETURN_NAMES = ('saved_mesh', 'source_context', 'saved_preview', 'native_obj')
    FUNCTION = 'load'
    CATEGORY = CATEGORY

    def check_lazy_status(self, source, fresh_mesh=None, fresh_context=None, **kwargs):
        if source == 'Refine source mesh':
            return [name for name, value in [('fresh_mesh', fresh_mesh), ('fresh_context', fresh_context)] if value is None]
        return []

    def load(self, source, run_folder, checkpoint, fresh_mesh=None, fresh_context=None):
        if source == 'Refine source mesh':
            if fresh_mesh is None or fresh_context is None:
                raise ValueError('Connect the clean mesh and source context before refining')
            return fresh_mesh, fresh_context, None, ""
        root = Path(run_folder).resolve()
        allowed = Path(folder_paths.get_output_directory()).resolve() / 'foundry/vt'
        if not root.is_relative_to(allowed):
            raise ValueError('Choose a saved Virtual 360 refinement run in the Comfy output directory')
        context = json.loads((root / 'source.json').read_text(encoding='utf-8'))
        if Path(context['root']).resolve() != root:
            raise ValueError('Checkpoint source context does not match this output folder')
        with np.load(root / (checkpoint + '.npz'), allow_pickle=False) as data:
            mesh = mesh_value(data['vertices'], data['faces'])
        return mesh, context, Types.File3D(str(root / (checkpoint + ".glb"))), str(root / (checkpoint + ".obj"))
