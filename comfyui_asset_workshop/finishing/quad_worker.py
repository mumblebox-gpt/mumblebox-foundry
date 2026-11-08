"""Isolated geometry/appearance worker; calls upstream remeshers and existing MeshLab bake."""
import json,sys,time,subprocess,os,psutil,hashlib,shutil
from pathlib import Path
import numpy as np
import trimesh
from quad_contract import read_obj,write_obj,triangles_to_quads,normalize_quad_diagonals
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parent/"pipeline_workers"))
from mesh_optimize_worker import simplify_mesh,rebake_maps,comfy_uvs

def bounded_process(command,timeout,**kwargs):
    """Terminate only this worker's owned process tree on timeout or failure."""
    with subprocess.Popen(command,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0,**kwargs) as proc:
        descendants={}
        started=time.monotonic()
        while proc.poll() is None:
            try:
                for child in psutil.Process(proc.pid).children(recursive=True):descendants[child.pid]=child
            except psutil.Error:pass
            if time.monotonic()-started>timeout:
                for child in reversed(list(descendants.values())):
                    try:child.kill()
                    except psutil.Error:pass
                proc.kill();proc.wait()
                raise subprocess.TimeoutExpired(command,timeout)
            time.sleep(.2)
        if proc.returncode:
            for child in reversed(list(descendants.values())):
                try:
                    if child.is_running():child.kill()
                except psutil.Error:pass
            raise subprocess.CalledProcessError(proc.returncode,command)

def blender(req,stage,timeout=600):
    log=Path(req["job"])/(stage+".log")
    with log.open("w",encoding="utf8") as out:
        bounded_process([req["blender"],"--background","--factory-startup","--python-exit-code","1",
                        "--python",str(HERE/("package_blender.py" if stage in ("package","package_verify") else "quad_blender.py")),"--",str(Path(req["job"])/"request.json"),stage],
                       stdout=out,stderr=subprocess.STDOUT,timeout=timeout)

def triangle_faces(polys):
    return np.asarray([[f[0],f[i],f[i+1]] for f in polys for i in range(1,len(f)-1)],dtype=np.int64)

def stats(v,f):
    mesh=trimesh.Trimesh(v,triangle_faces(f),process=False)
    counts=np.bincount(mesh.edges_unique_inverse)
    return {"vertices":len(v),"polygons":len(f),"quads":sum(len(p)==4 for p in f),
            "triangles":sum(len(p)==3 for p in f),"ngons":sum(len(p)>4 for p in f),
            "runtime_triangles":len(mesh.faces),"boundary_edges":int((counts==1).sum()),
            "nonmanifold_edges":int((counts>2).sum()),"degenerate_triangles":int((mesh.area_faces<1e-18).sum()),
            "watertight":bool(mesh.is_watertight),"winding_consistent":bool(mesh.is_winding_consistent),
            "components":len(trimesh.graph.connected_components(mesh.face_adjacency,nodes=np.arange(len(mesh.faces))))}

def topology_preserving_quads(part,budget):
    """QEM retains topology; planar subdivision creates quads without hole caps.

    This is an explicitly reported fallback, not a QuadriFlow result. It is
    permitted only for an already closed component and retains the same budget.
    """
    if not part.is_watertight or not part.is_winding_consistent:
        raise ValueError('Topology-preserving quads require a closed, consistently wound source component')
    reduced=simplify_mesh(part,max(8,budget//3))
    if not reduced.is_watertight or not reduced.is_winding_consistent:
        raise ValueError('Topology-preserving reduction could not retain the closed component')
    v,f=triangles_to_quads(reduced.vertices,reduced.faces)
    if len(f)>budget*1.25:raise ValueError('The closed quad fallback needs a higher quad budget for this component')
    return v,f


def small_holes_only(vertices,faces,extents):
    if not len(vertices) or not len(faces):return False
    check=stats(vertices,faces)
    if check['nonmanifold_edges'] or check['boundary_edges']>max(100,len(faces)*.02):return False
    es=np.asarray([[p[i],p[(i+1)%len(p)]] for p in faces for i in range(len(p))])
    es,ct=np.unique(np.sort(es,axis=1),axis=0,return_counts=True);boundary=es[ct==1]
    for ring in trimesh.graph.connected_components(boundary,nodes=np.unique(boundary)):
        if len(ring)>16 or np.linalg.norm(np.ptp(np.asarray(vertices)[ring],axis=0))>np.linalg.norm(extents)*.03:return False
    return True


def geometry(req):
    start=time.monotonic(); job=Path(req["job"])
    a=np.load(job/"master.npz")
    source=trimesh.Trimesh(a["vertices"],a["faces"],process=False)
    parts=sorted(source.split(only_watertight=False),key=lambda p:-p.area)
    small=[p for p in parts if len(p.faces)<200]
    major=[p for p in parts if len(p.faces)>=200]
    tiny_budget=sum(len(p.faces)*3 for p in small)
    remaining=req["target_quads"]-tiny_budget
    from quad_contract import allocate_budget
    budgets=allocate_budget([p.area for p in major],remaining,minimum=24)
    vertices=[];polys=[]; details=[];closed_fallback=False
    for index,(part,budget) in enumerate(zip(major,budgets)):
        guide=simplify_mesh(part,min(len(part.faces),req["guide_triangles"]))
        guide.export(job/"guide.obj",include_normals=False)
        np.savez(job/"projection-source.npz",vertices=part.vertices,faces=part.faces)
        subreq=dict(req,component=index,component_target=budget,initial_scale=(len(guide.faces)/(budget*2))**.5)
        (job/"request.json").write_text(json.dumps(subreq,indent=2))
        method="topology_preserving" if closed_fallback else req["method"]; reason=None
        if method=="qremeshify":
            try:
                blender(subreq,"remesh",600)
                v,f=read_obj(job/"remeshed-main.obj")
                qreport=json.loads((job/"remesh-result.json").read_text()); details.append(qreport)
                gate=stats(v,f)
                if not gate["watertight"] or gate["nonmanifold_edges"] or gate["degenerate_triangles"] or abs(len(f)-budget)/budget>.25:
                    qreport["accepted"]=False; qreport["rejection"]=gate
                    raise ValueError("QRemeshify failed topology or 25% budget tolerance: "+json.dumps(gate))
            except (subprocess.SubprocessError,ValueError,OSError) as exc:
                reason=str(exc)
                print("QREMESHIFY failed; using researched Instant Meshes fallback: "+reason,flush=True)
                method="instant_meshes"
        if method=="instant_meshes":
            import pynanoinstantmeshes as instant
            v,f=instant.remesh(np.array(guide.vertices,dtype=np.float32),
                np.array(guide.faces,dtype=np.uint32),-1,rosy=4,posy=4,face_count=max(100,budget//4),
                creaseAngle=0.0,align_to_boundaries=True,extrinsic=True,smooth_iter=2,deterministic=True)
            v=v.tolist();f=f.tolist()
            ireport={"method":method,"target":budget,"initial_field_faces":max(100,budget//4),"crease_angle":0,"actual":len(f),"fallback_reason":reason};details.append(ireport)
            gate=stats(v,f)
            if not gate["watertight"] or gate["nonmanifold_edges"] or gate["degenerate_triangles"]:
                ireport["accepted"]=False;ireport["rejection"]=gate
                print("Instant Meshes rejected by topology gate; testing bounded QuadriFlow fallback",flush=True)
                method="quadriflow"
        if method=="quadriflow":
            np.savez(job/"quadriflow-guide.npz",vertices=guide.vertices,faces=guide.faces)
            program="import sys,numpy as np;from pyquadriflow.quadriflow import quadriflow_remesh;a=np.load(sys.argv[1]);v,f=quadriflow_remesh(np.array(a['vertices'],dtype=np.float64),np.array(a['faces'],dtype=np.int32),int(sys.argv[3]),seed=42,preserve_sharp=True,preserve_boundary=True);np.savez(sys.argv[2],vertices=v,faces=f)"
            begin=time.monotonic()
            signature=hashlib.sha256(guide.vertices.tobytes()+guide.faces.tobytes()+str((budget,42,True,True)).encode()).hexdigest()
            qcache=job.parent/("quadriflow-"+signature+".npz")
            cache_hit=req.get("reuse_geometry",True) and qcache.is_file()
            if cache_hit:
                shutil.copy2(qcache,job/"quadriflow-result.npz")
                print("Reusing exact QuadriFlow guide/settings checkpoint "+signature,flush=True)
            else:
                bounded_process([sys.executable,"-u","-c",program,str(job/"quadriflow-guide.npz"),str(job/"quadriflow-result.npz"),str(budget)],timeout=1200)
                shutil.copy2(job/"quadriflow-result.npz",qcache)
            qr=np.load(job/"quadriflow-result.npz");v=qr["vertices"].tolist();f=qr["faces"].tolist()
            f,_=normalize_quad_diagonals(f)
            details.append({"method":"QuadriFlow 0.2.0","seed":42,"target":budget,"actual":len(f),"preserve_sharp":True,"preserve_boundary":True,"raw_checkpoint_reused":cache_hit,"seconds":time.monotonic()-begin})
        if method=='quadriflow' and part.is_watertight and not small_holes_only(v,f,part.extents):
            details.append({'method':'QuadriFlow rejected','component':index,'rejection':stats(v,f),
                'reason':'Boundary defects exceed the unchanged small-hole guard'})
            method='topology_preserving';closed_fallback=True
        if method=='topology_preserving':
            v,f=topology_preserving_quads(part,budget)
            details.append({'method':'Topology-preserving quad subdivision','component':index,'target':budget,'actual':len(f),
                'reason':'QuadriFlow damaged a closed component; QEM preserves topology before exact planar quad subdivision'})
        v=np.array(v,dtype=np.float64)
        distances=[]; nearest=[]
        for first in range(0,len(v),1024):
            p,d,_=trimesh.proximity.closest_point(part,v[first:first+1024])
            nearest.append(p);distances.append(d)
        nearest=np.concatenate(nearest); distances=np.concatenate(distances)
        limit=np.linalg.norm(part.extents)*.02
        if (distances>limit).any(): raise ValueError("Retopology moved beyond the 2% component projection guard")
        # Keep planar, closed fallback polygons intact. Their distance to the
        # master was just checked by the same 2% guard; projection can collapse
        # vertices near a narrow feature and damage this guaranteed topology.
        if method!='topology_preserving':v=nearest
        # Normalize before measuring defects; a fixed diagonal is not a surface edge.
        f,rotations=normalize_quad_diagonals(f)
        if rotations:details.append({"method":"polygon-start rotation before repair gate","rotated_quads":rotations})
        check=stats(v,f)
        if check["boundary_edges"] or check["degenerate_triangles"]:
            if check["nonmanifold_edges"] or check["boundary_edges"]>max(100,len(f)*.02):
                raise ValueError("Remesh defects exceed the component-local repair gate: "+json.dumps(check))
            es=np.array([[p[i],p[(i+1)%len(p)]] for p in f for i in range(len(p))])
            es,ct=np.unique(np.sort(es,axis=1),axis=0,return_counts=True)
            for ring in trimesh.graph.connected_components(es[ct==1]):
                if len(ring)>16 or np.linalg.norm(np.ptp(v[ring],axis=0))>np.linalg.norm(part.extents)*.03:
                    raise ValueError("Boundary exceeds the 16-edge/3%-diagonal small-hole limit")
            write_obj(job/"remeshed-repair-input.obj",v.tolist(),f)
            blender(req,"repair",120)
            v,f=read_obj(job/"remeshed-repaired.obj");v=np.array(v,dtype=np.float64)
            details.append({"method":"Blender component-local cleanup","repair":json.loads((job/"remesh-repair.json").read_text())})
            # A legal quad surface can still have a diagonal matching another polygon edge.
            # Rotate only the polygon start index to keep fixed bake/runtime triangulation manifold.
            f,rotations=normalize_quad_diagonals(f)
            if rotations:details.append({"method":"polygon-start rotation for manifold fixed triangulation","rotated_quads":rotations})
            check=stats(v,f)
        if not check["watertight"] or check["nonmanifold_edges"] or check["degenerate_triangles"] or not check["winding_consistent"]:
            raise ValueError("Remesher output failed geometry gate: "+json.dumps(check))
        offset=len(vertices);vertices.extend(v.tolist());polys.extend([[int(i)+offset for i in p] for p in f])
    for part in small:
        v,f=triangles_to_quads(part.vertices,part.faces)
        offset=len(vertices);vertices.extend(v);polys.extend([[i+offset for i in p] for p in f])
    write_obj(job/"quad-raw.obj",vertices,polys)
    report=stats(vertices,polys)
    report['warnings']=['Topology-preserving quad subdivision was used where QuadriFlow returned openings. This is an editable starting mesh; review its edge flow before rigging.'] if closed_fallback else []
    report.update({"target_quads":req["target_quads"],"component_policy":"remesh major components independently; exact quad subdivision for components under 200 triangles",
        "preserved_small_components":len(small),"source_components":len(parts),"methods":details,
        "source_vertices":len(source.vertices),"source_triangles":len(source.faces),"seconds":time.monotonic()-start})
    low=trimesh.Trimesh(vertices,triangle_faces(polys),process=False)
    errors=[]
    for src,dst in ((source,low),(low,source)):
        p,_=trimesh.sample.sample_surface(src,5000,seed=42)
        for first in range(0,len(p),512):errors.extend(trimesh.proximity.closest_point(dst,p[first:first+512])[1])
    errors=np.array(errors)/np.linalg.norm(source.extents)
    report["sampled_surface_error"]={"samples":10000,"seed":42,"mean":float(errors.mean()),"p95":float(np.percentile(errors,95)),"max":float(errors.max()),"unit":"fraction of master bbox diagonal"}
    (job/"geometry-report.json").write_text(json.dumps(report,indent=2))
    (job/"request.json").write_text(json.dumps(req,indent=2))
    print("GEOMETRY "+json.dumps(report),flush=True)

def appearance(req):
    job=Path(req["job"])
    blender(req,"uv",600)
    source=trimesh.load(req["texture_source"],force="mesh",process=False)
    a=np.load(job/"bake-arrays.npz")
    low=trimesh.Trimesh(a["vertices"],a["faces"],process=False,
                       visual=trimesh.visual.TextureVisuals(uv=a["uvs"]))
    rebake_maps(source,low,job,req["texture_size"])
    np.savez(job/"native-arrays.npz",vertices=a["vertices"],faces=a["faces"],normals=a["normals"],uvs=comfy_uvs(a["uvs"]))
    print("COLOR/MATERIAL TRANSFER COMPLETE",flush=True)

if __name__=="__main__":
    req=json.loads(Path(sys.argv[1]).read_text())
    if sys.argv[2]=="geometry":geometry(req)
    elif sys.argv[2]=="appearance":appearance(req)
    elif sys.argv[2]=="exports":blender(req,"exports",600)
    elif sys.argv[2]=="legacy":blender(req,"legacy",600)
    elif sys.argv[2] in ("package","package_verify"):
        blender(req,sys.argv[2],600)
        if sys.argv[2]=="package":
            from package_companions import add_companions
            add_companions(req)
