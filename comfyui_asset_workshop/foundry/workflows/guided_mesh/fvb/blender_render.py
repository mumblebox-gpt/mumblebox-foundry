"""Fixed Blender background worker. It runs only for an explicitly started job.

Usage: blender --background --factory-startup --disable-autoexec --python FILE -- REQUEST.json
No generated Python or Blender MCP/add-on is involved.
"""
import hashlib
import json
import math
import os
import sys
from pathlib import Path


def configure_compositor(scene,folder):
    """Blender 5.2's unified compositor API; no rendering in this function."""
    import bpy
    tree=bpy.data.node_groups.new('FVB diagnostic compositor','CompositorNodeTree')
    scene.compositing_node_group=tree; scene.render.use_compositing=True
    tree.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
    layers=tree.nodes.new('CompositorNodeRLayers')
    group_output=tree.nodes.new('NodeGroupOutput')
    tree.links.new(layers.outputs['Image'],group_output.inputs['Image'])
    depth_map=tree.nodes.new('ShaderNodeMapRange'); depth_map.inputs['To Min'].default_value=1; depth_map.inputs['To Max'].default_value=0; depth_map.clamp=True
    tree.links.new(layers.outputs['Depth'],depth_map.inputs['Value'])
    depth_mask=tree.nodes.new('ShaderNodeMath'); depth_mask.operation='MULTIPLY'
    tree.links.new(depth_map.outputs[0],depth_mask.inputs[0]); tree.links.new(layers.outputs['Alpha'],depth_mask.inputs[1])
    normal_sep=tree.nodes.new('ShaderNodeSeparateXYZ'); tree.links.new(layers.outputs['Normal'],normal_sep.inputs[0])
    normal_comb=tree.nodes.new('ShaderNodeCombineXYZ'); normal_rows=[]
    for channel in range(3):
        components=[]
        for axis in range(3):
            mul=tree.nodes.new('ShaderNodeMath'); mul.operation='MULTIPLY'
            tree.links.new(normal_sep.outputs[axis],mul.inputs[0]); components.append(mul)
        plus=tree.nodes.new('ShaderNodeMath'); plus.operation='ADD'
        tree.links.new(components[0].outputs[0],plus.inputs[0]); tree.links.new(components[1].outputs[0],plus.inputs[1])
        total=tree.nodes.new('ShaderNodeMath'); total.operation='ADD'
        tree.links.new(plus.outputs[0],total.inputs[0]); tree.links.new(components[2].outputs[0],total.inputs[1])
        remap=tree.nodes.new('ShaderNodeMath'); remap.operation='MULTIPLY_ADD'; remap.inputs[1].default_value=.5; remap.inputs[2].default_value=.5
        tree.links.new(total.outputs[0],remap.inputs[0])
        mask=tree.nodes.new('ShaderNodeMath'); mask.operation='MULTIPLY'
        tree.links.new(remap.outputs[0],mask.inputs[0]); tree.links.new(layers.outputs['Alpha'],mask.inputs[1])
        tree.links.new(mask.outputs[0],normal_comb.inputs[channel]); normal_rows.append(components)
    outputs={}
    for name,socket in [('depth',depth_mask.outputs[0]),('normal',normal_comb.outputs[0]),('alpha',layers.outputs['Alpha'])]:
        output=tree.nodes.new('CompositorNodeOutputFile'); output.directory=str(folder/name); output.file_name=name
        output.format.media_type='IMAGE'; output.format.file_format='PNG'; output.format.color_mode='RGBA'; output.format.color_depth='16'
        output.save_as_render=False
        output.file_output_items.new('RGBA','Image')
        tree.links.new(socket,output.inputs['Image']); outputs[name]=output
    return depth_map,normal_rows,outputs


def main(request_path):
    import bpy
    import numpy as np
    from mathutils import Matrix
    # Blender's Python uses the same small package directly; no host torch imports.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from fvb.camera_math import validate_camera

    request=json.loads(Path(request_path).read_text(encoding='utf-8'))
    folder=Path(request['output']).resolve(); folder.mkdir(parents=True,exist_ok=True)
    proxy=Path(request['proxy']).resolve()
    if not proxy.is_file() or hashlib.sha256(proxy.read_bytes()).hexdigest()!=request['proxy_sha256']:
        raise ValueError('Proxy changed after the render request was saved.')
    data=np.load(proxy,allow_pickle=False)
    vertices=np.asarray(data['vertices'],dtype=np.float64)
    faces=np.asarray(data['faces'],dtype=np.int64)
    colors=np.asarray(data['vertex_colors'],dtype=np.float32) if 'vertex_colors' in data else None
    transform=np.asarray(request['cameras'][0]['mesh_to_blender'])
    vertices=(np.c_[vertices,np.ones(len(vertices))]@transform.T)[:,:3]
    if not np.isfinite(vertices).all() or not len(faces):
        raise ValueError('Invalid proxy geometry.')
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    mesh=bpy.data.meshes.new('FVB normalized proxy')
    mesh.from_pydata(vertices.tolist(),[],faces.tolist()); mesh.update()
    obj=bpy.data.objects.new('Proxy',mesh); bpy.context.collection.objects.link(obj)
    processing=dict(material=request.get('guide_material','source_color'),cleanup=request.get('proxy_cleanup','off'),
        smooth_factor=request.get('guide_smooth_factor',.25),smooth_iterations=request.get('guide_smooth_iterations',2))
    if processing['cleanup']=='smooth_surface':
        # This object is already a guide-only copy; the immutable proxy arrays stay untouched.
        bpy.context.view_layer.objects.active=obj;obj.select_set(True)
        modifier=obj.modifiers.new('Optional guide smoothing','SMOOTH')
        modifier.factor=processing['smooth_factor'];modifier.iterations=processing['smooth_iterations']
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        mesh=obj.data
    evaluated=np.empty(len(mesh.vertices)*3,dtype=np.float32);mesh.vertices.foreach_get('co',evaluated)
    processing['evaluated_positions_sha256']=hashlib.sha256(evaluated.tobytes()).hexdigest()
    material=bpy.data.materials.new('Coarse source color'); material.use_nodes=True
    principled=material.node_tree.nodes.get('Principled BSDF')
    if processing['material']=='neutral_clay':principled.inputs['Base Color'].default_value=(.55,.55,.55,1)
    else:
        if colors is None:raise ValueError('Source-color guides require saved proxy vertex colors.')
        if colors.shape[-1]==3:colors=np.c_[colors,np.ones(len(colors))]
        attr=mesh.color_attributes.new(name='ProxyColor',type='FLOAT_COLOR',domain='CORNER')
        attr.data.foreach_set('color',colors[faces.reshape(-1)].astype(np.float32).ravel())
        color=material.node_tree.nodes.new('ShaderNodeVertexColor');color.layer_name='ProxyColor'
        material.node_tree.links.new(color.outputs['Color'],principled.inputs['Base Color'])
    principled.inputs['Roughness'].default_value=.8
    mesh.materials.append(material)
    scene=bpy.context.scene
    scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=int(request['samples'])
    scene.render.threads_mode='FIXED'; scene.render.threads=int(request['threads'])
    scene.render.resolution_x=request['cameras'][0]['width']; scene.render.resolution_y=request['cameras'][0]['height']; scene.render.resolution_percentage=100
    scene.render.pixel_aspect_x=1; scene.render.pixel_aspect_y=1
    scene.render.use_border=False; scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGBA'
    scene.render.image_settings.color_depth='8'
    scene.view_settings.view_transform='Standard'; scene.view_settings.look='None'
    scene.view_settings.exposure=0; scene.view_settings.gamma=1
    world=bpy.data.worlds.new('Neutral world'); world.use_nodes=True
    world.node_tree.nodes['Background'].inputs['Color'].default_value=(.8,.8,.8,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=.6; scene.world=world
    for index,position in enumerate(((3,-4,5),(-4,-2,3),(0,4,5))):
        light_data=bpy.data.lights.new('Soft light '+str(index),'AREA'); light_data.energy=90; light_data.shape='DISK'; light_data.size=4
        light=bpy.data.objects.new(light_data.name,light_data); bpy.context.collection.objects.link(light)
        light.location=position; light.rotation_euler=(-light.location).to_track_quat('-Z','Y').to_euler()
    layer=scene.view_layers[0]; layer.use_pass_z=True; layer.use_pass_normal=True
    depth_map,normal_rows,diagnostic_outputs=configure_compositor(scene,folder)
    records=[]
    for camera_record in request['cameras']:
        validate_camera(camera_record)
        ident=camera_record['id']
        data_cam=bpy.data.cameras.new(ident); data_cam.type='PERSP'; data_cam.sensor_fit='HORIZONTAL'
        data_cam.sensor_width=32; data_cam.sensor_height=32; data_cam.lens=16/math.tan(camera_record['fov_x_rad']/2)
        data_cam.shift_x=data_cam.shift_y=0; data_cam.clip_start=.001; data_cam.clip_end=1000
        camera=bpy.data.objects.new(ident,data_cam); bpy.context.collection.objects.link(camera)
        camera.matrix_world=Matrix(camera_record['c2w']); scene.camera=camera
        scene.render.filepath=str(folder/(ident+'.png'))
        depth_map.inputs['From Min'].default_value=camera_record['distance']-float(request['radius'])
        depth_map.inputs['From Max'].default_value=camera_record['distance']+float(request['radius'])
        for name,output in diagnostic_outputs.items():
            output.directory=str(folder/ident/name); output.file_name=name
        world_to_camera=np.asarray(camera.matrix_world.inverted(),dtype=float)
        for channel,components in enumerate(normal_rows):
            for axis,mul in enumerate(components):
                mul.inputs[1].default_value=float(world_to_camera[channel,axis])
        bpy.context.view_layer.update()
        actual=dict(camera_record)
        actual.update(c2w=[list(row) for row in camera.matrix_world],w2c=[list(row) for row in camera.matrix_world.inverted()],
                      fov_x_rad=float(data_cam.angle_x),fov_y_rad=float(data_cam.angle_y),lens_mm=float(data_cam.lens),
                      calibration_status='renderer_exact',proxy_sha256=request['proxy_sha256'],original_sha256=request['original_sha256'],guide_processing=processing)
        half=actual['width']/2; focal=half/math.tan(actual['fov_x_rad']/2); actual['K']=[[focal,0,half],[0,focal,half],[0,0,1]]
        validate_camera(actual)
        bpy.ops.render.render(write_still=True)
        for name in ('depth','normal','alpha'):
            emitted=list((folder/ident/name).glob('*.png'))
            if len(emitted)!=1:
                raise ValueError('Expected one diagnostic '+name+' output for '+ident)
            os.replace(emitted[0],folder/(ident+'_'+name+'.png'))
        actual['render_file']=ident+'.png'
        actual['render_sha256']=hashlib.sha256((folder/actual['render_file']).read_bytes()).hexdigest()
        actual['diagnostics']={name:ident+'_'+name+'.png' for name in ('depth','normal','alpha')}
        actual['diagnostic_encoding']=dict(depth='blender_linear_near_white_v1',alpha='coverage_in_rgb',
            depth_from_min=camera_record['distance']-float(request['radius']),
            depth_from_max=camera_record['distance']+float(request['radius']),depth_to_min=1,depth_to_max=0,
            depth_masked_by_alpha=True,save_as_render=False)
        records.append(actual)
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/'proxy-views.blend'))
    temporary=folder/'cameras.json.tmp'; temporary.write_text(json.dumps({'schema':'fvb.cameras/1','frames':records},indent=2),encoding='utf-8')
    os.replace(temporary,folder/'cameras.json')
    print('FVB complete: '+str(len(records))+' calibrated renders',flush=True)


if __name__=='__main__':
    if '--' not in sys.argv or len(sys.argv[sys.argv.index('--')+1:])!=1:
        raise SystemExit('Pass one structured render request after --')
    main(sys.argv[sys.argv.index('--')+1])
