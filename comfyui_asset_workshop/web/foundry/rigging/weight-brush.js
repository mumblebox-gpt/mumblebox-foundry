/** Inspect the native skinned mesh and collect one bounded world-space stroke. */
export class WeightBrush {
    constructor(viewport, spec, onStroke, onError, onSummary){
        this.viewport=viewport;
        this.spec=spec;
        this.onStroke=onStroke;
        this.onError=onError;
        this.onSummary=onSummary;
        this.original=new Map();
    }

    async show(options){
        this.options=options;
        if(!this.spec||!options||!this.viewport.viewer){
            this.restore();
            return;
        }
        const root=this.viewport.viewer.getCurrentModel();
        if(this.root===root&&this.bone===options.bone)return;
        this.restore();
        try{
            if(!this.three){
                const module=await import(this.spec.url);
                this.three=Object.fromEntries(Object.entries(this.spec.exports).map(([name,alias])=>[name,module[alias]]));
                this.raycaster=new this.three.Raycaster();
            }
            if(this.options!==options||this.viewport.viewer?.getCurrentModel()!==root)return;
            this.root=root;
            this.bone=options.bone;
            this.material??=new this.three.MeshBasicMaterial({vertexColors:true});
            let count=0,total=0;
            root.traverse(mesh=>{
                if(!mesh.isSkinnedMesh)return;
                const geometry=mesh.geometry;
                const {skinIndex,skinWeight}=geometry.attributes;
                if(!skinIndex||!skinWeight)return;
                const index=mesh.skeleton.bones.findIndex(bone=>bone.name===options.bone);
                const colors=new Float32Array(skinWeight.count*3);
                const get=["getX","getY","getZ","getW"];
                for(let vertex=0;vertex<skinWeight.count;vertex++){
                    let weight=0;
                    for(const component of get){
                        if(skinIndex[component](vertex)===index)weight+=skinWeight[component](vertex);
                    }
                    if(weight>0){count++;total+=weight;}
                    colors[vertex*3]=.08+.92*weight;
                    colors[vertex*3+1]=.2+.55*(1-Math.abs(2*weight-1));
                    colors[vertex*3+2]=.16+.8*(1-weight);
                }
                this.original.set(mesh,{material:mesh.material,color:geometry.getAttribute("color")});
                geometry.setAttribute("color",new this.three.BufferAttribute(colors,3));
                mesh.material=this.material;
            });
            this.onSummary?.({count,mean:count?Math.round(100*total/count):0});
            this.viewport.setOpacity(this.viewport.opacity);
        }catch(error){
            this.restore();
            this.onError(error);
        }
    }

    restore(){
        const redraw=this.original.size>0;
        for(const [mesh,original] of this.original){
            mesh.material=original.material;
            if(original.color)mesh.geometry.setAttribute("color",original.color);
            else mesh.geometry.deleteAttribute("color");
        }
        this.original.clear();
        this.root=null;
        this.bone=null;
        this.stroke=null;
        if(redraw){
            this.onSummary?.(null);
            this.viewport.setOpacity(this.viewport.opacity);
        }
    }

    point(event){
        const viewport=this.viewport;
        const box=viewport.element.getBoundingClientRect();
        const camera=viewport.camera;
        camera.updateMatrixWorld();
        this.raycaster.setFromCamera({
            x:(event.clientX-box.left)/box.width*2-1,y:1-(event.clientY-box.top)/box.height*2
        },camera);
        const hit=this.raycaster.intersectObjects([...this.original.keys()],false)[0];
        if(!hit)return null;
        return hit.point.applyMatrix4(viewport.meshTransform.clone().invert()).toArray();
    }

    handle(event){
        const options=this.options;
        if(!options?.paint||!this.original.size)return false;
        if(event.type==="pointerdown"){
            if(event.button!==0)return false;
            const point=this.point(event);
            if(!point)return false;
            this.stroke={id:event.pointerId,points:[point],options};
            this.viewport.element.setPointerCapture(event.pointerId);
        }
        const stroke=this.stroke;
        if(!stroke||stroke.id!==event.pointerId)return false;
        event.preventDefault();
        event.stopImmediatePropagation();
        if(event.type==="pointermove"&&stroke.points.length<options.maxPoints){
            const point=this.point(event);
            if(point&&Math.hypot(...point.map((x,i)=>x-stroke.points.at(-1)[i]))>options.radius*.3)
                stroke.points.push(point);
        }
        if(["pointerup","pointercancel","lostpointercapture"].includes(event.type)){
            this.stroke=null;
            if(this.viewport.element.hasPointerCapture(event.pointerId))
                this.viewport.element.releasePointerCapture(event.pointerId);
            if(event.type==="pointerup")this.onStroke(stroke);
        }
        return true;
    }

    dispose(){
        this.options=null;
        this.restore();
        this.material?.dispose();
    }
}
