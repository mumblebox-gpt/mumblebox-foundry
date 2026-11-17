/** Query the mounted mesh without copying its vertices, materials or textures. */
const MAX_HITS = 64;
const MAX_TOPOLOGY_TRIANGLES = 100_000;
const DOUBLE_SIDE = 2;
const nextFrame = () => new Promise(resolve => setTimeout(resolve, 0));

function triangleVertices(geometry, triangle) {
    const start = triangle * 3;
    const indices = geometry.index;
    return [start, start+1, start+2].map(index => indices ? indices.getX(index) : index);
}

function closedTopology(geometry) {
    const position = geometry.attributes.position;
    const count = (geometry.index?.count ?? position.count) / 3;
    if (!Number.isInteger(count) || count > MAX_TOPOLOGY_TRIANGLES) return "unknown";
    // glTF may duplicate positions at UV or normal seams. Weld identical
    // positions for this check only, leaving the source triangle IDs intact.
    const vertices = new Map();
    const welded = new Uint32Array(position.count);
    for (let i=0; i<position.count; i++) {
        const key = [position.getX(i), position.getY(i), position.getZ(i)].join(",");
        if (!vertices.has(key)) vertices.set(key, vertices.size);
        welded[i] = vertices.get(key);
    }
    const edges = new Map();
    const stride = vertices.size;
    for (let triangle=0; triangle<count; triangle++) {
        const ids = triangleVertices(geometry, triangle).map(index => welded[index]);
        if (new Set(ids).size !== 3) return "unknown";
        for (let side=0; side<3; side++) {
            const a = ids[side], b = ids[(side+1)%3];
            const key = Math.min(a,b)*stride + Math.max(a,b);
            const sign = a < b ? 1 : -1;
            const previous = edges.get(key);
            if (previous === undefined) edges.set(key, sign);
            else if (previous === -sign) edges.set(key, 0);
            else return "overlapping_or_inconsistent";
        }
    }
    return Array.from(edges.values()).every(value => value === 0) ? "closed_edges" : "open_edges";
}

function barycentric(point, a, b, c) {
    const ab = b.clone().sub(a), ac = c.clone().sub(a), ap = point.clone().sub(a);
    const d00 = ab.dot(ab), d01 = ab.dot(ac), d11 = ac.dot(ac);
    const d20 = ap.dot(ab), d21 = ap.dot(ac);
    const denominator = d00*d11-d01*d01;
    if (denominator <= 0) return null;
    const v = (d11*d20-d01*d21)/denominator;
    const w = (d00*d21-d01*d20)/denominator;
    return [1-v-w, v, w];
}

export class SpatialIndex {
    constructor(root, camera, three, sourceDiagonal) {
        this.root = root;
        this.camera = camera;
        this.three = three;
        this.epsilon = Math.max(1e-9, sourceDiagonal*1e-7);
        this.meshes = [];
        this.primitiveIds = new Map();
        root.traverse(mesh => {
            if (!mesh.isMesh || !mesh.geometry.attributes.position || mesh.isInstancedMesh) return;
            const id = this.meshes.length;
            this.meshes.push(mesh);
            this.primitiveIds.set(mesh,id);
        });
        this.topology = new WeakMap();
        this.material = new three.MeshBasicMaterial({side:DOUBLE_SIDE});
        this.raycaster = new three.Raycaster();
    }

    async probe(observation, pixels, stillCurrent=()=>true) {
        const settings = observation.camera;
        const camera = settings.type === "orthographic" ? new this.three.OrthographicCamera() : new this.three.PerspectiveCamera();
        camera.matrixAutoUpdate = false;
        camera.matrix.fromArray(settings.world);
        camera.updateMatrixWorld(true);
        camera.projectionMatrix.fromArray(settings.projection);
        camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
        const displayToSource = camera.matrix.clone().fromArray(settings.source_world).invert();
        const results = [];
        for (const [x,y] of pixels) {
            if (!stillCurrent()) throw Error("The rig changed during the depth probe.");
            this.raycaster.setFromCamera({x:x*2-1,y:1-y*2},camera);
            const origin = this.raycaster.ray.origin.clone().applyMatrix4(displayToSource);
            const direction = this.raycaster.ray.direction.clone().transformDirection(displayToSource);
            const intersection = [];
            for (const mesh of this.meshes) {
                const material = mesh.material;
                try {
                    mesh.material = this.material;
                    mesh.raycast(this.raycaster,intersection);
                } finally {
                    mesh.material = material;
                }
            }
            results.push(this.describe([x,y], intersection, displayToSource, origin, direction, !!observation.binding_key));
            if (pixels.length > 1) await nextFrame();
        }
        if (!stillCurrent()) throw Error("The rig changed during the depth probe.");
        return results;
    }

    describe(pixel, intersection, displayToSource, origin, direction, bound) {
        intersection.sort((a,b)=>a.distance-b.distance);
        const hits = [], faces = [];
        for (const hit of intersection) {
            if (!hit.face || !Number.isInteger(hit.faceIndex)) continue;
            const point = hit.point.clone().applyMatrix4(displayToSource);
            const previous = hits.at(-1);
            const distance = point.distanceTo(origin);
            if (previous && Math.abs(distance-previous.distance)<=this.epsilon &&
                previous.primitive_id===this.primitiveIds.get(hit.object)) continue;
            if (hits.length === MAX_HITS) break;
            const mesh = hit.object;
            const inverse = mesh.matrixWorld.clone().invert();
            const vertices = [hit.face.a,hit.face.b,hit.face.c].map(index=>mesh.getVertexPosition(index,point.clone()));
            const weights = barycentric(hit.point.clone().applyMatrix4(inverse),...vertices);
            if (!weights) continue;
            const transform = displayToSource.clone().multiply(mesh.matrixWorld);
            const m = transform.invert().elements;
            const {x,y,z} = hit.face.normal;
            const normal = point.clone().set(m[0]*x+m[1]*y+m[2]*z,m[4]*x+m[5]*y+m[6]*z,m[8]*x+m[9]*y+m[10]*z).normalize();
            hits.push({primitive_id:this.primitiveIds.get(mesh),triangle_id:hit.faceIndex,barycentric:weights,
                position:point.toArray(),normal:normal.toArray(),distance,anchorable:!bound});
            faces.push(normal.dot(direction));
        }
        const truncated = hits.length===MAX_HITS && intersection.length>MAX_HITS;
        const reasons = [];
        const spans = [];
        let topology = "unknown";
        if (hits.length===2 && hits[0].primitive_id===hits[1].primitive_id) {
            const geometry = this.meshes[hits[0].primitive_id].geometry;
            if (!this.topology.has(geometry)) this.topology.set(geometry,closedTopology(geometry));
            topology=this.topology.get(geometry);
            if (topology==="closed_edges" && faces[0]<-1e-4 && faces[1]>1e-4 && hits[1].distance-hits[0].distance>this.epsilon)
                spans.push({near:0,far:1,midpoint:hits[0].position.map((value,i)=>(value+hits[1].position[i])/2)});
            else reasons.push(topology==="closed_edges"?"face_direction_uncertain":topology);
        } else reasons.push(hits.length>1?"multiple_or_disconnected_surfaces":"missing_surface");
        if(truncated)reasons.push("hit_limit");
        return {pixel,hits,candidate_spans:spans,topology_status:topology,ambiguous_reasons:reasons,truncated};
    }

    landmarkPosition(anchor) {
        const mesh=this.meshes[anchor.primitive_id];
        if (!mesh) return null;
        const ids=triangleVertices(mesh.geometry,anchor.triangle_id);
        if(ids.some(index=>index>=mesh.geometry.attributes.position.count))return null;
        const point=this.camera.position.clone().set(0,0,0);
        const vertex=point.clone();
        for(const [index,id] of ids.entries()){
            mesh.getVertexPosition(id,vertex);
            point.addScaledVector(vertex,anchor.barycentric[index]);
        }
        return point.applyMatrix4(mesh.matrixWorld);
    }

    dispose() {
        this.material.dispose();
        this.meshes.length=0;
        this.primitiveIds.clear();
    }
}
