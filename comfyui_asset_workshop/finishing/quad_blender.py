"""Blender polygon-preserving operations for the ComfyUI finishing worker."""
import bpy,bmesh,sys,json,math,time
from pathlib import Path
import numpy as np
from mathutils import Matrix,Vector
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
from quad_contract import read_obj,write_obj
req=json.loads(Path(sys.argv[sys.argv.index("--")+1]).read_text())
stage=sys.argv[sys.argv.index("--")+2]
job=Path(req["job"])
bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)

def select(obj):
    bpy.ops.object.select_all(action="DESELECT");obj.hide_set(False);obj.select_set(True);bpy.context.view_layer.objects.active=obj

def make(name,v,f):
    me=bpy.data.meshes.new(name);me.from_pydata(v,[],f);me.update()
    ob=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(ob)
    select(ob);return ob

def summary(obj):
    me=obj.data
    return {"vertices":len(me.vertices),"polygons":len(me.polygons),"quads":sum(len(p.vertices)==4 for p in me.polygons),
            "triangles":sum(len(p.vertices)==3 for p in me.polygons),
            "uv_layers":len(me.uv_layers),"bounds":[[min((obj.matrix_world@v.co)[i] for v in me.vertices) for i in range(3)],
                                                  [max((obj.matrix_world@v.co)[i] for v in me.vertices) for i in range(3)]]}

def save_json(name,data): (job/name).write_text(json.dumps(data,indent=2))

if stage=="remesh":
    sys.path.insert(0,req["qremeshify"])
    import QRemeshify
    QRemeshify.register()
    v,f=read_obj(job/"guide.obj");obj=make("alien-guide-"+str(req["component"]),v,f)
    p=bpy.context.scene.quadwild_props
    p.enableRemesh=True;p.enableSmoothing=True;p.enableSharp=True;p.sharpAngle=35
    p.symmetryX=False;p.symmetryY=False;p.symmetryZ=False;p.useCache=False
    q=bpy.context.scene.quadpatches_props;q.scaleFact=req["initial_scale"];q.timeLimit=200
    started=time.monotonic();attempts=[]
    for attempt in range(2):
        select(obj)
        result=bpy.ops.qremeshify.remesh()
        output=bpy.context.view_layer.objects.active
        if output==obj:raise RuntimeError("QRemeshify produced no mesh")
        actual=len(output.data.polygons)
        attempts.append({"scale":q.scaleFact,"polygons":actual})
        if actual==0:raise RuntimeError("Empty quadrangulation")
        if attempt==0 and abs(actual-req["component_target"])/req["component_target"]>.15:
            q.scaleFact=max(.01,min(10,q.scaleFact*math.sqrt(actual/req["component_target"])))
            p.useCache=True
            continue
        break
    write_obj(job/"remeshed-main.obj",[list(v.co) for v in output.data.vertices],[list(p.vertices) for p in output.data.polygons])
    save_json("remesh-result.json",{"method":"QRemeshify 1.1.0","blender":bpy.app.version_string,"target":req["component_target"],"upstream_preprocess":True,"sharp_angle":35,"attempts":attempts,"seconds":time.monotonic()-started})

elif stage=="repair":
    v,f=read_obj(job/"remeshed-repair-input.obj")
    ob=make("component-local-repair",v,f);bm=bmesh.new();bm.from_mesh(ob.data)
    before={"verts":len(bm.verts),"faces":len(bm.faces),"boundary":sum(e.is_boundary for e in bm.edges)}
    # Restrict merging to vertices in a collapsed face; never weld the master or components.
    candidates=set()
    for face in bm.faces:
        verts=list(face.verts)
        if any((a.co-b.co).length<1e-10 for i,a in enumerate(verts) for b in verts[i+1:]):candidates.update(verts)
    if candidates:bmesh.ops.remove_doubles(bm,verts=list(candidates),dist=1e-10)
    bmesh.ops.dissolve_degenerate(bm,dist=1e-10,edges=list(bm.edges))
    boundary=[e for e in bm.edges if e.is_boundary]
    filled=bmesh.ops.holes_fill(bm,edges=boundary,sides=16) if boundary else {"faces":[]}
    caps=list(filled["faces"])
    # Blender can skip a triangular hole when two of its edges belong to the
    # same quad. Fill only a complete three-edge boundary cycle here. The
    # worker has already restricted every hole by size and checks the closed
    # surface again after this operation.
    remaining={e for e in bm.edges if e.is_boundary}
    while remaining:
        seed=remaining.pop();loop_edges={seed};loop_verts=set(seed.verts)
        pending=list(seed.verts)
        while pending:
            vertex=pending.pop()
            for edge in list(vertex.link_edges):
                if edge in remaining:
                    remaining.remove(edge);loop_edges.add(edge)
                    for other in edge.verts:
                        if other not in loop_verts:loop_verts.add(other);pending.append(other)
        if len(loop_edges)==3 and len(loop_verts)==3 and all(
                sum(v in e.verts for e in loop_edges)==2 for v in loop_verts):
            caps.append(bm.faces.new(list(loop_verts)))
    # Keep four-sided caps as quads. The shared fixed-triangle adapter
    # reserves unique diagonals even when two caps share opposite corners.
    large_caps = [face for face in caps if len(face.verts) > 4]
    if large_caps:
        bmesh.ops.triangulate(bm,faces=large_caps,quad_method="FIXED",ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.verts.ensure_lookup_table();bm.verts.index_update()
    write_obj(job/"remeshed-repaired.obj",[list(v.co) for v in bm.verts],[[v.index for v in f.verts] for f in bm.faces])
    save_json("remesh-repair.json",{"before":before,"collapsed_face_vertices":len(candidates),"small_boundary_caps":len(caps),
        "after":{"verts":len(bm.verts),"faces":len(bm.faces),"boundary":sum(e.is_boundary for e in bm.edges)},
        "policy":"only collapsed-face local vertices; max16edge caps; no global welding; caps may be triangles"})
    bm.free()

elif stage=="uv":
    v,f=read_obj(job/"quad-raw.obj")
    vb=[(x,-z,y) for x,y,z in v]
    ob=make("Alien_Editable_Quads",vb,f)
    for p in ob.data.polygons:p.use_smooth=True
    bpy.ops.object.mode_set(mode="EDIT");bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=16/req["texture_size"],
                             margin_method="FRACTION",area_weight=0,correct_aspect=True,scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    me=ob.data
    coords=[];uvs=[];normals=[];faces=[]
    vnorm=[v.normal.copy() for v in me.vertices]
    for p in me.polygons:
        start=len(coords)
        for li in p.loop_indices:
            vi=me.loops[li].vertex_index;c=me.vertices[vi].co;n=vnorm[vi]
            coords.append((c.x,c.z,-c.y));normals.append((n.x,n.z,-n.y))
            uvs.append(tuple(me.uv_layers.active.data[li].uv))
        for k in range(1,len(p.vertices)-1):faces.append((start,start+k,start+k+1))
    me.normals_split_custom_set([vnorm[l.vertex_index] for l in me.loops])
    np.savez(job/"bake-arrays.npz",vertices=np.asarray(coords,dtype=np.float32),faces=np.asarray(faces,dtype=np.int64),
             uvs=np.asarray(uvs,dtype=np.float32),normals=np.asarray(normals,dtype=np.float32))
    mod=ob.modifiers.new("Bake triangulation - keep for matching normal map","TRIANGULATE");mod.quad_method="FIXED";mod.ngon_method="BEAUTY"
    if hasattr(mod,"keep_custom_normals"):mod.keep_custom_normals=True
    bpy.context.scene.unit_settings.system="METRIC";bpy.context.scene.unit_settings.scale_length=1
    bpy.ops.wm.save_as_mainfile(filepath=str(job/"quad-uv.blend"))
    save_json("uv-report.json",dict(summary(ob),texture_size=req["texture_size"],padding_pixels=16,method="Blender Smart UV Project 66 degrees; polygon faces preserved; explicit fixed triangle copy"))

elif stage in ("exports","legacy"):
    out=Path(req["export_dir"]);out.mkdir(parents=True,exist_ok=True)
    maps=out/"maps";maps.mkdir(exist_ok=True)
    def clear():
        # Hidden runtime comparison objects are not selected by select_all.
        for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
    def import_glb(path):
        before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path))
        objs=[o for o in bpy.data.objects if o not in before and o.type=="MESH"]
        if len(objs)!=1:raise RuntimeError("Expected one mesh primitive object")
        return objs[0]
    def externalize(obj,prefix):
        images={}
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:continue
            for node in mat.node_tree.nodes:
                if node.type!="TEX_IMAGE" or not node.image:continue
                image=node.image
                if image.name in images:continue
                name=prefix+"-"+str(len(images))+".png"
                absolute=str(maps/name)
                image.filepath_raw=absolute;image.file_format="PNG";image.save()
                if image.packed_file:image.unpack(method="REMOVE")
                image.filepath=absolute;image.filepath_raw=absolute;image.reload()
                images[image.name]={"path":"maps/"+name,"color_space":image.colorspace_settings.name}
        return images
    def fbx(obj,path):
        select(obj)
        bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={"MESH"},
            global_scale=1.0,apply_unit_scale=True,apply_scale_options="FBX_SCALE_UNITS",
            axis_forward="-Z",axis_up="Y",bake_space_transform=False,use_mesh_modifiers=False,
            use_triangles=False,mesh_smooth_type="OFF",use_tspace=True,add_leaf_bones=False,
            bake_anim=False,path_mode="COPY",embed_textures=False)
    def verify(path,expected,kind):
        clear()
        if kind=="fbx":bpy.ops.import_scene.fbx(filepath=str(path),use_anim=False,use_custom_normals=True)
        else:bpy.ops.wm.obj_import(filepath=str(path),forward_axis="NEGATIVE_Z",up_axis="Y")
        objs=[o for o in bpy.context.scene.objects if o.type=="MESH"]
        if len(objs)!=1:raise RuntimeError("Roundtrip has unexpected mesh count")
        obj=objs[0];actual=summary(obj)
        if actual["polygons"]!=expected["polygons"] or actual["quads"]!=expected["quads"]:raise RuntimeError("Roundtrip changed polygon arity/count")
        error=max(abs(a-b) for aa,bb in zip(expected["bounds"],actual["bounds"]) for a,b in zip(aa,bb))
        if error>2e-5:raise RuntimeError("Roundtrip changed scale/axes/bounds: "+str(error))
        if not actual["uv_layers"]:raise RuntimeError("UV layer lost")
        actual["max_bound_error"]=error;actual["materials"]=len(obj.data.materials)
        actual["images"]=[{"path":bpy.path.abspath(n.image.filepath),"exists":Path(bpy.path.abspath(n.image.filepath)).is_file()}
                           for mat in obj.data.materials if mat and mat.use_nodes
                           for n in mat.node_tree.nodes if n.type=="TEX_IMAGE" and n.image]
        if not actual["materials"]:raise RuntimeError("Material assignment lost")
        if any(not i["exists"] for i in actual["images"]):raise RuntimeError("Export texture path is missing")
        return actual
    if stage=="exports":
        bpy.ops.wm.open_mainfile(filepath=str(job/"quad-uv.blend"))
        quad=bpy.data.objects.get("Alien_Editable_Quads")
        runtime=import_glb(out/"runtime.glb");runtime.name="Alien_Runtime_Triangles"
        images=externalize(runtime,"alien")
        quad.data.materials.clear()
        for mat in runtime.data.materials:quad.data.materials.append(mat)
        expected=summary(quad);runtime_expected=summary(runtime)
        select(quad)
        bpy.ops.wm.obj_export(filepath=str(out/"editable-quads.obj"),export_selected_objects=True,
                              apply_modifiers=False,export_uv=True,export_normals=True,export_materials=True,
                              export_triangulated_mesh=False,forward_axis="NEGATIVE_Z",up_axis="Y",path_mode="COPY")
        fbx(quad,out/"editable-quads.fbx")
        fbx(runtime,out/"runtime.fbx")
        # Editable mesh remains authoritative; runtime is a hidden comparison copy.
        runtime.hide_set(True);runtime.hide_render=True;select(quad)
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type=="VIEW_3D":
                    area.spaces.active.region_3d.view_distance=1.6
                    area.spaces.active.region_3d.view_location=quad.location+Vector((0,0,.1))
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(out/"editable-quads.blend"))
        checks={"authoring_fbx":verify(out/"editable-quads.fbx",expected,"fbx"),
                "authoring_obj":verify(out/"editable-quads.obj",expected,"obj"),
                "runtime_fbx":verify(out/"runtime.fbx",runtime_expected,"fbx")}
        bpy.ops.wm.open_mainfile(filepath=str(out/"editable-quads.blend"))
        checks["blend"]=summary(bpy.data.objects["Alien_Editable_Quads"])
        if checks["blend"]["quads"]!=expected["quads"]:raise RuntimeError("BLEND lost quads")
        save_json("export-report.json",{"expected_authoring":expected,"expected_runtime":runtime_expected,
             "roundtrip":checks,"textures":images,"units":"metres; generated source scale is not a real-world measurement",
             "authoring_up":"Z","interchange_up":"Y","blender":bpy.app.version_string,
             "normal_convention":"OpenGL +Y; FBX material graph may need target-engine reconstruction from companion maps",
             "unreal_import_tested":False})
    else:
        results={}
        for label,path in req["legacy_sources"].items():
            clear();obj=import_glb(path);obj.name="Alien_"+label
            images=externalize(obj,label);expected=summary(obj)
            fbx(obj,out/(label+".fbx"))
            results[label]={"source":path,"expected":expected,"textures":images,
                            "roundtrip":verify(out/(label+".fbx"),expected,"fbx")}
        save_json("export-report.json",{"legacy_exports":results,"blender":bpy.app.version_string,"unreal_import_tested":False})
