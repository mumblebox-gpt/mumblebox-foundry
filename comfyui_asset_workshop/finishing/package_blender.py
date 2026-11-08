"""Packaging-only Blender conversion and relocated re-import; no remeshing or baking."""
import bpy,json,sys,shutil,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).parent))
from package_catalog import FileRecord,VariantRecord,VARIANTS
from dataclasses import asdict
req=json.loads(Path(sys.argv[sys.argv.index("--")+1]).read_text(encoding="utf-8"))
stage=sys.argv[sys.argv.index("--")+2];job=Path(req["job"])
def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)
def select(obj):
    for o in bpy.context.scene.objects:o.select_set(False)
    obj.hide_set(False);obj.select_set(True);bpy.context.view_layer.objects.active=obj
def summary(obj):
    me=obj.data;me.calc_loop_triangles()
    bounds=[obj.matrix_world@Vector(c) for c in obj.bound_box]
    lo=[min(c[i] for c in bounds) for i in range(3)]
    hi=[max(c[i] for c in bounds) for i in range(3)]
    return {"vertices":len(me.vertices),"polygons":len(me.polygons),
        "triangles":sum(len(p.vertices)==3 for p in me.polygons),
        "quads":sum(len(p.vertices)==4 for p in me.polygons),
        "ngons":sum(len(p.vertices)>4 for p in me.polygons),
        "uv_layers":len(me.uv_layers),"bounds":[lo,hi],
        "dimensions":[b-a for a,b in zip(lo,hi)]}
def one_mesh():
    obs=[o for o in bpy.context.scene.objects if o.type=="MESH"]
    if len(obs)!=1:raise ValueError("Package conversion expects one mesh object; got "+str(len(obs)))
    return obs[0]
def glb(path):
    bpy.ops.import_scene.gltf(filepath=str(path));return one_mesh()
def image_nodes(socket,seen=None):
    seen=set() if seen is None else seen;found=[]
    for link in socket.links:
        node=link.from_node
        if node.as_pointer() in seen:continue
        seen.add(node.as_pointer())
        if node.type=="TEX_IMAGE" and node.image:found.append(node)
        else:
            for inp in node.inputs:found.extend(image_nodes(inp,seen))
    return found
def textures(obj,folder,relative,key):
    folder.mkdir(parents=True,exist_ok=True);records=[];specs=[];saved={}
    for mi,mat in enumerate(obj.data.materials):
        if not mat or not mat.use_nodes:continue
        shader=next((n for n in mat.node_tree.nodes if n.type=="BSDF_PRINCIPLED"),None)
        if shader is None:raise ValueError("Unsupported material without Principled BSDF")
        uses={}
        for sock,role in (("Base Color","base-color"),("Roughness","roughness"),("Metallic","metallic"),("Normal","normal-opengl"),("Emission Color","emissive"),("Alpha","opacity")):
            if sock not in shader.inputs:continue
            for n in image_nodes(shader.inputs[sock]):uses.setdefault(n.image.name,{"image":n.image,"roles":set()})["roles"].add(role)
        for entry in uses.values():
            img=entry["image"];roles=entry["roles"]
            role="metallic-roughness" if {"metallic","roughness"}<=roles else next((r for r in ("base-color","normal-opengl","emissive","roughness","metallic","opacity") if r in roles),None)
            if not role:raise ValueError("Unclassified material image")
            token=(img.as_pointer(),role)
            if token in saved:continue
            name=(f"material-{mi+1}-" if len(obj.data.materials)>1 else "")+role+".png"
            dest=folder/name;rel=relative+"Textures/"+name
            img.filepath_raw=str(dest);img.file_format="PNG";img.save()
            if img.packed_file:img.unpack(method="REMOVE")
            img.filepath=str(dest);img.reload();saved[token]=rel
            interpretation={"base-color":"sRGB base color","metallic-roughness":"Linear data; green = roughness, blue = metallic","normal-opengl":"Tangent-space normal, OpenGL +Y","emissive":"sRGB emissive color"}.get(role,"Linear "+role+" data")
            records.append(FileRecord(rel,"texture",key,interpretation+".","png",role))
            specs.append({"path":rel,"dimensions":list(img.size),"interpretation":interpretation})
        # Every linked texture must be explicitly represented; no hidden source paths.
        expected={x["image"].as_pointer() for x in uses.values()}
        for n in mat.node_tree.nodes:
            if n.type=="TEX_IMAGE" and n.image and n.outputs and any(s.is_linked for s in n.outputs) and n.image.as_pointer() not in expected:
                raise ValueError("Material has an unsupported linked texture; add its role to the package catalog")
    return records,specs
def fbx(obj,path):
    select(obj)
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={"MESH"},
      global_scale=1.0,apply_unit_scale=True,apply_scale_options="FBX_SCALE_UNITS",
      axis_forward="-Z",axis_up="Y",bake_space_transform=False,use_mesh_modifiers=False,
      use_triangles=False,mesh_smooth_type="OFF",use_tspace=True,add_leaf_bones=False,
      bake_anim=False,path_mode="RELATIVE",embed_textures=False)
def measured(s):
    return {k:v for k,v in s.items() if k!="bounds"}
def grounded_glb(source,target):
    frame=req.get('grounding')
    if not frame or frame.get('mode')=='original':return source,None
    from grounding import ground_glb,validate_frame
    T=validate_frame(frame);minimum=ground_glb(source,target,T,floor=True);T[1,3]-=minimum
    return str(target),T

def apply_frame(obj,matrix):
    from grounding import blender_frame
    obj.matrix_world=Matrix(blender_frame(matrix).tolist())@obj.matrix_world
    select(obj);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    obj.data.update();bpy.context.view_layer.update()

def package():
    root=Path(req["export_dir"]);files=[];variants=[];expected={}
    for key,item in req["variants"].items():
        clear();directory=item["directory"];out=root/directory;out.mkdir(parents=True,exist_ok=True)
        fmts=item["formats"];sources=item["sources"];owned=[];ex={}
        v=VariantRecord(key,directory,VARIANTS[key][2])
        def record(name,fmt,description,role="mesh",deps=()):
            rel=directory+name;owned.append(FileRecord(rel,"asset",key,description,fmt,role,tuple(deps)));return rel
        if key=="print":
            dst=out/"mesh.stl";shutil.copy2(sources["stl"],dst)
            bpy.ops.wm.stl_import(filepath=str(dst));obj=one_mesh()
            if req.get('grounding') and req['grounding']['mode']!='original':
                import numpy as np
                from grounding import validate_frame
                old_height=summary(obj)['dimensions'][2];T=validate_frame(req['grounding']);T[:3,3]=0;apply_frame(obj,T)
                height=summary(obj)['dimensions'][2]
                if height<=0:raise ValueError('The print mesh has no height')
                obj.scale=(old_height/height,)*3;select(obj);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
                lo,hi=summary(obj)['bounds'];obj.location=(-(lo[0]+hi[0])/2,-(lo[1]+hi[1])/2,-lo[2]);bpy.ops.object.transform_apply(location=True,rotation=False,scale=False)
                bpy.ops.wm.stl_export(filepath=str(dst),export_selected_objects=True)
            s=summary(obj)
            record("mesh.stl","stl","Print-oriented triangle geometry; STL does not store a unit declaration.")
            v.measurements={"geometry":measured(s),"coordinates":{"units":"Unitless STL coordinates","up_axis":"Not encoded in STL"}}
            ex["mesh.stl"]={"summary":s,"textured":False}
            v.limitations=["Physical wall thickness, fabrication and printer suitability have not been tested by this exporter."]
        elif key.startswith("quad_"):
            bpy.ops.wm.open_mainfile(filepath=sources["blend"])
            candidates=[o for o in bpy.context.scene.objects if o.type=="MESH"]
            quad=max(candidates,key=lambda o:sum(len(p.vertices)==4 for p in o.data.polygons))
            if not any(len(p.vertices)==4 for p in quad.data.polygons):raise ValueError("Quad source has no quads")
            for o in list(bpy.data.objects):
                if o!=quad:bpy.data.objects.remove(o,do_unlink=True)
            runtime_source,frame=grounded_glb(sources['runtime_glb'],job/(key+'-grounded.glb'))
            if frame is not None:apply_frame(quad,frame)
            before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=runtime_source)
            imported=[o for o in bpy.data.objects if o not in before and o.type=="MESH"]
            if len(imported)!=1:raise ValueError("Expected one runtime mesh")
            runtime=imported[0];runtime.name="Runtime_Triangles"
            tex,specs=textures(runtime,out/"Textures",directory,key);owned+=tex
            quad.data.materials.clear()
            for m in runtime.data.materials:quad.data.materials.append(m)
            a=summary(quad);r=summary(runtime);deps=[f.path for f in tex]
            v.measurements={"authoring":measured(a),"runtime":measured(r),"textures":specs,
                "coordinates":{"units":"Metres; generated scale is not calibrated","up_axis":"Z in Blender; Y in interchange files"}}
            if "obj" in fmts:
                select(quad)
                bpy.ops.wm.obj_export(filepath=str(out/"editable-quads.obj"),export_selected_objects=True,apply_modifiers=False,
                  export_uv=True,export_normals=True,export_materials=True,export_triangulated_mesh=False,
                  forward_axis="NEGATIVE_Z",up_axis="Y",path_mode="RELATIVE")
                record("editable-quads.obj","obj","Editable polygon mesh with UVs and normals.",deps=[directory+"editable-quads.mtl"])
                record("editable-quads.mtl","mtl","Material definitions for the OBJ mesh.","material",deps)
                ex["editable-quads.obj"]={"summary":a,"textured":bool(tex)}
            if "authoring_fbx" in fmts:
                fbx(quad,out/"editable-quads.fbx");record("editable-quads.fbx","fbx","Polygon-preserving authoring mesh with UVs and normals.",deps=deps)
                ex["editable-quads.fbx"]={"summary":a,"textured":bool(tex)}
            if "runtime_fbx" in fmts:
                fbx(runtime,out/"runtime.fbx");record("runtime.fbx","fbx","Triangulated runtime derivative with UVs and normals.",deps=deps)
                ex["runtime.fbx"]={"summary":r,"textured":bool(tex)}
            if "runtime_glb" in fmts:
                shutil.copy2(runtime_source,out/"runtime.glb");record("runtime.glb","glb","Preserved triangulated runtime mesh with embedded materials.")
                ex["runtime.glb"]={"summary":r,"textured":bool(tex)}
            if "blend" in fmts:
                runtime.hide_set(True);runtime.hide_render=True;select(quad)
                for mat in list(bpy.data.materials):
                    if mat.users==0:bpy.data.materials.remove(mat)
                for img in list(bpy.data.images):
                    if img.users==0:bpy.data.images.remove(img)
                bpy.ops.file.pack_all()
                bpy.ops.wm.save_as_mainfile(filepath=str(out/"editable-quads.blend"))
                record("editable-quads.blend","blend","Editable polygon master; textures packed; fixed triangulation modifier retained.")
                ex["editable-quads.blend"]={"summary":a,"textured":bool(tex)}
            v.limitations=["Retopology is an editable starting mesh, not a qualified animation rig. Skinning and deformation have not been tested.",
              "Changing topology, UVs, normals or the fixed triangulation can require rebaking.",
              "FBX and OBJ may require reconstruction of the target application's material graph from the supplied maps."]
        else:
            source,frame=grounded_glb(sources['glb'],job/(key+'-grounded.glb'));obj=glb(source);s=summary(obj)
            tex,specs=textures(obj,out/"Textures",directory,key);owned+=tex
            if "glb" in fmts:
                shutil.copy2(source,out/"mesh.glb");record("mesh.glb","glb","Preserved triangle mesh with embedded PBR materials.")
                ex["mesh.glb"]={"summary":s,"textured":bool(tex)}
            if "fbx" in fmts:
                fbx(obj,out/"mesh.fbx");record("mesh.fbx","fbx","Triangle mesh with UVs and normals; companion material maps included.",deps=[f.path for f in tex])
                ex["mesh.fbx"]={"summary":s,"textured":bool(tex)}
            v.measurements={"geometry":measured(s),"textures":specs,"coordinates":{"units":"Metres; generated scale is not calibrated","up_axis":"Y in interchange files; dimensions reported in Blender Z-up coordinates"}}
            v.limitations=["Rigging, deformation and Unreal import have not been qualified.",
                "FBX may require reconstruction of the target application's material graph from the supplied maps."]
        if req.get('grounding'):
            frame=req['grounding'];v.measurements['grounding']={'mode':frame['applied'],'correction_degrees':frame['correction_degrees'],'geometry_deformed':False}
        for f in owned:
            p=root/f.path;f.bytes=p.stat().st_size;f.sha256=hashlib.sha256(p.read_bytes()).hexdigest()
        v.file_paths=[f.path for f in owned];files+=owned;variants.append(v);expected[key]=ex
    report={"files":[asdict(f) for f in files],"variants":[asdict(v) for v in variants],"expected":expected,"blender":bpy.app.version_string}
    (job/"package-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
def verify():
    root=Path(req["verify_root"]).resolve();results={}
    for key,entries in req["expected_report"]["expected"].items():
        checks={};directory=req["variants"][key]["directory"]
        for name,expected in entries.items():
            clear();p=root/directory/name
            if p.suffix==".glb":obj=glb(p)
            elif p.suffix==".fbx":
                bpy.ops.import_scene.fbx(filepath=str(p),use_anim=False,use_custom_normals=True,use_image_search=False);obj=one_mesh()
            elif p.suffix==".obj":
                bpy.ops.wm.obj_import(filepath=str(p),forward_axis="NEGATIVE_Z",up_axis="Y");obj=one_mesh()
            elif p.suffix==".stl":
                bpy.ops.wm.stl_import(filepath=str(p));obj=one_mesh()
            elif p.suffix==".blend":
                bpy.ops.wm.open_mainfile(filepath=str(p));obj=bpy.context.view_layer.objects.active
            else:raise ValueError("Unsupported verification format")
            actual=summary(obj);want=expected["summary"]
            for field in ("polygons","triangles","quads","ngons","uv_layers"):
                if actual[field]!=want[field]:raise ValueError(f"{key}/{name}: {field} differs: {actual[field]} vs {want[field]}")
            error=max(abs(a-b) for aa,bb in zip(actual["bounds"],want["bounds"]) for a,b in zip(aa,bb))
            if error>2e-5:raise ValueError(f"{key}/{name}: bounds changed {error}")
            image_count=0
            for mat in obj.data.materials:
                if not mat or not mat.use_nodes:continue
                for node in mat.node_tree.nodes:
                    if node.type!="TEX_IMAGE" or not node.image:continue
                    img=node.image;image_count+=1
                    if not img.packed_file:
                        resolved=Path(bpy.path.abspath(img.filepath)).resolve()
                        if not resolved.is_relative_to(root) or not resolved.is_file():raise ValueError(f"Relocated texture escapes package or is missing: {resolved}")
                    if not all(img.size):raise ValueError("Empty texture after relocated import")
            if expected["textured"] and not image_count:raise ValueError("Material images were lost on relocated import")
            checks[name]={"polygons":actual["polygons"],"quads":actual["quads"],"uv_layers":actual["uv_layers"],"max_bounds_error":error,"loaded_material_images":image_count}
        results[key]={"note":f"{len(checks)} mesh file(s) re-imported in Blender {bpy.app.version_string}; polygon counts, UV layers, bounds and packaged texture paths checked. Engine-specific material behavior is not implied.","files":checks}
    (job/"package-verification.json").write_text(json.dumps({"variants":results},indent=2),encoding="utf-8")
if stage=="package":package()
elif stage=="package_verify":verify()
else:raise ValueError(stage)
