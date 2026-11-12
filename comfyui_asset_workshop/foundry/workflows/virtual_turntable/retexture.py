"""Native AliceVision texture projection onto the finished experiment mesh.

Uses the original dense SfM visibility and undistorted masked photographs. No
camera solving, video regeneration, geometry generation or AI repainting here.
"""
import json
import os
from pathlib import Path
import time
import trimesh
from PIL import Image
from comfy_api.latest import Types
from .runtime import runtime_settings
from .references import CATEGORY
from .meshroom import runtime_environment
from .processes import run_process, release_models
from .refinement import digest


def one(parent, pattern):
    values = list(parent.glob(pattern))
    if len(values) != 1:
        raise ValueError(f'Expected one original {pattern}, found {len(values)}')
    return values[0]


class RetextureRefinement:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'mesh_obj': ('STRING', {'forceInput': True}), 'context': ('V360_REFINEMENT',),
            'texture_size': ([2048, 4096, 8192], {'default': 4096}),
            'unwrap_method': (['Basic', 'LSCM', 'ABF'], {'default': 'Basic'}),
            'fill_texture_holes': ('BOOLEAN', {'default': True, 'tooltip': 'Fill unobserved texture pixels. Does not repair missing geometry.'}),
            'weight_by_projected_area': ('BOOLEAN', {'default': False, 'tooltip': 'Native useScore weighting. Leave off for dense refined geometry: subpixel triangle scores can round to zero and produce a black atlas.'}),
            'cpu_threads': ('INT', {'default': 8, 'min': 1, 'max': 64}),
            'metallic': ('FLOAT', {'default': 0., 'min': 0., 'max': 1.}),
            'roughness': ('FLOAT', {'default': .65, 'min': 0., 'max': 1.}),
            'memory_gib': ('INT', {'default': 12, 'min': 4, 'max': 48, 'tooltip': 'Native texture working-memory allowance; not a whole-process hard limit.'}),
            'timeout_minutes': ('INT', {'default': 60, 'min': 1, 'max': 240}),
        }}
    RETURN_TYPES = ('FILE_3D', 'STRING')
    RETURN_NAMES = ('textured_preview', 'texture_report')
    FUNCTION = 'texture'
    CATEGORY = CATEGORY

    def texture(self, mesh_obj, context, texture_size, unwrap_method, fill_texture_holes, cpu_threads, memory_gib, timeout_minutes, weight_by_projected_area=False, metallic=0., roughness=.65):
        root, project = Path(context['root']).resolve(), Path(context['project_folder']).resolve()
        mesh_obj = Path(mesh_obj).resolve()
        if not mesh_obj.is_relative_to(root) or not mesh_obj.is_file():
            raise ValueError('Retexturing accepts a saved mesh checkpoint from this refinement run')
        source_mesh = trimesh.load(mesh_obj, force='mesh', process=False)
        if getattr(source_mesh.visual, 'uv', None) is None:
            raise ValueError('Unwrap the entire finished mesh before texturing. Native Basic UV generation can omit unseen faces.')
        source_faces = len(source_mesh.faces)
        del source_mesh
        if digest(context['original_obj']) != context['original_sha256'] or digest(context['camera_file']) != context['camera_sha256']:
            raise ValueError('Original reconstruction or cameras changed; prepare a new run before projecting textures')
        dense = one(project / 'MeshroomCache/Meshing', '*/densePointCloud.abc')
        photographs = one(project / 'MeshroomCache/PrepareDenseScene', '*')
        runtime = runtime_settings()
        batch = Path(runtime['meshroom_batch'])
        exe = batch.parent / 'aliceVision/bin/aliceVision_texturing.exe'
        if not exe.is_file():
            raise ValueError('The existing Meshroom runtime has no AliceVision texturing executable')
        settings = dict(texture_size=texture_size, unwrap_method=unwrap_method, fill_texture_holes=fill_texture_holes,
                        weight_by_projected_area=weight_by_projected_area,
                        cpu_threads=cpu_threads, memory_gib=memory_gib, mesh_sha256=digest(mesh_obj))
        import hashlib
        identity = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]
        output = root / ('texturing-' + identity)
        output.mkdir(exist_ok=True)
        command = [str(exe), '--input', str(dense), '--imagesFolder', str(photographs),
                   '--inputMesh', str(mesh_obj), '--output', str(output), '--textureSide', str(texture_size),
                   '--downscale', '1', '--outputMeshFileType', 'obj', '--colorMappingFileType', 'png',
                   '--unwrapMethod', unwrap_method, '--visibilityRemappingMethod', 'PullPush',
                   '--subdivisionTargetRatio', '0', '--fillHoles', str(fill_texture_holes).lower(),
                   '--useScore', str(weight_by_projected_area).lower(),
                   '--padding', '5', '--multiBandDownscale', '4', '--useUDIM', 'true',
                   '--workingColorSpace', 'sRGB', '--outputColorSpace', 'sRGB',
                   '--maxCoresAvailable', str(cpu_threads), '--maxMemoryAvailable', str(memory_gib * 1024 ** 3)]
        env = runtime_environment(batch, cpu_threads)
        env['ALICEVISION_ROOT'] = str(batch.parent / 'aliceVision')
        dll_paths = [batch.parent, batch.parent / 'lib', exe.parent, batch.parent / 'aliceVision/lib']
        env['PATH'] = os.pathsep.join(map(str, dll_paths)) + os.pathsep + env.get('PATH', '')
        (output / 'command.json').write_text(json.dumps(command, indent=2), encoding='utf-8')
        release_models()
        started = time.monotonic()
        run_process(command, batch.parent, env, output / 'texturing.log', timeout_minutes * 60)
        obj = output / 'texturedMesh.obj'
        scene = trimesh.load(obj, force='scene', process=False)
        if not scene.geometry or not list(output.glob('*.png')):
            raise RuntimeError('AliceVision did not produce both textured geometry and PNG textures')
        texture_extrema = []
        for path in output.glob('texture_*.png'):
            with Image.open(path) as atlas:
                texture_extrema.append(atlas.convert('RGB').getextrema())
        if not texture_extrema or not any(high > 0 for extrema in texture_extrema for low, high in extrema):
            raise RuntimeError('Native texture atlas has no color contributions. Turn off projected-area weighting and inspect UVs/cameras; saved geometry is intact.')
        final_faces = sum(len(g.faces) for g in scene.geometry.values())
        if final_faces != source_faces:
            raise RuntimeError(f'Texturing changed the face count ({source_faces} to {final_faces}); clean master is preserved. Inspect UV coverage.')
        glb = output / 'texturedMesh.glb'
        for geometry in scene.geometry.values():
            material = geometry.visual.material.to_pbr()
            material.baseColorFactor = [1., 1., 1., 1.]
            material.metallicFactor = metallic
            material.roughnessFactor = roughness
            geometry.visual.material = material
        scene.export(glb, file_type='glb')
        report = dict(settings=settings, seconds=round(time.monotonic() - started, 2),
                      original_project=str(project), dense_visibility=str(dense), photographs=str(photographs),
                      native_obj=str(obj), glb=str(glb), texture_files=[p.name for p in output.glob('*.png')],
                      faces=final_faces, source_faces=source_faces,
                      texture_extrema=texture_extrema,
                      metallic=metallic, roughness=roughness, geometry_subdivision=False, appearance_source='original orbit frames',
                      limitation='Changed geometry may not agree with source photographs; inspect seams and silhouette')
        (output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        (root / 'README.md').write_text(
            '# Virtual 360: Hi3D refinement experiment\n\n'
            'Source reconstruction and camera files remain in the original Meshroom project.\n'
            '- source.json: camera transform, source paths and hashes.\n'
            '- reference.png: exact orbit frame with its foreground alpha.\n'
            '- prepared-source.*: geometry aligned to that reference camera.\n'
            '- refined.*: refined mesh approximately registered, then returned to the original coordinate frame.\n'
            '- clean.*: native cleanup result, before textures.\n'
            '- inference.json / alignment.json: measured Hi3D run and registration residuals.\n'
            '- texturing-*/: native OBJ/MTL/PNG, packed GLB, command, log and settings/result. Keep OBJ/MTL/textures together.\n\n'
            'Hi3D by OCEANO / Hi3D authors; T8star workbench integration; Meshroom/AliceVision; ComfyUI native cleanup. '
            'Original model/tool terms apply. Experimental generated-view geometry: no promise of measured accuracy or printability.\n', encoding='utf-8')
        return Types.File3D(str(glb)), json.dumps(report)
