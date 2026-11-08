"""Standalone optional finishing nodes; no GUI or existing generation changes."""
import hashlib,json,os,shutil,subprocess,time,uuid
from pathlib import Path
from .quad_contract import safe_name
HERE=Path(__file__).parent
from .runtime import work_root, worker_python, settings

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def run(req,stage,check_interrupt):
    import psutil
    job=Path(req["job"]);log=job/(stage+"-worker.log")
    req.update(settings())
    (job/"request.json").write_text(json.dumps(req,indent=2),encoding="utf-8")
    cmd=[worker_python(),"-u",str(HERE/"quad_worker.py"),str(job/"request.json"),stage]
    start=time.monotonic();peak=0;children={}
    with log.open("w",encoding="utf-8") as out:
        p=subprocess.Popen(cmd,stdout=out,stderr=subprocess.STDOUT,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        try:
            while p.poll() is None:
                check_interrupt()
                try:
                    proc=psutil.Process(p.pid);current=[proc]+proc.children(recursive=True)
                    for child in current:children[child.pid]=child
                    peak=max(peak,sum(x.memory_info().rss for x in current if x.is_running()))
                except psutil.Error:pass
                if time.monotonic()-start>1800:raise TimeoutError("Finishing stage exceeded 30 minutes")
                time.sleep(.25)
        finally:
            if p.poll() is None:
                for child in reversed(list(children.values())):
                    try:child.terminate()
                    except psutil.Error:pass
                try:p.wait(5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
    stats={"seconds":time.monotonic()-start,"peak_process_tree_rss_bytes":peak}
    (job/(stage+"-runtime.json")).write_text(json.dumps(stats,indent=2))
    if p.returncode:raise RuntimeError(stage+" failed: "+log.read_text(errors="replace")[-5000:])
    return stats

def native_mesh(v,f,uv=None,normals=None,base=None,mr=None):
    import torch
    from comfy_api.latest import Types
    return Types.MESH(vertices=torch.as_tensor(v).float().unsqueeze(0),
                      faces=torch.as_tensor(f).long().unsqueeze(0),
                      uvs=None if uv is None else torch.as_tensor(uv).float().unsqueeze(0),
                      normals=None if normals is None else torch.as_tensor(normals).float().unsqueeze(0),
                      texture=base,metallic_roughness=mr)

def arrays(mesh):
    v=mesh.vertices.detach().cpu().numpy();f=mesh.faces.detach().cpu().numpy()
    if v.ndim==3:
        if len(v)!=1:raise ValueError("Finishing supports one asset per call")
        v=v[0];f=f[0]
    return v,f

class Hi3DFinishingSource:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"use_saved_checkpoint":("BOOLEAN",{"default":False}),
                            "saved_clean_mesh":("STRING",{"default":""}),
                            "saved_texture_mesh":("STRING",{"default":""})},
                "optional":{"mesh":("MESH",{"lazy":True}),"textured_source":("FILE_3D",{"lazy":True})}}
    RETURN_TYPES=("MESH","FILE_3D")
    RETURN_NAMES=("clean_geometry","approved_appearance")
    CATEGORY="Hi3D/Finishing";FUNCTION="select"
    def check_lazy_status(self,use_saved_checkpoint,saved_clean_mesh,saved_texture_mesh,mesh=None,textured_source=None):
        if use_saved_checkpoint:return []
        return [k for k,v in (("mesh",mesh),("textured_source",textured_source)) if v is None]
    def select(self,use_saved_checkpoint,saved_clean_mesh,saved_texture_mesh,mesh=None,textured_source=None):
        if not use_saved_checkpoint:
            if mesh is None or textured_source is None:raise ValueError("Connect clean geometry and its textured master")
            return mesh,textured_source
        import trimesh
        from comfy_api.latest import Types
        if not Path(saved_clean_mesh).is_file() or not Path(saved_texture_mesh).is_file():raise ValueError("Saved finishing checkpoint is missing")
        m=trimesh.load(saved_clean_mesh,force="mesh",process=False)
        return native_mesh(m.vertices,m.faces),Types.File3D(saved_texture_mesh)
    @classmethod
    def IS_CHANGED(cls,use_saved_checkpoint,saved_clean_mesh,saved_texture_mesh,**kwargs):
        return [(str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in map(Path,(saved_clean_mesh,saved_texture_mesh))] if use_saved_checkpoint else False

class Hi3DQuadFinish:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"mesh":("MESH",),"textured_source":("FILE_3D",),
            "enabled":("BOOLEAN",{"default":True}),
            "target_quads":("INT",{"default":25000,"min":1000,"max":200000,"step":1000}),
            "texture_size":("INT",{"default":4096,"min":512,"max":4096,"step":512}),
            "method":(["quadriflow","qremeshify","instant_meshes"],),
            "guide_triangles":("INT",{"default":100000,"min":10000,"max":200000,"step":10000}),
            "cage_distance":("FLOAT",{"default":.01,"min":.001,"max":.05,"step":.001}),
            "run_name":("STRING",{"default":"editable-25k"}),
            "reuse_geometry":("BOOLEAN",{"default":True})},
            "optional":{"after":("STRING",)}}
    RETURN_TYPES=("FILE_3D","STRING","STRING")
    RETURN_NAMES=("baked_runtime_glb","export_manifest","report")
    CATEGORY="Hi3D/Finishing";FUNCTION="finish";OUTPUT_NODE=True
    def finish(self,mesh,textured_source,enabled,target_quads,texture_size,method,guide_triangles,cage_distance,run_name,reuse_geometry,after=None):
        if not enabled:return {"ui":{"text":["Optional quads disabled; original appearance retained"]},"result":(textured_source,"","disabled")}
        import numpy as np,torch
        from PIL import Image
        import folder_paths,comfy.model_management as mm
        from comfy_api.latest import Types
        from comfy_extras.nodes_mesh_postprocess import BakeNormalMapFromMesh,ApplyTextureToMesh
        from comfy_extras.nodes_save_3d import MeshToFile3D
        name=safe_name(run_name);ident=uuid.uuid4().hex
        job=work_root()/"quad-jobs"/ident;job.mkdir(parents=True)
        dest=Path(folder_paths.get_output_directory())/"3d"/"Finishing"/(name+"-"+ident[:8]);dest.mkdir(parents=True)
        from .owned_scratch import register
        register(job,["master.npz","source-texture.glb","guide.obj","projection-source.npz","quadriflow-guide.npz",
                      "quadriflow-result.npz","remeshed-main.obj","remeshed-repair-input.obj","remeshed-repaired.obj",
                      "bake-arrays.npz","native-arrays.npz","baked-base-color.png","baked-metallic-roughness.png","baked-normal-opengl.png"],
                 "Quad finishing intermediates; outputs, logs and reusable quad geometry retained")
        v,f=arrays(mesh)
        original_hash=hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest()
        np.savez(job/"master.npz",vertices=v,faces=f)
        source=textured_source.get_source()
        if not isinstance(source,str):
            source=str(job/"source-texture.glb");textured_source.save_to(source)
        req={"job":str(job),"export_dir":str(dest),"target_quads":target_quads,"texture_size":texture_size,
             "method":method,"guide_triangles":guide_triangles,"cage_distance":cage_distance,"texture_source":source,"reuse_geometry":reuse_geometry,
             "input_geometry_sha256":original_hash,"input_texture_sha256":digest(source)}
        (job/"request.json").write_text(json.dumps(req,indent=2))
        key=hashlib.sha256(json.dumps([original_hash,target_quads,guide_triangles,method,digest(HERE/"quad_worker.py"),digest(HERE/"quad_contract.py"),digest(HERE/"quad_blender.py"),"geometry-v2"]).encode()).hexdigest()
        cache=work_root()/"quad-jobs"/("geometry-"+key+".json")
        reused=False;timings={}
        mm.unload_all_models();mm.soft_empty_cache()
        if reuse_geometry and cache.is_file():
            old=Path(json.loads(cache.read_text())["job"])
            if (old/"geometry-report.json").is_file() and (old/"quad-raw.obj").is_file():
                for file in ("geometry-report.json","quad-raw.obj"):shutil.copy2(old/file,job/file)
                reused=True
        if not reused:
            timings["geometry"]=run(req,"geometry",mm.throw_exception_if_processing_interrupted)
            cache.write_text(json.dumps({"job":str(job),"key":key}))
        timings["appearance"]=run(req,"appearance",mm.throw_exception_if_processing_interrupted)
        def image(name):
            return torch.from_numpy(np.asarray(Image.open(job/name).convert("RGB")).copy().astype(np.float32)/255).unsqueeze(0)
        base=image("baked-base-color.png");mr=image("baked-metallic-roughness.png")
        # Close the archive before owned scratch cleanup (Windows retains its lock).
        with np.load(job/"native-arrays.npz",allow_pickle=False) as baked_arrays:
            low=native_mesh(baked_arrays["vertices"],baked_arrays["faces"],baked_arrays["uvs"],baked_arrays["normals"],base,mr)
        start=time.monotonic()
        normal=BakeNormalMapFromMesh.execute(low,mesh,texture_size,cage_distance,True)[0]
        baked=ApplyTextureToMesh.execute(low,base,normal_map=normal)[0]
        MeshToFile3D.execute(baked)[0].save_to(str(dest/"runtime.glb"))
        Image.fromarray((normal[0].cpu().numpy().clip(0,1)*255).round().astype("uint8")).save(job/"baked-normal-opengl.png")
        timings["normal_bake_seconds"]=time.monotonic()-start
        del low,baked,normal
        mm.soft_empty_cache()
        timings["exports"]=run(req,"exports",mm.throw_exception_if_processing_interrupted)
        for file in ("baked-base-color.png","baked-metallic-roughness.png","baked-normal-opengl.png"):
            shutil.copy2(job/file,dest/file)
        mr_image=np.asarray(Image.open(job/"baked-metallic-roughness.png").convert("RGB"))
        Image.fromarray(mr_image[:,:,1]).save(dest/"roughness.png");Image.fromarray(mr_image[:,:,2]).save(dest/"metallic.png")
        dx=np.asarray(Image.open(job/"baked-normal-opengl.png").convert("RGB")).copy();dx[:,:,1]=255-dx[:,:,1]
        Image.fromarray(dx).save(dest/"normal-directx.png")
        report={"schema":"mumblebox.quad-finishing/1","settings":req,
                "geometry":json.loads((job/"geometry-report.json").read_text()),
                "uv":json.loads((job/"uv-report.json").read_text()),
                "exports":json.loads((job/"export-report.json").read_text()),
                "geometry_reused":reused,"timings":timings,
                "normal_map":"OpenGL +Y in GLB; DirectX companion explicitly separate",
                "animation_ready":False,"unreal_import_tested":False}
        report["source_unchanged"]=original_hash==hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest() and req["input_texture_sha256"]==digest(source)
        if not report["source_unchanged"]:raise RuntimeError("Master unexpectedly changed")
        report["files"]={p.relative_to(dest).as_posix():{"sha256":digest(p),"size":p.stat().st_size} for p in dest.rglob("*") if p.is_file()}
        manifest=dest/"manifest.json";manifest.write_text(json.dumps(report,indent=2))
        from .owned_scratch import cleanup
        scratch=cleanup(job)
        text=json.dumps({"cleanup":scratch,"quads":report["geometry"]["quads"],"triangles_runtime":report["geometry"]["runtime_triangles"],"watertight":report["geometry"]["watertight"],"warnings":report["geometry"].get("warnings",[]),"export_dir":str(dest)})
        return {"ui":{"text":[text]},"result":(Types.File3D(str(dest/"runtime.glb")),str(manifest),text)}

class Hi3DExportBundle:
    """One selection contract drives lazy inputs, the catalog, README and ZIP."""
    INPUTS={"detailed":"detailed","game_balanced":"balanced","game_compact":"compact",
            "print":"print_stl","quad_light":"quad_light","quad_detail":"quad_detail"}
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"use_saved_variants":("BOOLEAN",{"default":False}),
                "saved_balanced":("STRING",{"default":""}),"saved_compact":("STRING",{"default":""}),
                "saved_print":("STRING",{"default":""}),"run_name":("STRING",{"default":"asset-all-exports"})},
                "optional":{"detailed":("FILE_3D",{"lazy":True}),"balanced":("FILE_3D",{"lazy":True}),
                    "compact":("FILE_3D",{"lazy":True}),"print_stl":("FILE_3D",{"lazy":True}),
                    "quad_light":("STRING",{"default":"","lazy":True}),"quad_detail":("STRING",{"default":"","lazy":True}),
                    "asset_name":("STRING",{"default":"Asset"}),
                    "selection_json":("STRING",{"default":"","multiline":True,"tooltip":"Blank includes available outputs. Explicit schema: mumblebox.export-selection/1."}),
                    "grounding_json":("STRING",{"default":""}),
                    "metadata_json":("STRING",{"default":"","multiline":True,"tooltip":"Optional hash-bound production receipts; old asset statistics are never applied to a different file."})},
                "hidden":{"prompt":"PROMPT","unique_id":"UNIQUE_ID"}}
    RETURN_TYPES=("STRING","STRING");RETURN_NAMES=("zip_path","report")
    CATEGORY="Hi3D/Finishing";FUNCTION="export";OUTPUT_NODE=True
    @classmethod
    def selection(cls,use_saved_variants,selection_json="",prompt=None,unique_id=None,**kw):
        from .package_catalog import VARIANTS,parse_selection
        linked=(prompt or {}).get(str(unique_id),{}).get("inputs",{})
        available={}
        for variant,input_name in cls.INPUTS.items():
            if use_saved_variants and variant in ("game_balanced","game_compact","print"):
                present=bool(kw.get({"game_balanced":"saved_balanced","game_compact":"saved_compact","print":"saved_print"}[variant]))
            elif kw.get(input_name) is not None:present=kw[input_name]!=""
            else:present=isinstance(linked.get(input_name),list)
            if present:available[variant]=set(VARIANTS[variant][1])
        return parse_selection(selection_json,available)
    def check_lazy_status(self,use_saved_variants,selection_json="",prompt=None,unique_id=None,**kw):
        selected=self.selection(use_saved_variants,selection_json,prompt,unique_id,**kw)
        return [self.INPUTS[v] for v in selected.variants
                if not (use_saved_variants and v in ("game_balanced","game_compact","print"))
                and kw.get(self.INPUTS[v]) is None]
    def export(self,use_saved_variants,saved_balanced,saved_compact,saved_print,run_name,
               detailed=None,balanced=None,compact=None,print_stl=None,quad_light="",quad_detail="",
               asset_name="Asset",selection_json="",metadata_json="",grounding_json="",prompt=None,unique_id=None):
        import folder_paths
        import comfy.model_management as mm
        from comfy_api.latest import Types
        from .package_catalog import SourceArtifact,safe_relative
        from .package_archive import build_archive
        from dataclasses import asdict
        args=dict(detailed=detailed,balanced=balanced,compact=compact,print_stl=print_stl,
                  quad_light=quad_light,quad_detail=quad_detail,saved_balanced=saved_balanced,
                  saved_compact=saved_compact,saved_print=saved_print)
        selected=self.selection(use_saved_variants,selection_json,prompt,unique_id,**args)
        metadata=json.loads(metadata_json) if metadata_json.strip() else {}
        if not isinstance(metadata,dict):raise ValueError("Package metadata must be a JSON object")
        if grounding_json.strip():
            from .grounding import validate_frame
            frame=json.loads(grounding_json);validate_frame(frame)
            metadata['grounding']=frame;metadata.setdefault('production',{})['grounding']=frame
            if frame.get('warning'):metadata.setdefault('warnings',[]).append(frame['warning'])
        metadata.update(asset_name=asset_name,run_name=safe_name(run_name),_job_root=str(work_root()/"package-jobs"))
        sources={};staging=None
        for variant in selected.variants:
            input_name=self.INPUTS[variant]
            if variant.startswith("quad_"):
                m=Path(args[input_name])
                if not m.is_file():raise ValueError("Selected quad manifest is missing")
                report=json.loads(m.read_text(encoding="utf-8"))
                if not report.get("source_unchanged") or not report.get("exports",{}).get("roundtrip"):
                    raise ValueError("Selected quad output has no successful verification receipt")
                files={"blend":m.parent/"editable-quads.blend","runtime_glb":m.parent/"runtime.glb"}
                for path in files.values():
                    rel=safe_relative(path.relative_to(m.parent).as_posix())
                    expected=report.get("files",{}).get(rel,{})
                    if not path.is_file() or digest(path)!=expected.get("sha256"):raise ValueError("Quad artifact checksum differs from its manifest")
                g=report.get("geometry",{})
                topology={k:g[k] for k in ("boundary_edges","nonmanifold_edges","watertight","winding_consistent","components","degenerate_triangles") if k in g}
                receipts=({"variant_id":variant,"sha256":digest(files["blend"]),"topology":topology,
                    "validation":[{"name":"Source quad export checks","status":"pass","note":"Matching authoring-file digest and original roundtrip receipt"}],
                    "resources":["quadriflow"] if any(str(x.get("method","")).startswith("QuadriFlow") for x in g.get("methods",[])) else [],"provenance_scope":"finishing_only"},)
                sources[variant]=SourceArtifact(variant,files,receipts)
            else:
                value=args[input_name]
                if use_saved_variants and variant in ("game_balanced","game_compact","print"):
                    path=args[{"game_balanced":"saved_balanced","game_compact":"saved_compact","print":"saved_print"}[variant]]
                    if not Path(path).is_file():raise ValueError("Selected saved output is missing: "+variant)
                    value=Types.File3D(path)
                if value is None:raise ValueError("Selected output was not evaluated: "+variant)
                source=value.get_source()
                if not isinstance(source,str):
                    if staging is None:
                        staging=work_root()/"package-jobs"/("inputs-"+uuid.uuid4().hex);staging.mkdir(parents=True)
                    source=str(staging/(variant+(".stl" if variant=="print" else ".glb")));value.save_to(source)
                if not Path(source).is_file():raise ValueError("Selected source file is missing")
                sources[variant]=SourceArtifact(variant,{"stl" if variant=="print" else "glb":source})
        identity=json.loads((HERE/"package_identity.json").read_text(encoding="utf-8"))
        mm.unload_all_models();mm.soft_empty_cache()
        result=build_archive(sources,selected,identity,metadata,Path(folder_paths.get_output_directory())/"3d"/"Finishing",
                             run,mm.throw_exception_if_processing_interrupted)
        summary=asdict(result)
        if metadata.get('grounding'):
            from .grounding import ground_glb,validate_frame
            frame=metadata['grounding'];summary['grounding']=frame;summary['grounded_previews']={}
            if frame['mode']=='original':
                views={'detailed':'texture','game_balanced':'balanced','game_compact':'compact','quad_light':'quads','print':'print'}
                for key,artifact in sources.items():summary['grounded_previews'][views[key]]=str(artifact.files.get('glb') or artifact.files.get('runtime_glb') or artifact.files['stl'])
            else:
                root=Path(result.archive_path).with_suffix('')
                preview_root=Path(folder_paths.get_output_directory())/'foundry'/'grounded-previews'/result.export_id
                paths={'detailed':('Detailed/mesh.glb','texture'),'game_balanced':('Game/Balanced/mesh.glb','balanced'),'game_compact':('Game/Compact/mesh.glb','compact'),'quad_light':('Editable_Quads/Light/runtime.glb','quads'),'print':('Print/mesh.stl','print')}
                for key,artifact in sources.items():
                    relative,view=paths[key];path=root/relative
                    if not path.is_file() and key!='print':
                        preview_root.mkdir(parents=True,exist_ok=True);path=preview_root/(key+'.glb')
                        ground_glb(artifact.files.get('glb') or artifact.files['runtime_glb'],path,validate_frame(frame),floor=True)
                    if path.is_file():summary['grounded_previews'][view]=str(path)
        try:
            from .history_receipt import publish
            publish(result.archive_path, result.export_id, folder_paths.get_user_directory())
        except Exception:
            # History indexing must never invalidate a completed, verified asset package.
            summary.setdefault("warnings", []).append("The package was saved, but its history notification could not be written.")
        from .owned_scratch import cleanup,register
        try:
            summary["scratch_cleanup"]=cleanup(work_root()/"package-jobs"/result.export_id)
            if staging is not None:
                register(staging,[p.name for p in staging.iterdir() if p.is_file()],"Serialized package inputs; published exports retained")
                summary["input_cleanup"]=cleanup(staging)
        except (OSError,ValueError) as error:
            summary["scratch_cleanup"]={"status":"failed","error":str(error)}
            summary.setdefault("warnings",[]).append("Package saved; disposable verification files could not all be removed.")
        return {"ui":{"text":[result.archive_path,json.dumps(summary)]},"result":(result.archive_path,json.dumps(summary))}

NODE_CLASS_MAPPINGS={c.__name__:c for c in (Hi3DFinishingSource,Hi3DQuadFinish,Hi3DExportBundle)}
NODE_DISPLAY_NAME_MAPPINGS={"Hi3DFinishingSource":"Finishing input — live or preserved checkpoint",
    "Hi3DQuadFinish":"Optional quads → final UVs → detail bake → authoring exports",
    "Hi3DExportBundle":"Asset package - selected exports + README + ZIP"}
