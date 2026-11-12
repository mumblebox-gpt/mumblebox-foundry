"""Branch B camera preparation and native OpenMVS final texture projection.

Hi3D/cleanup remain visible native graph nodes. All child processes use the shared
experiment owner. Original reconstruction is read-only after it completes.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path
import numpy as np
import torch
import trimesh
from PIL import Image
import folder_paths
from comfy_api.latest import Types
from .runtime import runtime_settings
from .references import CATEGORY
from .processes import release_models, run_process
from .refinement import digest, mesh_value, save_mesh
from .refinement_geometry import restore_frame
from .colmap_geometry import image_records, read_camera, prepare, project as project_vertices
from .colmap_openmvs import arglist
from .openmvs_texture import texture_runtime, texture_options
from .colmap_export import export_asset

ROOT = Path(__file__).resolve().parent


class PrepareOpenMVSRefinement:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'project_folder': ('STRING', {'forceInput': True}),
            'reference_frame': ('INT', {'default': -1, 'min': -1, 'max': 1000}),
            'run_name': ('STRING', {'default': 'jade-guardian-colmap-refine-20261111'}),
        }}
    RETURN_TYPES = ('MESH', 'IMAGE', 'MASK', 'V360_REFINEMENT')
    RETURN_NAMES = ('camera_aligned_mesh', 'orbit_reference', 'background_mask', 'source_context')
    FUNCTION = 'prepare'
    CATEGORY = CATEGORY

    def prepare(self, project_folder, reference_frame, run_name):
        project = Path(project_folder).resolve()
        receipt = json.loads((project / 'result.json').read_text(encoding='utf-8'))
        runtime = runtime_settings()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', run_name):
            raise ValueError('Use a simple unique run name')
        root = Path(folder_paths.get_output_directory()).resolve() / 'foundry/vt' / run_name
        root.mkdir(exist_ok=True, parents=True)
        text_model = root / 'camera-text'
        text_model.mkdir(exist_ok=True)
        colmap = Path(runtime['colmap'])
        env = os.environ.copy()
        env['PATH'] = str(colmap.parent) + os.pathsep + env.get('PATH', '')
        command = [str(colmap), 'model_converter', '--input_path', str(project / 'undistorted/sparse'),
                   '--output_path', str(text_model), '--output_type', 'TXT']
        run_process(command, root, env, root / 'camera-export.log', 120)
        if reference_frame < 0:
            names = sorted(row[9] for row in image_records(text_model))
            if not names:
                raise ValueError('No registered view is available for finishing.')
            reference_frame = int(Path(names[0]).stem.removeprefix('frame_'))
        name = f'frame_{reference_frame:05d}.png'
        rotation, translation, intrinsics, width, height = read_camera(text_model, name)
        original = Path(receipt['original'])
        native_geometry = Path(receipt.get('selected_native_mesh', original))
        source_mesh = trimesh.load(native_geometry, force='mesh', process=False, skip_materials=True)
        source_mesh.merge_vertices(merge_tex=True, merge_norm=True)
        if len(source_mesh.faces) > 5_000_000:
            raise ValueError('Hi3D input exceeds 5 million triangles; insert native Decimate Mesh before refinement')
        image_path = project / 'undistorted/images' / name
        mask_path = image_path.with_name(image_path.stem + '.mask.png')
        rgb = np.array(Image.open(image_path).convert('RGB'), dtype=np.float32) / 255.
        fg = np.array(Image.open(mask_path).convert('L'), dtype=np.float32) / 255.
        if rgb.shape[:2] != (height, width) or fg.shape != (height, width):
            raise ValueError('Camera, undistorted image and foreground mask dimensions disagree')
        sample = source_mesh.vertices[::max(1, len(source_mesh.vertices) // 30000)]
        pixels = np.rint(project_vertices(sample, rotation, translation, intrinsics)).astype(int)
        valid = (pixels[:, 0] >= 0) & (pixels[:, 0] < width) & (pixels[:, 1] >= 0) & (pixels[:, 1] < height)
        overlap = float(np.sum(fg[pixels[valid, 1], pixels[valid, 0]] > .25) / len(pixels))
        if overlap < .8:
            raise ValueError(f'Reference projection overlaps the foreground by only {overlap:.1%}; inspect camera geometry before Hi3D')
        vertices, transform = prepare(source_mesh.vertices, rotation)
        context = dict(root=str(root), project_folder=str(project), transform=transform,
                       original_obj=str(original), original_sha256=digest(original),
                       reference_path=str(image_path), reference_sha256=digest(image_path), reference_frame=reference_frame,
                       camera_file=str(text_model / 'images.txt'), camera_sha256=digest(text_model / 'images.txt'),
                       projection_foreground_fraction=overlap,
                       roundtrip_max_error=float(np.abs(restore_frame(vertices, transform) - source_mesh.vertices).max()),
                       camera_convention='COLMAP world-to-camera; original OpenMVS world restored before texturing')
        previous = root / 'source.json'
        if previous.is_file() and json.loads(previous.read_text()) != context:
            raise ValueError('Run name belongs to a different source; choose a new name to preserve existing results')
        previous.write_text(json.dumps(context, indent=2), encoding='utf-8')
        Image.fromarray(np.dstack([(rgb*255).astype('uint8'), (fg*255).astype('uint8')])).save(root / 'reference.png')
        mesh = mesh_value(vertices, source_mesh.faces)
        save_mesh(mesh, root, 'prepared-source')
        return mesh, torch.from_numpy(rgb).unsqueeze(0), torch.from_numpy(1-fg).unsqueeze(0), context


class TextureOpenMVSRefinement:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'mesh_obj': ('STRING', {'forceInput': True}), 'context': ('V360_REFINEMENT',),
            'texture_size': ([2048, 4096, 8192], {'default': 4096}),
            'cpu_threads': ('INT', {'default': 8, 'min': 1, 'max': 64}),
            'gpu_index': ('INT', {'default': 0, 'min': 0, 'max': 7}),
            'outlier_threshold': ('FLOAT', {'default': .06, 'min': 0., 'max': 1.}),
            'seam_leveling': ('BOOLEAN', {'default': True}),
            'timeout_minutes': ('INT', {'default': 60, 'min': 1, 'max': 240}),
        }, 'optional': {
            'source_geometry': (['Connected clean mesh', 'Original reconstruction'], {'default': 'Connected clean mesh'}),
            'advanced_texture': ('STRING', {'default': '{}', 'multiline': True, 'tooltip': 'Native TextureMesh scalar options. Includes separate global/local seam leveling, patch quality, image scale, empty color, sharpness and lossless output. Paths and clean topology are protected.'}),
        }}
    RETURN_TYPES = ('FILE_3D', 'STRING')
    RETURN_NAMES = ('textured_preview', 'texture_report')
    FUNCTION = 'texture'
    CATEGORY = CATEGORY

    def texture(self, mesh_obj, context, texture_size, cpu_threads, gpu_index, outlier_threshold, seam_leveling, timeout_minutes,
                source_geometry='Connected clean mesh', advanced_texture='{}'):
        root, project = Path(context['root']).resolve(), Path(context['project_folder']).resolve()
        mesh_obj = Path(context['original_obj'] if source_geometry == 'Original reconstruction' else mesh_obj).resolve()
        if (source_geometry != 'Original reconstruction' and not mesh_obj.is_relative_to(root)) or not mesh_obj.is_file():
            raise ValueError('Choose this run\'s saved clean geometry')
        if digest(context['original_obj']) != context['original_sha256'] or digest(context['camera_file']) != context['camera_sha256']:
            raise ValueError('Original reconstruction/cameras changed; choose a new refinement run')
        runtime = runtime_settings()
        executable, runtime_info = texture_runtime(runtime)
        extra = json.loads(advanced_texture)
        if not isinstance(extra, dict):
            raise ValueError('Advanced texture controls must be a JSON object')
        settings = dict(texture_size=texture_size, cpu_threads=cpu_threads, gpu_index=gpu_index,
                        outlier_threshold=outlier_threshold, seam_leveling=seam_leveling, advanced_texture=extra,
                        source_geometry=source_geometry)
        identity = json.dumps(dict(mesh=digest(mesh_obj), settings=settings, runtime=runtime_info, revision=2), sort_keys=True)
        folder = root / ('texture-' + hashlib.sha256(identity.encode()).hexdigest()[:12])
        folder.mkdir(exist_ok=True)
        obj, glb = folder / 'texturedMesh.obj', folder / 'texturedMesh.glb'
        options = {'input-file': project/'openmvs/scene_dense.mvs', 'mesh-file': mesh_obj,
                   'output-file': folder/'texturedMesh.mvs', 'working-folder': project/'openmvs',
                   'export-type': 'obj', 'decimate': 1, 'close-holes': 0, 'max-threads': cpu_threads,
                   'cuda-device': gpu_index, 'ignore-mask-label': 0, 'max-texture-size': texture_size,
                   'outlier-threshold': outlier_threshold, 'global-seam-leveling': seam_leveling,
                   'local-seam-leveling': seam_leveling}
        options = texture_options(options, extra, runtime_info, preserve_geometry=True)
        command = [str(executable), *arglist(options)]
        (folder/'command.json').write_text(json.dumps(command, indent=2), encoding='utf-8')
        release_models()
        started = time.monotonic()
        cached_report = json.loads((folder/'result.json').read_text(encoding='utf-8')) if (folder/'result.json').is_file() else None
        if cached_report is None:
            run_process(command, folder, os.environ.copy(), folder/'texture.log', timeout_minutes*60)
        source = trimesh.load(mesh_obj, force='mesh', process=False)
        scene = trimesh.load(obj, force='scene', process=False)
        count = sum(len(g.faces) for g in scene.geometry.values())
        if count != len(source.faces):
            raise ValueError(f'Final texture geometry changed: {len(source.faces)} -> {count} triangles; preserve clean checkpoint and inspect native output')
        texture_files = list(folder.glob('*.png')) + list(folder.glob('*.jpg'))
        if not texture_files or not any(max(b[1] for b in Image.open(p).convert('RGB').getextrema()) > 0 for p in texture_files):
            raise ValueError('Native texture output is empty or black')
        presentation = export_asset(scene, context, glb)
        report = dict(settings=settings, faces=count, texture_files=[str(p) for p in texture_files],
                      elapsed_seconds=cached_report['elapsed_seconds'] if cached_report else round(time.monotonic()-started,2), original=str(obj), preview=str(glb),
                      runtime=runtime_info, presentation=presentation,
                      provenance='OpenMVS TextureMesh with original solved cameras; ' + source_geometry + '; native UVs, no decimation')
        (folder/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return Types.File3D(str(glb)), json.dumps(report)
