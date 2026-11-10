"""Settle the authors' sewn surface on a character using Blender cloth."""
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit import clear_scene, find_target, load_glb, surface

FABRICS = {
    'light': {'mass': .13, 'tension_stiffness': 12., 'compression_stiffness': 12.,
              'shear_stiffness': 5., 'bending_stiffness': .18},
    'medium': {'mass': .22, 'tension_stiffness': 24., 'compression_stiffness': 24.,
               'shear_stiffness': 12., 'bending_stiffness': .7},
    'heavy': {'mass': .40, 'tension_stiffness': 40., 'compression_stiffness': 40.,
              'shear_stiffness': 23., 'bending_stiffness': 2.5},
}


def active_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def mesh_points(mesh):
    values = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get('co', values)
    return values.reshape(-1, 3)


def penetrations(vertices, body):
    hits = []
    for index, vertex in enumerate(vertices):
        point, normal, _, _ = body.find_nearest(Vector(vertex))
        depth = (point - Vector(vertex)).dot(normal)
        if depth > .001:
            hits.append((index, depth))
    return hits


def outline(hits):
    return {'vertices': len(hits), 'depth_mm': round(max((depth for _, depth in hits), default=0) * 1000, 2)}


def initial_clearance(cloth, body, margin):
    moved = 0
    for vertex in cloth.data.vertices:
        point, normal, _, _ = body.find_nearest(vertex.co)
        gap = (vertex.co - point).dot(normal)
        if gap < margin:
            vertex.co += (margin - gap) * normal
            moved += 1
    cloth.data.update()
    return moved


def simulate(cloth, target, options, attachments):
    clearance = max(.003, options['clearance'] / 1000)
    # The input has shared seam vertices and loop UVs. Preserve that topology.
    target.modifiers.new('Rest-pose character', 'COLLISION')
    target.collision.thickness_outer = .003
    pin = cloth.vertex_groups.new(name='Drape support')
    points = mesh_points(cloth.data)
    support = sorted({index for label in ('left_collar', 'right_collar', 'strapless_top', 'lower_interface')
                      for index in attachments.get(label, []) if 0 <= index < len(points)})
    if not support:
        # Older meshes predate author attachment metadata.
        top = np.quantile(points[:, 2], .965)
        support = np.flatnonzero(points[:, 2] >= top).tolist()
    pin.add(support, 1., 'REPLACE')
    modifier = cloth.modifiers.new('Settled garment', 'CLOTH')
    for prop, value in FABRICS[options['fabric']].items():
        setattr(modifier.settings, prop, value)
    modifier.settings.quality = 8
    modifier.settings.vertex_group_mass = pin.name
    modifier.settings.air_damping = 3.
    collision = modifier.collision_settings
    collision.use_collision = True
    collision.distance_min = clearance
    collision.collision_quality = 4
    collision.use_self_collision = True
    collision.self_distance_min = .0025
    scene = bpy.context.scene
    scene.render.fps = 24
    frames = options['frames']
    modifier.point_cache.frame_start = 1
    modifier.point_cache.frame_end = frames
    for frame in range(1, frames + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        if frame == 1 or frame % 8 == 0 or frame == frames:
            print(f'Cloth simulation frame {frame} of {frames}', flush=True)
    pin_name = pin.name
    active_only(cloth)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    remaining = cloth.vertex_groups.get(pin_name)
    if remaining is not None:
        cloth.vertex_groups.remove(remaining)
    return points


def export(path, objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True,
                              export_animations=False, export_skins=False)


def preview_body(body):
    copy = body.copy()
    copy.data = body.data.copy()
    world = body.matrix_world.copy()
    copy.parent = None
    copy.matrix_world = world
    copy.modifiers.clear()
    copy.name = 'Rest-pose body'
    bpy.context.collection.objects.link(copy)
    material = bpy.data.materials.new('Body guide')
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value = (.11, .25, .36, 1)
    shader.inputs['Alpha'].default_value = .33
    copy.data.materials.clear()
    copy.data.materials.append(material)
    for face in copy.data.polygons:
        face.material_index = 0
    return copy


def preview_hits(cloth, hits):
    # Small octahedra stay visible in standard GLB viewers without point extensions.
    radius = .0035
    offsets = [Vector(p) * radius for p in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]]
    faces = [(0,2,4),(2,1,4),(1,3,4),(3,0,4),(2,0,5),(1,2,5),(3,1,5),(0,3,5)]
    stride = max(1, len(hits) // 1200)
    positions, triangles = [], []
    for index, _ in hits[::stride]:
        start = len(positions)
        positions.extend(cloth.data.vertices[index].co + delta for delta in offsets)
        triangles.extend(tuple(start + j for j in face) for face in faces)
    mesh = bpy.data.meshes.new('Penetration marks')
    mesh.from_pydata(positions, [], triangles)
    marks = bpy.data.objects.new('Clipping markers', mesh)
    bpy.context.collection.objects.link(marks)
    material = bpy.data.materials.new('Clipping')
    material.diffuse_color = (.95, .015, .02, 1)
    mesh.materials.append(material)
    return marks


def main(options):
    output = Path(options['output'])
    clear_scene()
    _, body = find_target(load_glb(options['character']))
    mesh_path = Path(options['mesh'])
    sewn_obj = mesh_path.with_suffix('.obj')
    if sewn_obj.is_file():
        # The OBJ has one position per sewn vertex and separate UV loop indices.
        # glTF stores a separate vertex for each UV seam, which opens cloth springs.
        bpy.ops.wm.obj_import(filepath=str(sewn_obj), global_scale=.01)
        pieces = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
    else:
        pieces = [obj for obj in load_glb(mesh_path) if obj.type == 'MESH']
    if not pieces:
        raise ValueError('The sewn garment has no surface to drape.')
    active_only(pieces[0])
    for piece in pieces[1:]:
        piece.select_set(True)
    if len(pieces) > 1:
        bpy.ops.object.join()
    cloth = bpy.context.view_layer.objects.active
    cloth.name = 'Settled garment'
    offset = Vector([options['x'], options['y'], options['z']])
    cloth.data.transform(Matrix.Translation(offset) @ Matrix.Scale(options['scale'], 4) @ cloth.matrix_world)
    cloth.parent = None
    cloth.matrix_world = Matrix.Identity(4)
    if not cloth.data.uv_layers or not cloth.data.materials:
        raise ValueError('The sewn garment must have its original pattern UVs and material.')
    triangles = len(cloth.data.polygons)
    bvh = surface(body)
    original = mesh_points(cloth.data)
    before = penetrations(original, bvh)
    body_preview = preview_body(body)
    if before:
        marks = preview_hits(cloth, before)
        export(output / 'starting-fit.glb', [cloth, body_preview, marks])
        bpy.data.objects.remove(marks, do_unlink=True)
    else:
        export(output / 'starting-fit.glb', [cloth, body_preview])
    adjusted = initial_clearance(cloth, bvh, max(.008, options['clearance'] / 1000 + .003))
    attachments_file = mesh_path.with_name('pattern-attachments.json')
    attachments = json.loads(attachments_file.read_text(encoding='utf-8')) if sewn_obj.is_file() and attachments_file.is_file() else {}
    baseline = simulate(cloth, body, options, attachments)
    settled = mesh_points(cloth.data)
    if settled.shape != original.shape or not np.isfinite(settled).all() or len(cloth.data.polygons) != triangles:
        raise ValueError('The cloth solve did not preserve finite garment geometry and topology.')
    movement = np.linalg.norm(settled - baseline, axis=1)
    if movement.max() < .001 or movement.max() > max(.5, float(np.ptp(original, axis=0).max())):
        raise ValueError('The cloth did not settle reliably. Adjust garment placement, scale or fabric and retry.')
    after = penetrations(settled, bvh)
    cloth.data.polygons.foreach_set('use_smooth', np.ones(triangles, dtype=bool))
    export(output / 'draped-garment.glb', [cloth])
    marks = [preview_hits(cloth, after)] if after else []
    export(output / 'draped-fit.glb', [cloth, body_preview, *marks])
    report = {'solver': 'Blender Cloth', 'blender': bpy.app.version_string, 'fabric': options['fabric'],
              'frames': options['frames'], 'triangles': triangles, 'vertices': len(settled),
              'before': outline(before), 'after': outline(after), 'initial_clearance_vertices': adjusted,
              'simulated_movement_mm': round(float(np.median(movement)) * 1000, 2),
              'max_simulated_movement_mm': round(float(movement.max()) * 1000, 2),
              'needs_review': bool(after)}
    (output / 'drape-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    try:
        request = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
        main(request)
    except Exception as error:
        print('ValueError:', error, flush=True)
        raise

