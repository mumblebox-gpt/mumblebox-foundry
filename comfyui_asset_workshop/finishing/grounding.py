"""Rigid, near-upright support poses and lossless-buffer GLB frame application."""
import json,struct
from pathlib import Path
import numpy as np

MODES=('level','place','original')

def validate_frame(frame):
    matrix=np.asarray(frame['matrix_y_up'],dtype=np.float64)
    if matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3],[0,0,0,1]):raise ValueError('Invalid grounding frame')
    rotation=matrix[:3,:3]
    if not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-6) or not np.isclose(np.linalg.det(rotation),1,atol=1e-6):raise ValueError('Grounding must be a proper rigid transform')
    if frame.get('mode') not in MODES:raise ValueError('Choose a supported grounding mode')
    return matrix

def plan_grounding(vertices,faces,mode='level',max_tilt=30):
    import trimesh
    v=np.asarray(vertices,dtype=np.float64);f=np.asarray(faces,dtype=np.int64)
    if mode not in MODES:raise ValueError('Choose a supported grounding mode')
    if v.ndim!=2 or v.shape[1]!=3 or len(v)<4 or not np.isfinite(v).all() or np.linalg.norm(np.ptp(v,axis=0))<1e-12:raise ValueError('Grounding needs a finite, nondegenerate mesh')
    if not 0<=max_tilt<=45:raise ValueError('Grounding tilt limit must be between 0 and 45 degrees')
    T=np.eye(4);angle=0.;applied=mode;warning='';candidates=0
    if mode=='level':
        mesh=trimesh.Trimesh(v,f,process=False)
        C=trimesh.transformations.rotation_matrix(np.pi/2,[1,0,0])
        hull=mesh.convex_hull;center=mesh.center_mass if mesh.is_watertight else hull.center_mass
        hull.apply_transform(C);center=trimesh.transform_points([center],C)[0]
        poses,prob=hull.compute_stable_poses(center_mass=center,sigma=0,n_samples=1,threshold=0)
        near=[]
        for pose,p in zip(poses,prob):
            degrees=float(np.degrees(np.arccos(np.clip(pose[2,2],-1,1))))
            if degrees<=max_tilt+1e-8:near.append((degrees,-float(p),np.linalg.inv(C)@pose@C))
        candidates=len(near)
        if near:
            angle,_,pose=min(near,key=lambda item:item[:2]);normal=pose[:3,:3].T@np.array([0.,1.,0.])
            axis=np.cross(normal,[0.,1.,0.]);theta=float(np.arccos(np.clip(normal[1],-1,1)))
            if np.linalg.norm(axis)>1e-10:T[:3,:3]=trimesh.transformations.rotation_matrix(theta,axis)[:3,:3]
        else:applied='place';warning='No stable support plane within the upright tilt limit; placed on the floor without leveling. Choose Keep original orientation if this object should float.'
    if mode!='original':
        points=v@T[:3,:3].T;lo=points.min(axis=0);hi=points.max(axis=0)
        T[:3,3]=[-(lo[0]+hi[0])/2,-lo[1],-(lo[2]+hi[2])/2]
    points=v@T[:3,:3].T+T[:3,3];tol=float(np.linalg.norm(np.ptp(points,axis=0))*.002)
    contacts=points[points[:,1]<=points[:,1].min()+tol]
    return {'schema':'mumblebox.grounding/1','mode':mode,'applied':applied,'matrix_y_up':T.tolist(),'correction_degrees':angle,
        'candidate_count':candidates,'floor_min':float(points[:,1].min()),'contact_tolerance':tol,'contact_vertices':len(contacts),
        'contact_span_xz':np.ptp(contacts,axis=0)[[0,2]].tolist(),'warning':warning,
        'method':'near-upright stable support pose; rigid rotation and floor placement; no vertex flattening'}

def blender_frame(matrix):
    C=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]],dtype=float)
    return C@np.asarray(matrix)@C.T

def ground_glb(source,target,matrix,floor=False):
    """Bake a frame into dense native mesh attributes; retain UVs, indices and image bytes.

    Foundry's saved native GLBs have identity scene-node transforms. Refuse
    unqualified instancing/TRS instead of applying an incorrect local frame.
    """
    if Path(source).resolve()==Path(target).resolve():raise ValueError('Keep the original GLB; grounding needs a new destination')
    raw=Path(source).read_bytes();magic,version,length=struct.unpack_from('<III',raw)
    if magic!=0x46546c67 or version!=2 or length!=len(raw):raise ValueError('Invalid GLB')
    chunks=[];offset=12
    while offset<len(raw):
        size,kind=struct.unpack_from('<II',raw,offset);offset+=8;chunks.append((kind,bytearray(raw[offset:offset+size])));offset+=size
    document=json.loads(bytes(next(data for kind,data in chunks if kind==0x4e4f534a)));binary=next(data for kind,data in chunks if kind==0x004e4942)
    for node in document.get('nodes',[]):
        if ('matrix' in node and not np.allclose(np.array(node['matrix']).reshape(4,4).T,np.eye(4))) or not np.allclose(node.get('translation',[0,0,0]),0) or not np.allclose(node.get('rotation',[0,0,0,1]),[0,0,0,1]) or not np.allclose(node.get('scale',[1,1,1]),1):raise ValueError('Grounding requires native GLB geometry with baked scene transforms')
    matrix=np.asarray(matrix,dtype=float);R=matrix[:3,:3];done=set();minimum=float('inf')
    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            for role in ('POSITION','NORMAL','TANGENT'):
                index=primitive.get('attributes',{}).get(role)
                if index is None or index in done:continue
                done.add(index);a=document['accessors'][index];view=document['bufferViews'][a['bufferView']];width=4 if a['type']=='VEC4' else 3
                if a['componentType']!=5126 or a.get('sparse') or view.get('buffer',0)!=0:raise ValueError('Unsupported native GLB attribute layout')
                values=np.ndarray((a['count'],width),dtype='<f4',buffer=binary,offset=view.get('byteOffset',0)+a.get('byteOffset',0),strides=(view.get('byteStride',width*4),4))
                out=values[:,:3].astype(float)@R.T
                if role=='POSITION':out+=matrix[:3,3];minimum=min(minimum,float(out[:,1].min()))
                else:out/=np.maximum(np.linalg.norm(out,axis=1,keepdims=True),1e-20)
                values[:,:3]=out
                if role=='POSITION':a['min']=values[:,:3].min(axis=0).tolist();a['max']=values[:,:3].max(axis=0).tolist()
    if floor:
        for index in {primitive['attributes']['POSITION'] for mesh in document['meshes'] for primitive in mesh['primitives']}:
            a=document['accessors'][index];view=document['bufferViews'][a['bufferView']]
            values=np.ndarray((a['count'],3),dtype='<f4',buffer=binary,offset=view.get('byteOffset',0)+a.get('byteOffset',0),strides=(view.get('byteStride',12),4))
            values[:,1]-=minimum;a['min']=values.min(axis=0).tolist();a['max']=values.max(axis=0).tolist()
    payload=json.dumps(document,separators=(',',':')).encode();payload+=b' '*((-len(payload))%4)
    result=b''.join(struct.pack('<II',len(payload if kind==0x4e4f534a else data),kind)+(payload if kind==0x4e4f534a else bytes(data)) for kind,data in chunks)
    Path(target).write_bytes(struct.pack('<III',magic,2,len(result)+12)+result)
    return minimum
