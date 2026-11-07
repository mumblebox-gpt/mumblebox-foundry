"""Read-only exported-geometry gate, executed in the configured finishing worker."""
import json
import sys
from pathlib import Path

def measure(path):
    import hashlib
    import numpy as np
    import trimesh,pymeshlab
    m=trimesh.load(path,force='mesh',process=False,skip_materials=True)
    edges=np.bincount(m.edges_unique_inverse)
    ms=pymeshlab.MeshSet();ms.add_mesh(pymeshlab.Mesh(vertex_matrix=np.asarray(m.vertices),face_matrix=np.asarray(m.faces,dtype=np.int32)))
    ms.compute_selection_by_self_intersections_per_face();crossings=int(ms.current_mesh().face_selection_array().sum())
    ms.compute_selection_by_non_manifold_per_vertex();nonmanifold=int(ms.current_mesh().vertex_selection_array().sum())
    r=dict(vertices=len(m.vertices),triangles=len(m.faces),watertight=bool(m.is_watertight),winding_consistent=bool(m.is_winding_consistent),
        positive_volume=bool(m.volume>0),finite_vertices=bool(np.isfinite(m.vertices).all()),boundary_edges=int((edges==1).sum()),
        nonmanifold_edges=int((edges>2).sum()),nonmanifold_vertices=nonmanifold,zero_area_faces=int((m.area_faces==0).sum()),
        duplicate_faces=int(len(m.faces)-len(np.unique(np.sort(m.faces,axis=1),axis=0))),self_intersection_selected_faces=crossings,
        components=len(trimesh.graph.connected_components(m.face_adjacency,nodes=np.arange(len(m.faces)),min_len=1)),bounds=m.bounds.tolist())
    with Path(path).open('rb') as source:r['sha256']=hashlib.file_digest(source,'sha256').hexdigest()
    r['passed']=all(r[k] for k in ('watertight','winding_consistent','positive_volume','finite_vertices')) and all(r[k]==0 for k in ('boundary_edges','nonmanifold_edges','nonmanifold_vertices','zero_area_faces','duplicate_faces','self_intersection_selected_faces'))
    return r

def audit(service,record):
    from ....finishing.runtime import worker_python
    from ....pipeline_workers.trellis_bridge_runtime import run_worker
    directory=service.output_root/'foundry-splat'/record['id'];directory.mkdir(parents=True,exist_ok=True)
    request=directory/'quality-request.json';report=directory/'quality.json'
    request.write_text(json.dumps({k:str(service.artifact_path(record,k)) for k in ('master','companion')}),encoding='utf-8')
    run_worker([worker_python(),'-u',str(Path(__file__).resolve()),str(request),str(report)],directory/'quality.log',lambda:service.check(record))
    result=json.loads(report.read_text(encoding='utf-8'))
    record['quality']=result
    if not all(x['passed'] for x in result.values()):raise ValueError('The mesh quality check found a remaining geometry defect. Saved splat and meshes are preserved; review the audit before exporting.')
    return result

if __name__=='__main__':
    paths=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    result={k:measure(v) for k,v in paths.items()}
    Path(sys.argv[2]).write_text(json.dumps(result,indent=2),encoding='utf-8')
