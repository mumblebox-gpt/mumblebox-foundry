import assert from "node:assert/strict";
import {test} from "node:test";
import * as three from "../material_lab/vendor/three.module.js";
import {SpatialIndex} from "../web/foundry/rigging/spatial.js";
import {measureMovement} from "../web/foundry/rigging/deformation.js";
import {constrainedMove} from "../web/foundry/rigging/transforms.js";

function setup(geometries, scale=[1,1,1]) {
    const root = new three.Group();
    const mesh = new three.Mesh(geometries[0], new three.MeshBasicMaterial());
    mesh.scale.fromArray(scale);
    for (const geometry of geometries.slice(1)) root.add(new three.Mesh(geometry, mesh.material));
    root.add(mesh);
    root.updateMatrixWorld(true);
    const camera = new three.PerspectiveCamera(35,1,.01,100);
    camera.position.set(0,0,6);
    camera.lookAt(0,0,0);
    camera.updateMatrixWorld(true);
    const observation = {camera:{type:"perspective",world:camera.matrixWorld.toArray(),
        projection:camera.projectionMatrix.toArray(),source_world:root.matrixWorld.toArray()},
        binding_key:null};
    return {index:new SpatialIndex(root,camera,three,8), observation, mesh};
}

test("depth records both surfaces of a closed mesh in source coordinates under nonuniform reflection", async () => {
    const {index,observation}=setup([new three.BoxGeometry(2,2,2)],[-1,2,1.5]);
    const [probe]=await index.probe(observation,[[.5,.5]]);
    assert.deepEqual(probe.hits.map(hit=>hit.position[2]),[1.5,-1.5]);
    assert.equal(probe.candidate_spans.length,1);
    assert.deepEqual(probe.candidate_spans[0].midpoint,[0,0,0]);
    assert.ok(probe.hits.every(hit=>Math.abs(hit.barycentric.reduce((a,b)=>a+b,0)-1)<1e-8));
    index.dispose();
});

test("a local axis and a local plane constrain the source-space result",()=>{
    const axes=[[0,0,1],[0,1,0],[-1,0,0]];
    assert.deepEqual(constrainedMove([1,1,1],[4,5,6],axes,"X"),[1,1,6]);
    assert.deepEqual(constrainedMove([1,1,1],[4,5,6],axes,"XZ"),[4,1,6]);
});

test("measure the exact mounted skin and restore the tested bone",()=>{
    const root=new three.Group();
    const geometry=new three.BufferGeometry();
    geometry.setAttribute("position",new three.Float32BufferAttribute([1,0,0,2,0,0,3,0,0,4,0,0,5,0,0,6,0,0],3));
    geometry.setAttribute("skinIndex",new three.Uint16BufferAttribute([0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],4));
    geometry.setAttribute("skinWeight",new three.Float32BufferAttribute([1,0,0,0,.8,.2,0,0,1,0,0,0,0,0,0,0,NaN,0,0,0,.5,0,0,0],4));
    const mesh=new three.SkinnedMesh(geometry,new three.MeshBasicMaterial());
    root.add(mesh);
    const target=new three.Bone(),neighbor=new three.Bone();
    target.name="finger"; neighbor.name="next";
    mesh.add(target,neighbor);
    root.updateMatrixWorld(true);
    mesh.bind(new three.Skeleton([target,neighbor]));
    const report=measureMovement(root,new three.Matrix4(),{bone_id:"finger",neighbor_ids:["next"]},
        {bone_id:"finger",axis:"z",angle:Math.PI/2},1e-4);
    assert.equal(report.target.moved,1);
    assert.equal(report.neighbors.moved,1);
    assert.equal(report.neighbors.samples,2);
    assert.ok(Math.abs(report.target.max-Math.SQRT2)<1e-7);
    assert.ok(Math.abs(report.neighbors.max-Math.SQRT2*.4)<1e-7);
    assert.equal(report.unweighted,1);
    assert.equal(report.invalid_weights,1);
    assert.equal(report.not_normalized,1);
    assert.equal(report.max_influences,2);
    assert.deepEqual(target.quaternion.toArray(),[0,0,0,1]);
});

test("open or nested surfaces cannot report a unique candidate pivot", async () => {
    for(const meshes of [[new three.PlaneGeometry(4,4)],
                         [new three.BoxGeometry(4,4,4),new three.BoxGeometry(2,2,2)]]){
        const {index,observation}=setup(meshes);
        const [probe]=await index.probe(observation,[[.5,.5]]);
        assert.deepEqual(probe.candidate_spans,[]);
        assert.ok(probe.ambiguous_reasons.length);
        index.dispose();
    }
});
