import {el} from "../dom.js";
import {mountMesh} from "../wizard/preview.js";
import {inspectionCamera,nativeThree,renderObservation} from "./observations.js";
import {SpatialIndex} from "./spatial.js";
import {constrainedMove,editAxes} from "./transforms.js";
import {applyLocalPose,measureMovement} from "./deformation.js";

const AXIS_COLORS=["#ff877d","#a6e898","#8ac6ff"];

export class RigViewport {
    constructor(onEdit, jointLabel, onDrag) {
        this.onEdit=onEdit;
        this.jointLabel=jointLabel;
        this.onDrag=onDrag;
        this.cameraRevision=0;
        this.mount=el("div",{class:"rig-native"});
        this.canvas=el("canvas",{class:"rig-joints","aria-hidden":"true"});
        this.element=el("div",{class:"rig-viewport",tabIndex:0},this.mount,this.canvas);
        this.events=new AbortController();
        const options={capture:true,signal:this.events.signal};
        for(const type of ["pointerdown","pointermove","pointerup","pointercancel","lostpointercapture"])
            this.element.addEventListener(type,event=>this.pointer(event),options);
        this.element.addEventListener("keydown",event=>this.keyboard(event),options);
        this.resize=new ResizeObserver(()=>this.draw());
        this.resize.observe(this.element);
        this.view="front";
        this.tool="move";
        this.opacity=1;
        this.faded=new Map();
    }

    async show(state,module) {
        this.restoreJointPose?.();
        this.restoreJointPose=null;
        this.state=state;
        // The rest-pose editor always uses the same source mesh. Edits can
        // invalidate a binding without replacing the canvas under the cursor.
        const useRig=(state.pose!=="rest"||state.step==="review")&&Boolean(state.weight_preview_url||state.rig_url);
        const url=useRig?(state.weight_preview_url||state.rig_url):state.mesh_url;
        if(this.url!==url){
            const cameraState=this.cameraState()||this.savedView;
            this.url=url;
            const sequence=this.sequence=(this.sequence||0)+1;
            this.restoreOpacity();
            this.spatial?.dispose();
            this.spatial=null;
            this.weights?.restore();
            this.release?.();
            this.release=null;
            this.viewer=null;
            this.mount.replaceChildren();
            this.draw();
            let viewer;
            const loading=mountMesh(this.mount,url,module,useRig?"rig.glb":"source.glb");
            this.loading=loading;
            try{
                viewer=await loading;
            }catch(error){
                if(this.closed||sequence!==this.sequence)return;
                this.url=null;
                throw error;
            }finally{
                if(this.loading===loading)this.loading=null;
            }
            if(this.closed||sequence!==this.sequence){viewer();return;}
            this.release=viewer;
            this.viewer=viewer.viewer;
            const controls=this.viewer.getControlsManager().controls;
            controls.addEventListener("change",()=>{this.cameraRevision++;this.draw();this.saveCamera();},{signal:this.events.signal});
            this.viewer.toggleGrid?.(false);
            this.viewer.getSceneManager?.().setBackgroundColor("#202832");
            this.viewer.toggleAnimation?.(false);
            this.orient(this.view);
            this.restoreCamera(cameraState);
            this.setOpacity(this.opacity);
        }else if(this.loading){
            await this.loading;
        }
        if(this.viewer && this.state.id===state.id){
            const current=this.state;
            this.applyViewPose(current);
            this.draw();
        }
    }

    applyViewPose(state){
        this.restoreJointPose?.();
        this.restoreJointPose=null;
        this.viewer.setAnimationTime?.(state.output?.report?.pose_seconds?.[state.pose]||0);
        const testPose=state.step==="review"?state.joint_pose:null;
        if(testPose)this.restoreJointPose=applyLocalPose(this.viewer.getCurrentModel(),testPose);
        this.viewer.setShowSkeleton?.(state.pose!=="rest"||!!testPose);
        this.viewer.forceRender();
    }

    measure(identity,selection,pose){
        const state=this.state;
        if(!this.viewer||this.drag||state.revision!==identity.revision||!state.bound||
            state.output?.binding!==identity.binding_key||this.url===state.mesh_url)
            throw Error("The visible binding changed during the movement check.");
        const root=this.viewer.getCurrentModel();
        const transform=this.meshTransform.clone().invert();
        const diagonal=Math.hypot(...state.bounds[1].map((value,axis)=>value-state.bounds[0][axis]));
        this.restoreJointPose?.();
        this.restoreJointPose=null;
        this.viewer.setAnimationTime?.(state.output.report.pose_seconds?.rest||0);
        root.updateWorldMatrix(true,true);
        try{return measureMovement(root,transform,selection,pose,Math.max(diagonal*1e-4,1e-8));}
        finally{this.applyViewPose(state);}
    }

    get camera(){return this.viewer?.getCameraManager().activeCamera;}

    cameraState(){
        if(!this.viewer||this.capturing)return null;
        const {position,target,zoom,cameraType,fov}=this.viewer.getCameraState();
        return {view:this.view,position:position.toArray(),target:target.toArray(),zoom,cameraType,fov};
    }

    saveCamera(){
        if(this.capturing)return;
        clearTimeout(this.cameraSave);
        this.cameraSave=setTimeout(()=>{const state=this.cameraState();if(state)this.onCamera?.(state);},160);
    }

    restoreCamera(saved){
        const validVector=point=>Array.isArray(point)&&point.length===3&&point.every(Number.isFinite);
        if(!saved||!validVector(saved.position)||!validVector(saved.target)||!(saved.zoom>0&&saved.zoom<100))return;
        const native=this.viewer.getCameraState();
        this.view=["front","side","back","oblique"].includes(saved.view)?saved.view:"front";
        this.viewer.setCameraState({...native,zoom:saved.zoom,fov:saved.fov>0&&saved.fov<180?saved.fov:34,
            cameraType:saved.cameraType==="orthographic"?"orthographic":"perspective",
            position:native.position.clone().fromArray(saved.position),target:native.target.clone().fromArray(saved.target)});
        this.viewer.forceRender();
    }

    get meshTransform() {
        // The native viewer fits the glTF scene root to its display bounds.
        // Rig state stays in the mesh's original glTF coordinates.
        const root=this.viewer.getCurrentModel();
        root.updateWorldMatrix(true,false);
        return root.matrixWorld;
    }

    orient(view) {
        this.view=view;
        if(!this.viewer)return;
        const bounds=this.viewer.modelManager.getCurrentBounds();
        const seed=this.camera.position.clone();
        const target=bounds.getCenter(seed);
        const span=bounds.getSize(target.clone());
        const radius=Math.max(span.x,span.y,span.z);
        const yaw=this.state.orientation*Math.PI/2+({side:Math.PI/2,back:Math.PI,oblique:Math.PI/4}[view]||0);
        const position=target.clone().add(target.clone().set(Math.sin(yaw),0,Math.cos(yaw)).multiplyScalar(radius*2.45));
        const old=this.viewer.getCameraState();
        this.viewer.setCameraState({...old,position,target,zoom:1,
            cameraType:({front:true,side:true,back:true})[view]?"orthographic":"perspective",fov:34});
        this.cameraRevision++;
        this.viewer.setFOV?.(34);
        this.viewer.forceRender();
        if(this.linkRegion){this.frameSelection();return;}
        this.draw();
    }

    frame(ids){
        if(!this.viewer)return;
        if(!ids?.length){this.orient(this.view);return;}
        this.framePoints(ids.map(id=>this.state.joints[id]).filter(Boolean));
    }

    framePoints(sourcePoints){
        if(!this.viewer)return;
        const points=sourcePoints.map(point=>
            this.camera.position.clone().fromArray(point).applyMatrix4(this.meshTransform));
        if(!points.length)return;
        const low=points[0].clone(),high=points[0].clone();
        for(const point of points){low.min(point);high.max(point);}
        const target=low.clone().add(high).multiplyScalar(.5);
        const modelSize=this.viewer.modelManager.getCurrentBounds().getSize(target.clone()).length();
        const radius=Math.max(low.distanceTo(high)*2.8,modelSize*.12);
        const camera=this.viewer.getCameraState();
        const direction=camera.position.clone().sub(camera.target).normalize();
        let zoom=camera.zoom;
        if(this.camera.isOrthographicCamera){
            this.camera.updateMatrixWorld();
            const inverse=this.camera.matrixWorldInverse;
            const center=target.clone().applyMatrix4(inverse);
            let w=modelSize*.045,h=modelSize*.045;
            for(const point of points){
                const viewPoint=point.clone().applyMatrix4(inverse);
                w=Math.max(w,Math.abs(viewPoint.x-center.x));
                h=Math.max(h,Math.abs(viewPoint.y-center.y));
            }
            zoom=Math.min((this.camera.right-this.camera.left)*.36/w,(this.camera.top-this.camera.bottom)*.36/h);
        }
        this.viewer.setCameraState({...camera,target,zoom,position:target.clone().addScaledVector(direction,radius)});
        this.cameraRevision++;
        this.viewer.forceRender();
        this.draw();
    }

    frameSelection(){
        const region=this.selectedRegion();
        if(!region)return this.frame([this.state.selected_joint]);
        this.framePoints(region.corners);
    }

    coords(width,height,camera=this.camera) {
        if(!camera)return {};
        camera.updateMatrixWorld();
        const meshTransform=this.meshTransform;
        const joints=this.drag?.draft||this.state.joints;
        const projected={};
        const p=camera.position.clone();
        for(const [name,[x,y,z]] of Object.entries(joints)){
            p.set(x,y,z).applyMatrix4(meshTransform).project(camera);
            if(p.z>=-1&&p.z<=1)projected[name]=[(p.x+1)*width/2,(1-p.y)*height/2,p.z];
        }
        return projected;
    }

    restoreOpacity(){
        for(const [material,original] of this.faded){
            Object.assign(material,original);
            material.needsUpdate=true;
        }
        this.faded.clear();
    }

    setOpacity(value){
        this.opacity=value;
        if(!this.viewer)return;
        if(value===1)this.restoreOpacity();
        else this.viewer.getCurrentModel()?.traverse(object=>{
            if(!object.isMesh)return;
            for(const material of [object.material].flat()){
                if(!material)continue;
                if(!this.faded.has(material)){
                    this.faded.set(material,{opacity:material.opacity,transparent:material.transparent,depthWrite:material.depthWrite});
                    material.transparent=true;
                    material.depthWrite=false;
                    material.needsUpdate=true;
                }
                material.opacity=this.faded.get(material).opacity*value;
            }
        });
        this.viewer.forceRender();
    }

    handles(joints, width, height, selected,camera=this.camera){
        const origin=joints[selected];
        if(!origin||this.tool!=="move"||this.locked)return [];
        const source=this.drag?.draft[selected]||this.state.joints[selected];
        const distance=(this.state.bounds[1][1]-this.state.bounds[0][1])*.075;
        const matrix=this.meshTransform;
        const axes=editAxes(this.state,this.localAxes,selected);
        return AXIS_COLORS.map((color,axis)=>{
            const basis=axes[axis];
            const p=camera.position.clone().fromArray(source.map((value,index)=>value+basis[index]*distance));
            p.applyMatrix4(matrix).project(camera);
            const dx=(p.x+1)*width/2-origin[0],dy=(1-p.y)*height/2-origin[1];
            const length=Math.hypot(dx,dy);
            const depth=length<4;
            const direction=depth?[Math.SQRT1_2,Math.SQRT1_2]:[dx/length,dy/length];
            return {axis,basis,color,origin,direction,depth,scale:distance/Math.max(length,30),
                x:origin[0]+direction[0]*(depth?30:47),y:origin[1]+direction[1]*(depth?30:47)};
        });
    }

    selectedBone(joint){
        return this.state.skeleton?.bones.find(bone=>bone.id===joint||
            (bone.legacy_tip||bone.id+"/tip")===joint);
    }

    overlaps(x,y,joints){
        return Object.entries(joints).map(([id,[jx,jy,depth]])=>({id,depth,distance:Math.hypot(x-jx,y-jy)}))
            .filter(item=>item.distance<=14)
            .sort((a,b)=>Math.floor(a.distance/4)-Math.floor(b.distance/4)||a.depth-b.depth||a.distance-b.distance);
    }

    placePoint(reference,onPlace){
        this.pointPicker={reference,onPlace};
    }

    keyboard(event){
        if(event.key==="Escape"&&this.drag){
            const drag=this.drag;
            this.drag=null;
            if(this.element.hasPointerCapture(drag.id))this.element.releasePointerCapture(drag.id);
            void this.finishDrag(drag,false);
            event.preventDefault();
            this.draw();
            return;
        }
        if(event.key==="Escape"&&this.pointPicker){
            this.pointPicker=null;
            event.preventDefault();
            return;
        }
        if(this.locked||this.drag||!this.state||this.state.pose!=="rest")return;
        const joint=this.state.selected_joint;
        if((event.key==="["||event.key==="]")&&this.camera){
            const joints=this.coords(this.element.clientWidth,this.element.clientHeight);
            if(!joints[joint])return;
            const nearby=this.overlaps(...joints[joint].slice(0,2),joints);
            const next=(nearby.findIndex(item=>item.id===joint)+(event.key==="]"?1:-1)+nearby.length)%nearby.length;
            event.preventDefault();
            this.onEdit({action:"select",joint:nearby[next].id,revision:this.state.revision});
            return;
        }
        const axes={ArrowLeft:[0,-1],ArrowRight:[0,1],ArrowUp:[1,1],ArrowDown:[1,-1],PageUp:[2,1],PageDown:[2,-1]};
        if(!axes[event.key])return;
        const [axis,direction]=axes[event.key];
        const point=this.state.joints[joint]?.slice();
        if(!point)return;
        const increment=(this.state.bounds[1][1]-this.state.bounds[0][1])/(event.shiftKey?100:400);
        editAxes(this.state,this.localAxes,joint)[axis].forEach((basis,index)=>{point[index]+=basis*direction*increment;});
        event.preventDefault();
        this.onEdit({action:"move",joint,point,rigRevision:this.state.rig_revision});
    }

    draw(target=this.canvas,width=this.element.clientWidth,height=this.element.clientHeight,camera=this.camera) {
        if(!width||!height)return;
        if(target===this.canvas){
            const pixelRatio=Math.min(window.devicePixelRatio||1,2);
            const w=Math.round(width*pixelRatio), h=Math.round(height*pixelRatio);
            if(target.width!==w||target.height!==h){target.width=w;target.height=h;}
            target.getContext("2d").setTransform(pixelRatio,0,0,pixelRatio,0,0);
        }
        const ctx=target.getContext("2d");
        if(target===this.canvas)ctx.clearRect(0,0,width,height);
        if(!this.viewer||this.state.pose!=="rest"||(this.state.step==="review"&&this.state.joint_pose))return;
        if(this.url===this.state.mesh_url)for(const mark of this.state.surface_landmarks||[]){
            if(mark.source_sha256!==this.state.source.sha256)continue;
            const point=this.spatial?.landmarkPosition(mark)||
                camera.position.clone().fromArray(mark.position).applyMatrix4(this.meshTransform);
            point.project(camera);
            if(point.z< -1||point.z>1)continue;
            const x=(point.x+1)*width/2,y=(1-point.y)*height/2;
            ctx.save();
            ctx.translate(x,y);
            ctx.strokeStyle="#ffe49f";
            ctx.lineWidth=2;
            ctx.beginPath();
            ctx.moveTo(-7,0);ctx.lineTo(0,-7);ctx.lineTo(7,0);ctx.lineTo(0,7);ctx.closePath();ctx.stroke();
            ctx.font="bold 12px system-ui";
            ctx.fillStyle="#ffe49f";
            if(mark.label)ctx.fillText(mark.label,10,0);
            ctx.restore();
        }
        const joints=this.coords(width,height,camera);
        const selected=this.drag?.joint||this.state.selected_joint;
        for(const [start,end] of this.state.chains){
            if(!joints[start]||!joints[end])continue;
            ctx.beginPath();
            ctx.moveTo(...joints[start].slice(0,2));
            ctx.lineTo(...joints[end].slice(0,2));
            ctx.strokeStyle="#11202c";
            ctx.lineWidth=5;
            ctx.stroke();
            ctx.strokeStyle=start===selected||end===selected?"#ffcca0":"#83e6e0";
            ctx.lineWidth=2;
            ctx.stroke();
        }
        for(const [name,[x,y]] of Object.entries(joints)){
            ctx.beginPath();
            ctx.arc(x,y,name===selected?7:4,0,Math.PI*2);
            ctx.fillStyle=name===selected?"#ffae63":"#d8fffb";
            ctx.fill();
            ctx.strokeStyle="#11202c";
            ctx.lineWidth=1.5;
            ctx.stroke();
        }
        if(joints[selected]){
            const [x,y]=joints[selected];
            ctx.font="bold 14px system-ui";
            ctx.lineWidth=4;
            const label=String(this.jointLabel(selected));
            const left=Math.max(5,Math.min(x+11,width-ctx.measureText(label).width-6));
            ctx.strokeText(label,left,y-9);
            ctx.fillStyle="#fff4e9";
            ctx.fillText(label,left,y-9);
            ctx.save();
            for(const handle of this.handles(joints,width,height,selected,camera)){
                ctx.strokeStyle=ctx.fillStyle=handle.color;
                ctx.lineWidth=2;
                if(handle.depth)ctx.setLineDash([4,4]);
                ctx.beginPath();
                ctx.moveTo(x,y);
                ctx.lineTo(handle.x,handle.y);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillRect(handle.x-9,handle.y-9,18,18);
                ctx.fillStyle="#13232b";
                ctx.textAlign="center";
                ctx.textBaseline="middle";
                ctx.fillText("XYZ"[handle.axis],handle.x,handle.y);
            }
            if(this.tool==="orient"&&!this.locked&&this.selectedBone(selected)){
                const roll=this.drag?.roll??this.selectedBone(selected).roll??0;
                ctx.strokeStyle=ctx.fillStyle="#ffd280";
                ctx.lineWidth=3;
                ctx.beginPath();
                ctx.arc(x,y,33,0,2*Math.PI);
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(x+33*Math.cos(roll),y+33*Math.sin(roll),6,0,2*Math.PI);
                ctx.fill();
            }
            ctx.restore();
        }
        const ghost=[...(this.ghostPart||[]),...(this.editGhost||[]),...(this.agentGhost||[])];
        if(ghost.length){
            const matrix=this.meshTransform;
            const xy=point=>{
                const p=camera.position.clone().fromArray(point).applyMatrix4(matrix).project(camera);
                return [(p.x+1)*width/2,(1-p.y)*height/2];
            };
            ctx.beginPath();
            for(const bone of ghost){ctx.moveTo(...xy(bone.head));ctx.lineTo(...xy(bone.tail));}
            ctx.setLineDash([5,4]);
            ctx.strokeStyle="#ffd280";
            ctx.lineWidth=3;
            ctx.stroke();
            ctx.setLineDash([]);
        }
        for(const [index,position] of (this.depthPreview||[]).entries()){
            const point=camera.position.clone().fromArray(position).applyMatrix4(this.meshTransform).project(camera);
            ctx.beginPath();
            ctx.arc((point.x+1)*width/2,(1-point.y)*height/2,5+index*2,0,Math.PI*2);
            ctx.strokeStyle="#ffd280";
            ctx.lineWidth=2;
            ctx.stroke();
        }
    }

    pointer(event) {
        if(!this.camera||this.capturing)return;
        if(this.weights?.handle(event))return;
        if(!this.drag&&(this.locked||this.state.pose!=="rest"))return;
        const box=this.element.getBoundingClientRect();
        const {clientWidth:width,clientHeight:height}=this.element;
        if(!width||!height||!box.width||!box.height)return;
        const x=(event.clientX-box.left)*width/box.width,y=(event.clientY-box.top)*height/box.height;
        if(this.depthPicker&&event.type==="pointerdown"&&event.button===0){
            event.preventDefault();
            event.stopImmediatePropagation();
            this.depthPicker([x/width,y/height]);
            return;
        }
        if(this.pointPicker&&event.type==="pointerdown"&&event.button===0){
            event.preventDefault();
            event.stopImmediatePropagation();
            const {reference,onPlace}=this.pointPicker;
            const matrix=this.meshTransform;
            const point=this.camera.position.clone().fromArray(reference).applyMatrix4(matrix).project(this.camera);
            point.set(x/width*2-1,1-y/height*2,point.z)
                .unproject(this.camera).applyMatrix4(matrix.clone().invert());
            this.pointPicker=null;
            onPlace(point.toArray());
            return;
        }
        if(this.tool==="orbit")return;
        if(event.type==="pointerdown"){
            if(event.button!==0)return;
            const joints=this.coords(width,height);
            const selected=this.state.selected_joint;
            const nearby=this.overlaps(x,y,joints);
            const handle=this.handles(joints,width,height,selected).find(handle=>Math.hypot(x-handle.x,y-handle.y)<10);
            const place=this.tool==="place"||event.shiftKey;
            const center=joints[selected];
            const bone=this.tool==="orient"&&center&&Math.abs(Math.hypot(x-center[0],y-center[1])-33)<11?
                this.selectedBone(selected):null;
            const current=nearby.findIndex(item=>item.id===selected);
            const pick=this.tool==="select"?nearby[(current+1)%nearby.length]?.id:nearby[0]?.id;
            const joint=place||handle||bone?selected:pick;
            if(!joint||!joints[joint])return;
            if(!place&&!bone&&["select","orient"].includes(this.tool)){
                event.preventDefault();
                event.stopImmediatePropagation();
                this.element.focus({preventScroll:true});
                this.onEdit({action:"select",joint,revision:this.state.revision});
                return;
            }
            if(this.selectedBone(joint)?.locked)return;
            this.drag={id:event.pointerId,joint,depth:joints[joint][2],revision:this.state.revision,
                       rigRevision:this.state.rig_revision,
                       x,y,place,origin:this.state.joints[joint],
                       moved:place,draft:{...this.state.joints},handle,bone,center};
            const drag=this.drag;
            drag.token=crypto.randomUUID().replaceAll("-","");
            drag.lease=this.onDrag(drag).catch(error=>{drag.leaseError=error;});
            drag.renew=setInterval(()=>this.onDrag(drag).catch(error=>{drag.leaseError=error;}),4000);
            this.element.focus({preventScroll:true});
            this.element.setPointerCapture(event.pointerId);
        }
        const drag=this.drag;
        if(!drag||event.pointerId!==drag.id)return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if(Math.hypot(x-drag.x,y-drag.y)>2)drag.moved=true;
        if(drag.moved&&!["pointercancel","lostpointercapture"].includes(event.type)){
            if(drag.bone){
                const angle=(a,b)=>Math.atan2(b-drag.center[1],a-drag.center[0]);
                const roll=drag.bone.roll+angle(x,y)-angle(drag.x,drag.y);
                drag.roll=Math.atan2(Math.sin(roll),Math.cos(roll));
            }else if(drag.handle){
                const {basis,direction,scale}=drag.handle;
                const delta=(x-drag.x)*direction[0]+(y-drag.y)*direction[1];
                drag.draft[drag.joint]=drag.origin.map((value,index)=>value+basis[index]*delta*scale);
            }else{
                const inverseTransform=this.meshTransform.clone().invert();
                const onPlane=(px,py)=>this.camera.position.clone().set(px/width*2-1,1-py/height*2,drag.depth)
                    .unproject(this.camera).applyMatrix4(inverseTransform);
                const point=onPlane(x,y);
                if(!drag.place)point.sub(onPlane(drag.x,drag.y)).add(point.clone().fromArray(drag.origin));
                drag.draft[drag.joint]=point.toArray().map(v=>Number(v.toFixed(7)));
                if(!drag.place)drag.draft[drag.joint]=constrainedMove(drag.origin,drag.draft[drag.joint],
                    editAxes(this.state,this.localAxes,drag.joint),this.axis);
            }
        }
        if(["pointerup","pointercancel","lostpointercapture"].includes(event.type)){
            this.drag=null;
            if(this.element.hasPointerCapture(event.pointerId))this.element.releasePointerCapture(event.pointerId);
            void this.finishDrag(drag,event.type==="pointerup");
        }
        this.draw();
    }

    async finishDrag(drag, apply){
        clearInterval(drag.renew);
        await drag.lease;
        let released=false;
        try{
            if(!apply||this.closed)return;
            if(!drag.moved){
                await this.onDrag(drag,true);
                released=true;
                await this.onEdit({action:"select",joint:drag.joint,revision:drag.revision});
                return;
            }
            const edit=drag.bone?{action:"orient",bone_id:drag.bone.id,roll:drag.roll}:
                {action:"move",joint:drag.joint,point:drag.draft[drag.joint]};
            if(edit.action==="move"&&this.previewMirror?.()){
                await this.onDrag(drag,true);
                released=true;
            }
            await this.onEdit({...edit,rigRevision:drag.rigRevision,drag:released?undefined:drag.token,dragError:drag.leaseError});
        }finally{
            if(!released)await this.onDrag(drag,true).catch(()=>{});
        }
    }

    selectedRegion(){
        const bone=this.selectedBone(this.state.selected_joint);
        if(!bone)return null;
        const bones=bone.part_id?this.state.skeleton.bones.filter(item=>item.part_id===bone.part_id):[bone];
        const points=bones.flatMap(item=>[item.head,item.tail]);
        const low=[0,1,2].map(axis=>Math.min(...points.map(point=>point[axis])));
        const high=[0,1,2].map(axis=>Math.max(...points.map(point=>point[axis])));
        const extent=this.state.bounds[1].map((upper,axis)=>upper-this.state.bounds[0][axis]);
        const scale=this.regionScale||1;
        const diagonal=Math.hypot(...extent);
        const pad=Math.max(diagonal*.04,Math.hypot(...high.map((value,axis)=>value-low[axis]))*.45)*scale;
        const probeMin=low.map(value=>value-pad),probeMax=high.map(value=>value+pad);
        const key=[this.url,this.state.revision,bone.id,scale].join(":");
        if(this.regionCache?.key===key)return this.regionCache.region;
        const root=this.viewer.getCurrentModel();
        const toSource=this.meshTransform.clone().invert();
        const point=this.camera.position.clone();
        const boneIds=new Set(bones.map(item=>item.id));
        let scoped=0;
        root.traverse(mesh=>{
            if(!mesh.isMesh||!mesh.geometry.attributes.position)return;
            const {position,skinIndex,skinWeight}=mesh.geometry.attributes;
            const transform=toSource.clone().multiply(mesh.matrixWorld);
            const influences=mesh.isSkinnedMesh&&skinIndex&&skinWeight
                ?new Set(mesh.skeleton.bones.flatMap((item,index)=>boneIds.has(item.name)?[index]:[])):null;
            for(let i=0;i<position.count;i++){
                if(influences?.size&&!(["getX","getY","getZ","getW"].some(axis=>influences.has(skinIndex[axis](i))&&skinWeight[axis](i)>.01)))continue;
                mesh.getVertexPosition(i,point).applyMatrix4(transform);
                const values=[point.x,point.y,point.z];
                if(!influences?.size&&!values.every((value,axis)=>value>=probeMin[axis]&&value<=probeMax[axis]))continue;
                scoped++;
                for(let axis=0;axis<3;axis++){
                    low[axis]=Math.min(low[axis],values[axis]);
                    high[axis]=Math.max(high[axis],values[axis]);
                }
            }
        });
        const center=low.map((value,axis)=>(value+high[axis])/2);
        const half=high.map((value,axis)=>Math.max(diagonal*.014,(value-low[axis])*.55));
        const corners=[];
        for(const x of [-1,1])for(const y of [-1,1])for(const z of [-1,1])
            corners.push(center.map((value,axis)=>value+[x,y,z][axis]*half[axis]));
        const region={center,radius:Math.hypot(...half),corners,vertices:scoped};
        this.regionCache={key,region};
        return region;
    }

    async capture(view,spatialTools) {
        if(!this.viewer||this.drag)throw Error("Wait for the rig viewport to load or the joint drag to finish.");
        const viewer=this.viewer;
        const state=this.state;
        const three=await nativeThree(spatialTools);
        if(this.closed||this.viewer!==viewer||this.state!==state||this.drag)
            throw Error("The rig changed during capture. Try again.");
        const aspect=Math.max(1,this.element.clientWidth)/Math.max(1,this.element.clientHeight);
        for(const edge of [848,680,544,432,344]){
            const width=Math.max(1,Math.round(edge*Math.min(1,aspect)));
            const height=Math.max(1,Math.round(edge/Math.max(1,aspect)));
            const camera=inspectionCamera(this,view,width/height,three);
            const metadata={world:camera.matrixWorld.toArray(),projection:camera.projectionMatrix.toArray(),
                source_world:this.meshTransform.toArray(),revision:this.cameraRevision,
                type:camera.isOrthographicCamera?"orthographic":"perspective"};
            const canvas=renderObservation(viewer,camera,width,height,three);
            this.draw(canvas,width,height,camera);
            const png=canvas.toDataURL("image/png").split(",")[1];
            if(png.length<=900000){
                const visible_joints=state.pose==="rest"?Object.entries(this.coords(width,height,camera))
                    .filter(([,point])=>point[0]>=0&&point[0]<=width&&point[1]>=0&&point[1]<=height)
                    .map(([id])=>id):[];
                return {png,camera:metadata,visible_joints};
            }
        }
        throw Error("The rig viewport image exceeds the capture size limit.");
    }

    cameraMetadata(){
        this.camera.updateMatrixWorld();
        return {world:this.camera.matrixWorld.toArray(),projection:this.camera.projectionMatrix.toArray(),
            source_world:this.meshTransform.toArray(),type:this.camera.isOrthographicCamera?"orthographic":"perspective"};
    }

    async probe(observation,pixels,spatialTools){
        if(!this.viewer||this.drag||observation.revision!==this.state.revision)
            throw Error("The rig changed during the depth probe.");
        const viewer=this.viewer,state=this.state;
        const current=()=>!this.closed&&this.viewer===viewer&&this.state===state&&!this.drag;
        const three=await nativeThree(spatialTools);
        if(!current())throw Error("The rig changed during the depth probe.");
        const diagonal=Math.hypot(...state.bounds[1].map((value,axis)=>value-state.bounds[0][axis]));
        this.spatial??=new SpatialIndex(viewer.getCurrentModel(),this.camera,three,diagonal);
        return this.spatial.probe(observation,pixels,current);
    }

    dispose() {
        clearTimeout(this.cameraSave);
        const camera=this.cameraState();
        if(camera)this.onCamera?.(camera);
        this.closed=true;
        this.restoreJointPose?.();
        this.spatial?.dispose();
        this.restoreOpacity();
        this.weights?.dispose();
        if(this.drag){void this.finishDrag(this.drag,false);this.drag=null;}
        this.events.abort();
        this.resize.disconnect();
        this.release?.();
    }
}
