/** Use the mounted GLB's actual skin and sample vertices in source units. */
const COMPONENTS=["getX","getY","getZ","getW"];
const MAX_SAMPLES=16384;
const WEIGHT_TOLERANCE=1e-4;

export function applyLocalPose(root, pose){
    if(!pose)return ()=>{};
    let bone=null;
    root.traverse(item=>{if(item.isBone&&item.name===pose.bone_id)bone=item;});
    if(!bone)throw Error("The bound mesh does not contain the selected bone.");
    const previous=bone.quaternion.clone();
    const axis=bone.position.clone().set(0,0,0);
    axis[pose.axis]=1;
    bone.rotateOnAxis(axis,pose.angle);
    root.updateWorldMatrix(true,true);
    return ()=>{
        bone.quaternion.copy(previous);
        root.updateWorldMatrix(true,true);
    };
}

export function measureMovement(root, transform, selection, pose, threshold){
    const meshes=[];
    let total=0;
    root.traverse(mesh=>{
        if(!mesh.isSkinnedMesh)return;
        const {position,skinIndex,skinWeight}=mesh.geometry.attributes;
        if(!position||!skinIndex||!skinWeight)return;
        total+=position.count;
        meshes.push({mesh,position,skinIndex,skinWeight,transform:transform.clone().multiply(mesh.matrixWorld)});
    });
    if(!total)throw Error("Open the current skinned mesh in Review.");
    const stride=Math.max(1,Math.ceil(total/MAX_SAMPLES));
    const target={samples:0,moved:0,max:0},neighbors={samples:0,moved:0,max:0};
    const neighborIds=new Set(selection.neighbor_ids);
    const samples=[];
    const point=root.position.clone();
    let offset=0,sampled=0,unweighted=0,invalid_weights=0,not_normalized=0,max_influences=0;
    for(const entry of meshes){
        const {mesh,position,skinIndex,skinWeight}=entry;
        for(let index=(stride-offset%stride)%stride;index<position.count;index+=stride){
            sampled++;
            let strongest=-1,best=0,influences=0,sum=0,valid=true;
            for(const component of COMPONENTS){
                const weight=skinWeight[component](index);
                const joint=skinIndex[component](index);
                if(!Number.isFinite(weight)||weight<0||(weight>0&&!mesh.skeleton.bones[joint])){
                    valid=false;
                    break;
                }
                sum+=weight;
                if(weight>0)influences++;
                if(weight>best){best=weight;strongest=joint;}
            }
            if(!valid){invalid_weights++;continue;}
            if(!influences){unweighted++;continue;}
            max_influences=Math.max(max_influences,influences);
            if(Math.abs(sum-1)>WEIGHT_TOLERANCE){not_normalized++;continue;}
            const name=mesh.skeleton.bones[strongest].name;
            const region=name===selection.bone_id?target:neighborIds.has(name)?neighbors:null;
            if(!region)continue;
            mesh.getVertexPosition(index,point).applyMatrix4(entry.transform);
            samples.push({entry,index,region,rest:point.toArray()});
        }
        offset+=position.count;
    }
    const restore=applyLocalPose(root,pose);
    try{
        for(const {entry,index,region,rest} of samples){
            entry.mesh.getVertexPosition(index,point).applyMatrix4(entry.transform);
            const displacement=Math.hypot(point.x-rest[0],point.y-rest[1],point.z-rest[2]);
            region.samples++;
            if(displacement>threshold)region.moved++;
            region.max=Math.max(region.max,displacement);
        }
    }finally{restore();}
    return {total,sampled,unweighted,invalid_weights,not_normalized,max_influences,target,neighbors};
}
