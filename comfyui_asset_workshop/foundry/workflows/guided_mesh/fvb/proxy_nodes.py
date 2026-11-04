"""Automatic working-proxy processing, executed by the real Comfy graph."""
import copy
import json
import torch
from . import runtime
from .journal import atomic_json
from .proxy import upright_box_frame


class OrientProxy:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'mesh':('MESH',),'job_id':('STRING',{'default':''}),
            'policy':(['upright_solid_box'],)}}
    RETURN_TYPES=('MESH','STRING');FUNCTION='orient';CATEGORY='Foundry View Bridge/Proxy'

    def orient(self,mesh,job_id,policy):
        if policy!='upright_solid_box':raise ValueError('Unsupported proxy-processing policy.')
        if mesh.vertices.shape[0]!=1:raise ValueError('Process one working proxy.')
        count=int(mesh.vertex_counts[0]) if getattr(mesh,'vertex_counts',None) is not None else mesh.vertices.shape[1]
        vertices=mesh.vertices[0,:count].detach().cpu().numpy()
        matrix,report=upright_box_frame(vertices)
        result=copy.copy(mesh)
        T=torch.as_tensor(matrix,dtype=mesh.vertices.dtype,device=mesh.vertices.device)
        result.vertices=mesh.vertices@T[:3,:3].T+T[:3,3]
        for name in ('normals','tangents'):
            value=getattr(mesh,name,None)
            if value is not None:
                moved=torch.nn.functional.normalize(value[...,:3]@T[:3,:3].to(value).T,dim=-1)
                setattr(result,name,torch.cat([moved,value[...,3:]],-1) if value.shape[-1]>3 else moved)
        report['input_vertex_count']=count
        report['input_face_count']=int(mesh.face_counts[0]) if getattr(mesh,'face_counts',None) is not None else mesh.faces.shape[1]
        path,relative=runtime.target(job_id,'proxy:orientation','.json');atomic_json(path,report)
        return {'ui':{'fvb_artifacts':[{'proxy:orientation':runtime.record(path,relative,'json')}]},'result':(result,json.dumps(report))}


class FinalizeProxy:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'mesh':('MESH',),'job_id':('STRING',{'default':''}),'orientation_report':('STRING',{'multiline':True}),
            'resolution':('INT',{'default':512,'min':128,'max':512,'step':128}),
            'smooth_iterations':('INT',{'default':2,'min':0,'max':3})}}
    RETURN_TYPES=('MESH',);FUNCTION='finalize';CATEGORY='Foundry View Bridge/Proxy'

    def finalize(self,mesh,job_id,orientation_report,resolution,smooth_iterations):
        report=json.loads(orientation_report)
        result=copy.copy(mesh)
        count=int(result.vertex_counts[0]) if getattr(result,'vertex_counts',None) is not None else result.vertices.shape[1]
        floor=result.vertices[0,:count,1].min()
        result.vertices=result.vertices.clone();result.vertices[...,1]-=floor
        report.update(topology_backend='native RemeshMesh solid',resolution=resolution,fill=20.,band=1.,smooth_iterations=smooth_iterations,
            ground_y_translation=-float(floor),output_vertex_count=count,output_face_count=result.faces.shape[1],
            bounds=[result.vertices[0,:count].amin(0).tolist(),result.vertices[0,:count].amax(0).tolist()],
            working_mesh_used_by='G3D_SaveMesh(proxy) -> native preview and G3D_RenderProxy',
            geometry_quality='Topology/noise cleanup applied; semantic geometry fidelity must be inspected.')
        path,relative=runtime.target(job_id,'proxy:processing','.json');atomic_json(path,report)
        return {'ui':{'fvb_artifacts':[{'proxy:processing':runtime.record(path,relative,'json')}]},'result':(result,)}


PROXY_NODES={'G3D_OrientProxy':OrientProxy,'G3D_FinalizeProxy':FinalizeProxy}
