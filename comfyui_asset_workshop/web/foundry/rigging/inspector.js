import {button,el,field,hint} from "../dom.js";
import {replaceContent,setText} from "../i18n.js";
import {request} from "../services.js";
import {rigText as t} from "./entry.js";

/** Spatial controls for the current selection and the preview it produced. */
export class RigInspector {
    constructor(wizard, token) {
        this.wizard=wizard;
        this.token=token;
        this.message=el("p", {role:"status"});
        this.previewPanel=el("div", {class:"rig-edit-preview",hidden:true});
        this.marks=el("div",{class:"rig-landmarks"});
        this.label=el("input",{type:"text",maxLength:100});
        this.useRegion=el("input",{type:"checkbox",onchange:event=>{
            wizard.viewport.linkRegion=event.target.checked;
            if(event.target.checked)wizard.viewport.frameSelection();
        }});
        this.regionSize=el("input",{type:"range",min:1,max:4,step:.25,value:1,onchange:event=>{
            wizard.viewport.regionScale=event.target.valueAsNumber;
            wizard.viewport.frameSelection();
        }});
        this.probe=button(t("spatial_probe"),()=>this.startProbe());
        this.result=el("div",{});
        this.testAxis=el("select",{},...["x","y","z"].map(axis=>el("option",{value:axis},axis.toUpperCase())));
        this.angle=el("input",{type:"number",min:-90,max:90,step:5,value:30});
        this.findings=el("div",{class:"rig-findings","aria-live":"polite"});
        this.movement=el("details",{},el("summary",{},t("spatial_movement")),field(t("spatial_local_axes"),this.testAxis),
            field(t("spatial_angle"),this.angle),
            button(t("spatial_bend"),()=>this.poseJoint()),button(t("spatial_rest"),()=>wizard.edit({action:"pose_joint",test_pose:null})),
            button(t("spatial_checks"),()=>this.check()),this.findings);
        this.element=el("details",{class:"rig-inspection"},
            el("summary",{},t("spatial_inspect")),this.probe,this.message,this.result,
            field(t("spatial_link_views"),this.useRegion),field(t("spatial_region_size"),this.regionSize),this.marks);
    }

    update(state){
        if(this.revision===state.rig_revision)return;
        this.revision=state.rig_revision;
        this.clearPreview();
        replaceContent(this.findings);
        replaceContent(this.result);
        setText(this.message,"");
        this.wizard.viewport.depthPicker=null;
        this.wizard.viewport.depthPreview=null;
        replaceContent(this.marks,...(state.surface_landmarks||[]).map(mark=>el("div",{class:"actions"},
            button(mark.label||t("spatial_landmark"),()=>{
                this.wizard.viewport.framePoints([mark.position]);
            }),
            button(t("spatial_remove"),()=>this.wizard.edit({
                action:"landmark_remove",id:mark.id,
            })))));
    }

    selectedPose(){
        const bone=this.wizard.selectedBone();
        return bone&&{bone_id:bone.id,axis:this.testAxis.value,angle:this.angle.valueAsNumber*Math.PI/180};
    }

    poseJoint(){
        const pose=this.selectedPose();
        if(pose)return this.wizard.edit({action:"pose_joint",test_pose:pose});
    }

    check(){
        const {wizard}=this;
        return wizard.act(async()=>{
            const state=wizard.state;
            const bone=wizard.selectedBone();
            if(!bone)return;
            const neighbor_ids=state.skeleton.bones.filter(item=>item.id!==bone.id&&
                (item.parent_id===bone.parent_id||item.id===bone.parent_id)).slice(0,32).map(item=>item.id);
            const result=await request("rigging/runs/"+state.id+"/check",{rig_revision:state.rig_revision,
                selection:{bone_id:bone.id,neighbor_ids},pose:state.bound?this.selectedPose():null});
            if(wizard.state!==state)return;
            replaceContent(this.findings,...result.findings.map(finding=>{
                const measure=finding.measure;
                return el("div",{class:"rig-finding","data-severity":finding.severity},
                    button(t("finding_"+finding.code),()=>{
                        if(wizard.state.rig_revision!==finding.identity.rig_revision)return;
                        if(finding.identity.binding_key&&wizard.state.output?.binding!==finding.identity.binding_key)return;
                        wizard.viewport.frame(finding.bone_ids);
                    }),finding.code==="weight_sample"?hint(t("spatial_weight_sample",measure)):
                        measure?.sampled?hint(t("spatial_measured",{moved:measure.moved,region:measure.samples,
                        sampled:measure.sampled,total:measure.total,max:Number(measure.max.toPrecision(3))})):
                        measure?.count?hint(String(measure.count)):null);
            }));
        });
    }

    startProbe(){
        const wizard=this.wizard,viewport=wizard.viewport;
        if(!viewport.viewer||viewport.drag)return;
        wizard.agentControls.humanCameraInput();
        setText(this.message,t("spatial_pick"));
        viewport.depthPicker=async pixel=>{
            viewport.depthPicker=null;
            const state=wizard.state;
            try{
                const observation={revision:state.revision,camera:viewport.cameraMetadata(),
                    binding_key:viewport.url===state.mesh_url?null:state.output?.binding};
                const [probe]=await viewport.probe(observation,[pixel],wizard.capabilities.spatial_tools);
                if(wizard.state!==state)return;
                this.showProbe(probe,state);
            }catch(error){setText(this.message,error.message);}
        };
    }

    showProbe(probe,state){
        const {wizard}=this;
        const first=probe.hits[0];
        const span=probe.candidate_spans[0];
        const bone=wizard.selectedBone();
        wizard.viewport.depthPreview=probe.hits.slice(0,8).map(hit=>hit.position);
        if(span)wizard.viewport.depthPreview.push(span.midpoint);
        wizard.viewport.draw();
        setText(this.message,t(!first?"spatial_no_hit":span?"spatial_span":"spatial_uncertain",{count:probe.hits.length}));
        const format=position=>position.map(value=>Number(value.toFixed(5))).join(", ");
        replaceContent(this.result,
            ...probe.hits.slice(0,4).map(hit=>hint(format(hit.position))),
            first?.anchorable?field(t("spatial_landmark"),this.label):null,
            first?.anchorable?button(t("spatial_save"),()=>{
                if(wizard.state!==state)return;
                return wizard.edit({action:"landmark_put",...first,label:this.label.value,
                    joint_id:wizard.selectedBone()?.id,source_sha256:state.source.sha256});
            }):null,
            span?button(t("spatial_review_move"),()=>{
                if(wizard.state!==state)return;
                return this.review([{action:"move",args:{joint:state.selected_joint,point:span.midpoint}}]);
            }):null,
            span&&bone?button(t("spatial_refit"),()=>{
                if(wizard.state!==state)return;
                const bones=state.skeleton.bones;
                let root=bone;
                while(root.part_id){
                    const parent=bones.find(item=>item.id===root.parent_id&&item.part_id===root.part_id);
                    if(!parent)break;
                    root=parent;
                }
                const tip=bone.legacy_tip||bone.id+"/tip";
                const endpoint=state.selected_joint===root.id?tip:state.selected_joint;
                return this.review([{action:"refit_branch",args:{root_id:root.id,preserve_outside:true,
                    candidate_points:{[endpoint]:span.midpoint}}}]);
            }):null);
    }

    batch(data){
        const {wizard}=this;
        return request("rigging/runs/"+wizard.state.id+"/batch",{browser:wizard.browser,...data});
    }

    review(commands){
        return this.wizard.act(()=>this.previewEdits(commands));
    }

    async previewEdits(commands){
        const {wizard}=this;
            const state=wizard.state;
            const preview=await this.batch({rig_revision:state.rig_revision,request_id:this.token(),operation:"preview",commands});
            if(wizard.state!==state)return;
            this.previewPanel.hidden=false;
            wizard.viewport.editGhost=Object.values(preview.bones).map(change=>change.after).filter(Boolean);
            wizard.viewport.draw();
            const request_id=this.token();
            const base={rig_revision:state.rig_revision,request_id,preview_id:preview.preview_id};
            replaceContent(this.previewPanel,hint(t("spatial_batch_summary",{count:preview.changed_bone_ids.length})),
                ...preview.warnings.map(warning=>hint(t("spatial_"+warning))),
                ...preview.changed_bone_ids.slice(0,12).map(id=>hint(preview.bones[id]?.after?.label||wizard.label(id))),
                button(t("spatial_apply"),()=>wizard.act(async()=>{
                    const result=await this.batch({...base,operation:"apply"});
                    await wizard.update(result);
                })),
                button(t("spatial_discard"),()=>{
                    this.clearPreview();
                    void this.batch({...base,operation:"discard"}).catch(()=>{});
                }));
    }

    clearPreview(){
        this.previewPanel.hidden=true;
        if(this.wizard.viewport){
            this.wizard.viewport.editGhost=null;
            this.wizard.viewport.draw();
        }
    }
}
