"""Established CPU remeshing, CuMesh UVs and MeshLab texture rebaking."""
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image
import pymeshlab
import trimesh

ROOT = Path(__file__).parent


def comfy_uvs(upward_uvs):
    """CuMesh/MeshLab use upward V; native MESH/glTF uses image-row V."""
    result = np.array(upward_uvs, dtype=np.float32, copy=True)
    result[:, 1] = 1.0 - result[:, 1]
    return result


def simplify_mesh(mesh, target, planar_quadric=False):
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=np.array(mesh.vertices),
                              face_matrix=np.array(mesh.faces, dtype=np.int32)))
    # AutoClean merges coincident positions after topology-safe collapses and
    # reconnects intentionally separated touching sheets. Compact without welding.
    ms.meshing_decimation_quadric_edge_collapse(
        targetfacenum=target, qualitythr=.3, preserveboundary=True,
        preservenormal=True, preservetopology=True, optimalplacement=True,
        planarquadric=planar_quadric, autoclean=False)
    ms.meshing_remove_unreferenced_vertices()
    m = ms.current_mesh()
    m.compact()
    return trimesh.Trimesh(m.vertex_matrix().copy(), m.face_matrix().copy(), process=False)


def rebake_maps(source, target, folder, resolution):
    ms = pymeshlab.MeshSet()
    def layer(mesh):
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        return pymeshlab.Mesh(vertex_matrix=vertices,
                             face_matrix=np.asarray(mesh.faces, dtype=np.int32),
                             w_tex_coords_matrix=np.asarray(mesh.visual.uv[mesh.faces].reshape(-1, 2), dtype=np.float64))
    # OBJ/MTL loading initializes source texture indices, unlike the in-memory
    # wedge-UV constructor. Pad only the temporary search bbox: TransferColorSampler
    # rejects outer planes through bbox.IsInEx before its nearest-face query.
    padding = max(float(np.linalg.norm(source.extents)) * .01, 1e-8)
    padded = trimesh.Trimesh(
        np.concatenate([source.vertices, source.bounds + np.array([[-padding]*3, [padding]*3])]),
        source.faces.copy(), process=False,
        visual=trimesh.visual.TextureVisuals(
            uv=np.concatenate([source.visual.uv, np.zeros((2,2))]),
            material=source.visual.material))
    padded.export(folder / 'transfer-source.obj', include_normals=False)
    ms.load_new_mesh(str(folder / 'transfer-source.obj'))
    ms.add_mesh(layer(target), 'target')
    material = source.visual.material
    if material.baseColorTexture is None:
        raise ValueError('Source must have a base-color texture')
    images = (material.baseColorTexture, material.metallicRoughnessTexture)
    outputs = []
    for image, name in zip(images, ('base-color', 'metallic-roughness')):
        destination = folder / f'baked-{name}.png'
        if image is None:
            # glTF stores uniform roughness/metalness as factors when it has no map.
            roughness = material.roughnessFactor if material.roughnessFactor is not None else 1.0
            metallic = material.metallicFactor if material.metallicFactor is not None else 1.0
            image = Image.new('RGB', (resolution, resolution), (0, round(255 * roughness), round(255 * metallic)))
            image.save(destination)
            outputs.append(image)
            continue
        source_path = folder / f'source-{name}.png'
        image.save(source_path)
        ms.set_current_mesh(0)
        ms.set_texture_per_mesh(textname=str(source_path))
        ms.set_current_mesh(1)
        ms.transfer_attributes_to_texture_per_vertex(
            sourcemesh=0, targetmesh=1, attributeenum='Texture Color',
            upperbound=pymeshlab.PercentageValue(1.), textname=str(destination),
            textw=resolution, texth=resolution,
            overwrite=ms.mesh(1).texture_number() > 0, pullpush=True)
        ms.mesh(1).texture(0).save(str(destination))
        outputs.append(Image.open(destination).copy())
    return tuple(outputs)


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    job = Path(sys.argv[1]).parent
    arrays = np.load(request['mesh'])
    original = trimesh.Trimesh(arrays['vertices'], arrays['faces'], process=False)
    before_hash = hashlib.sha256(arrays['vertices'].tobytes() + arrays['faces'].tobytes()).hexdigest()
    target = request['target_triangles']
    method = request['method']
    started = time.monotonic()
    print(f'OPTIMIZE {method}: {len(original.faces)} -> target {target} triangles', flush=True)
    guide_faces = len(original.faces)
    if method == 'quadriflow':
        from pyquadriflow.quadriflow import quadriflow_remesh
        limit = max(target * 2, 250000)
        guide = simplify_mesh(original, limit) if len(original.faces) > limit else original
        guide_faces = len(guide.faces)
        print(f'QuadriFlow guide: {guide_faces} triangles; master remains unchanged', flush=True)
        v, f = quadriflow_remesh(np.array(guide.vertices, dtype=np.float64),
                                np.array(guide.faces, dtype=np.int32), target // 2,
                                seed=0, preserve_sharp=True, preserve_boundary=True)
        low = trimesh.Trimesh(v, f, process=False)
    elif method == 'quadric':
        low = simplify_mesh(original, target, request.get('planar_quadric', False))
    else:
        raise ValueError(f'Unsupported optimizer: {method}')
    low.export(job / 'optimized-before-uv.glb')
    from geometry import topology_report
    topology = topology_report(low.vertices, low.faces)
    raw_hash = hashlib.sha256(low.vertices.astype(np.float32).tobytes() + low.faces.astype(np.int64).tobytes()).hexdigest()
    errors = []
    for a, b in ((original, low), (low, original)):
        points, _ = trimesh.sample.sample_surface(a, 5000, seed=42)
        _, distances, _ = trimesh.proximity.closest_point(b, points)
        errors.append(distances)
    errors = np.concatenate(errors)
    diagonal = float(np.linalg.norm(original.extents))
    print('Unwrap optimized mesh; retain original coordinate frame', flush=True)
    import torch
    import cumesh
    cm = cumesh.CuMesh()
    cm.init(torch.as_tensor(np.asarray(low.vertices), dtype=torch.float32, device='cuda'),
            torch.as_tensor(np.asarray(low.faces), dtype=torch.int32, device='cuda'))
    v, f, uv, vmap = cm.uv_unwrap(
        compute_charts_kwargs={'threshold_cone_half_angle_rad': np.radians(60.),
                               'refine_iterations': 0, 'global_iterations': 1, 'smooth_strength': 1},
        xatlas_pack_charts_kwargs={'resolution': request['texture_size'], 'padding': 8,
                                  'bilinear': True, 'block_align': True}, return_vmaps=True)
    v, f, uv = v.cpu().numpy(), f.cpu().numpy(), uv.cpu().numpy()
    normals = low.vertex_normals[vmap.cpu().numpy()]
    if len(f) != len(low.faces):
        raise RuntimeError('UV preparation changed the number of triangles')
    target_mesh = trimesh.Trimesh(v, f, process=False,
                                  visual=trimesh.visual.TextureVisuals(uv=uv))
    source = trimesh.load(request['texture_source'], force='mesh', process=False)
    print('Rebake existing final-mesh color and material maps; no texture regeneration', flush=True)
    base, mr = rebake_maps(source, target_mesh, job, request['texture_size'])
    after_hash = hashlib.sha256(arrays['vertices'].tobytes() + arrays['faces'].tobytes()).hexdigest()
    if before_hash != after_hash:
        raise RuntimeError('Optimizer changed the master input arrays')
    np.savez(job / 'result.npz', vertices=v, faces=f, uvs=comfy_uvs(uv), normals=normals)
    report = {'method': method, 'target_triangles': target, 'actual_triangles': len(f),
              'quadric_autoclean_welding': False if method == 'quadric' else None,
              'input_triangles': len(original.faces), 'raw_geometry_sha256': raw_hash,
              'solver_guide_triangles': guide_faces,
              'input_arrays_unchanged': True, 'topology_before_uv': topology,
              'sampled_surface_error': {'samples': 10000, 'seed': 42,
                  'mean_fraction_bbox_diagonal': float(errors.mean() / diagonal),
                  'p95_fraction_bbox_diagonal': float(np.percentile(errors, 95) / diagonal),
                  'max_fraction_bbox_diagonal': float(errors.max() / diagonal)},
              'relative_surface_area_difference': float(abs(low.area - original.area) / original.area),
              'texture_size': request['texture_size'], 'uv_padding_pixels': 8,
              'native_uv_convention': 'image-row V; converted from upward CuMesh/MeshLab V',
              'seconds': time.monotonic() - started,
              'source_texture': request['texture_source'],
              'note': 'Surface error is sampled, not a certified Hausdorff bound. Actual quad output is triangulated for GLB.'}
    (job / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
