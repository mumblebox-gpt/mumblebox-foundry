import {api} from "/scripts/api.js";
import {appendContent,msg,onLanguageChange,replaceContent,setText,sourceMessage} from "../i18n.js";
import {button,el,field,hint} from "../dom.js";
import {request} from "../services.js";
import {rigText as t} from "./entry.js";
import {RigPresets,setupHint} from "./method-controls.js";
import {PartAuthor} from "./part-author.js";
import {RigViewport} from "./viewer.js";
import {WeightBrush} from "./weight-brush.js";
import {AgentControls} from "./agent-control.js";
import {RigInspector} from "./inspector.js";

const EVENT="mumblebox-foundry-rigging";
const path=id=>"rigging/runs/"+id;
const token=()=>crypto.randomUUID().replaceAll("-","");
const STEPS=["build","fit","review","export"];
const VIEW_KEY="mumblebox-foundry:rig-camera";
const COMMANDS=new Set(["move","orient","add_chain","add_part","remove_chain","reparent","pair","mirror_chain","label","role","lock","undo","redo",
    "weight_stroke","weight_lock","side","landmark_put","landmark_remove","refit_branch"]);
const jointLabel=name=>{
    const [joint,side]=name.split(".");
    return side?t(side==="L"?"left_joint":"right_joint",{joint:t("joint_"+joint)}):t("joint_"+joint);
};

function storedView(id){
    try{
        const saved=JSON.parse(localStorage.getItem(VIEW_KEY)||"null");
        return saved?.id===id?saved.view:null;
    }catch{return null;}
}

export class RigWizard {
    constructor(shell,options){
        this.shell=shell;
        this.options=options;
        this.browser=token();
        this.root=el("section",{class:"rig-workflow","aria-label":t("title")});
        this.content=el("div",{});
        this.note=el("p",{class:"rig-note",role:"status","aria-live":"polite"});
        this.choose=button(t("choose_mesh"),()=>this.shell.open('History'));
        appendContent(this.root,el("div",{class:"page-head"},
            el("div",{},el("h2",{},t("title")),hint(t("description"))),
            this.choose),this.note,this.content);
        this.event=e=>this.onEvent(e.detail);
        api.addEventListener(EVENT,this.event);
        this.stopLanguage=onLanguageChange(()=>this.viewport?.draw());
    }

    async init(){
        this.capabilities=await request("rigging/capabilities");
        const options=this.options;
        if(options.id||options.resume&&this.shell.node.properties.foundryRigging?.id){
            await this.open(await request(path(options.id||this.shell.node.properties.foundryRigging.id)));
        }else if(options.exportId){
            const record=await request("rigging/exports/"+options.exportId);
            await this.chooseRecord(record.record_id,record.sources.filter(x=>!options.variant||x.variant===options.variant));
        }else if(options.recordId){
            if(options.fileId)await this.create(options.recordId,options.fileId);
            else{
                const {sources}=await request("rigging/sources/"+options.recordId);
                await this.chooseRecord(options.recordId,sources.filter(x=>!options.variant||x.variant===options.variant));
            }
        }else await this.history();
        return this.root;
    }

    async chooseRecord(recordId,sources){
        sources ||= (await request("rigging/sources/"+recordId)).sources;
        if(sources.length===1)return this.create(recordId,sources[0].id);
        await this.history(sources.length?"from_history":"no_variant");
    }

    async history(message="from_history"){
        await this.shell.open("History");
        this.shell.message(t(message));
    }

    async create(record_id,file_id){
        await request("rigging/live",{browser:this.browser,prepare:true});
        const state=await request("rigging/runs",{record_id,file_id,browser:this.browser});
        await this.open(state);
    }

    async open(state){
        if(this.closed)return;
        this.viewport?.dispose();
        this.state=state;
        this.agentControls=new AgentControls((action,capability)=>request("rigging/live/control",{
            browser:this.browser,id:state.id,action,capability,
        }));
        const previous=this.shell.node.properties.foundryRigging;
        const savedView=storedView(state.id)||(previous?.id===state.id?previous.view:null);
        const property=this.shell.node.properties.foundryRigging={id:state.id,view:savedView};
        this.viewport=new RigViewport(data=>this.edit(data),name=>this.label(name),(drag,release)=>request("rigging/live/drag",{
            id:state.id,browser:this.browser,drag:drag.token,joint:drag.bone?.id||drag.joint,rig_revision:drag.rigRevision,release
        }));
        this.viewport.savedView=savedView;
        this.viewport.previewMirror=()=>this.mirror.checked;
        this.inspector=new RigInspector(this,token);
        const yieldCamera=()=>this.agentControls.humanCameraInput();
        for(const event of ["pointerdown","wheel"])
            this.viewport.element.addEventListener(event,yieldCamera,{capture:true,signal:this.viewport.events.signal});
        this.viewport.onCamera=view=>{
            property.view=view;
            try{localStorage.setItem(VIEW_KEY,JSON.stringify(property));}catch{}
        };
        this.viewport.weights=new WeightBrush(this.viewport,this.capabilities.weight_tools,
            ({points,options})=>this.edit({action:"weight_stroke",rigRevision:options.revision,bone_id:options.bone,
                points,mode:options.mode,radius:options.radius,strength:options.strength,target:options.target}),
            error=>setText(this.note,sourceMessage(error.message,error.i18n)),
            summary=>setText(this.weightSummary,summary?t("weight_summary",summary):""));
        this.source=el("p",{class:"rig-source"});
        this.joint=el("select",{"aria-label":t("joint"),onchange:e=>this.edit({action:"select",joint:e.target.value})});
        this.parts=el("details",{class:"rig-parts",open:true});
        this.authorMount=el("div",{});
        this.addPart=button(t("add_part"),()=>this.startPart());
        this.partKey=null;
        const step=(state.bounds[1][1]-state.bounds[0][1])/400;
        this.axes=["X","Y","Z"].map(axis=>el("input",{type:"number",step,value:0,"aria-label":t("axis",{axis})}));
        this.mirror=el("input",{type:"checkbox"});
        this.orientation=el("select",{"aria-label":t("direction")},
            ...[0,1,2,3].map(value=>el("option",{value},t("direction_"+value))));
        this.method=el("select",{"aria-label":t("method"),onchange:()=>this.showMethod()},
            ...["guided_template","local_ai"].map(value=>el("option",{value},t(value))));
        this.method.value=state.step==="build"&&this.capabilities.local_ai.supported_platform?"local_ai":state.fit.method;
        this.fitPresets=new RigPresets("ai_preset",this.capabilities.methods.local_ai,state.fit.preset,state.fit.settings);
        this.bindPresets=new RigPresets("bind_preset",this.capabilities.methods.binding,
            state.output?.binding_preset,state.output?.binding_settings);
        this.binder=el("select",{onchange:()=>this.refreshControls()},
            ...(this.capabilities.binding_methods||["voxel"]).map(value=>
                el("option",{value},t("bind_"+value))));
        this.binder.value=state.output?.binding_method||state.recommended_binding;
        this.methodHint=el("div",{});
        this.fitButton=button(t("fit_template"),()=>this.act(()=>this.fit()));
        this.cancel=button(t("cancel_fit"),()=>this.cancelFit());
        this.cancel.hidden=true;
        this.applied=el("p",{class:"rig-fit-receipt"});
        this.showMethod();
        this.undo=button(t("undo"),()=>this.edit({action:"undo"}));
        this.redo=button(t("redo"),()=>this.edit({action:"redo"}));
        this.moveChildren=el("input",{type:"checkbox"});
        this.reset=button(t("reset_joints"),()=>this.edit({action:"reset",orientation:Number(this.orientation.value)}));
        this.poses=Object.fromEntries(this.capabilities.poses.map(pose=>[pose,
            button(t("pose_"+pose),()=>this.edit({action:"pose",pose}))]));
        this.bind=button(t("bind"),()=>this.act(async()=>{
            const method=this.binder.value;
            const settings=method==="voxel"?this.bindPresets.payload():{};
            const job=await request(path(state.id)+"/bind-start",{revision:this.state.revision,request_id:token(),
                browser:this.browser,binding_method:method,...settings});
            await this.watchOperation('bind',job);
        }),{class:"primary"});
        this.cancelBind=button(t('cancel_bind'),()=>this.cancelOperation());
        this.cancelBind.hidden=true;
        this.save=button(t("save"),()=>this.act(async()=>{
            const result=await request(path(state.id)+"/export",{revision:this.state.revision,browser:this.browser});
            replaceContent(this.exportLink,el('a',{href:result.download,download:'',class:'download-link'},t("download")),
                button(msg("common.history"),()=>this.shell.open("History")));
            setText(this.note,t("saved"));
        }));
        this.openBlender=button(t("open_blender"),()=>this.act(async()=>{
            await request(path(state.id)+"/open-blender",{revision:this.state.revision,browser:this.browser});
            setText(this.note,t("opened_blender"));
        }));
        this.exportLink=el("div",{class:"actions"});
        this.front=button(t("front"),()=>this.viewport.orient("front"));
        this.side=button(t("side"),()=>this.viewport.orient("side"));
        this.rear=button(t("back_view"),()=>this.viewport.orient("back"));
        this.oblique=button(t("oblique"),()=>this.viewport.orient("oblique"));
        this.frameJoint=button(t("frame_joint"),()=>this.viewport.frameSelection());
        for(const control of [this.front,this.side,this.rear,this.oblique,this.frameJoint])
            control.addEventListener("click",()=>this.agentControls.humanCameraInput(),{capture:true});
        this.axis=el("select",{"aria-label":t("move_axis"),onchange:e=>{this.viewport.axis=e.target.value;this.viewport.draw();}},
            ...["free","X","Y","Z","XY","XZ","YZ"].map(axis=>el("option",{value:axis},axis==="free"?t("screen_plane"):axis)));
        this.localAxes=el("input",{type:"checkbox",onchange:e=>{this.viewport.localAxes=e.target.checked;this.viewport.draw();}});
        this.tools=Object.fromEntries(["orbit","select","move","orient","place","pose"].map(tool=>[tool,
            button(t("tool_"+tool),()=>{
                if(tool==="pose")return this.edit({action:"step",step:"review"});
                this.viewport.tool=tool;
                this.refreshControls();
                this.viewport.draw();
            })]));
        this.opacity=el("input",{type:"range",min:.15,max:1,step:.05,value:1,
            oninput:e=>this.viewport.setOpacity(e.currentTarget.valueAsNumber)});
        const coords=el("div",{class:"rig-axis-fields"},...this.axes.map((input,index)=>
            el("label",{},["X","Y","Z"][index],input)));
        const adjust=button(t("apply_joint"),()=>this.edit({action:"move",joint:this.state.selected_joint,
            point:this.axes.map(input=>input.value===""?null:input.valueAsNumber)}));
        this.roll=el("input",{type:"number",min:-180,max:180,step:1,value:0});
        this.applyRoll=button(t("apply_roll"),()=>this.edit({action:"orient",bone_id:this.selectedBone()?.id,
            roll:this.roll.valueAsNumber*Math.PI/180}));
        this.lockBone=button(t("lock_bone"),()=>this.edit({action:"lock",bone_id:this.selectedBone()?.id,
            locked:!this.selectedBone()?.locked}));
        this.boneParent=el("select",{});
        this.partner=el("select",{});
        this.boneLabel=el("input",{type:"text",maxLength:100});
        this.role=el("select",{onchange:()=>{this.digitField.hidden=this.role.value!=="finger";}},
            ...(this.capabilities.roles||[]).map(role=>el("option",{value:role},role)));
        this.digit=el("select",{},el("option",{value:""},t("bone_none")),
            ...["thumb","index","middle","ring","little"].map(digit=>el("option",{value:digit},t("digit_"+digit))));
        this.digitField=field(t("digit"),this.digit);
        this.plane=el("select",{},...["x","y","z"].map(axis=>el("option",{value:axis},axis.toUpperCase())));
        this.plane.value=state.orientation%2?"z":"x";
        this.mirrorCenter=el("input",{type:"number",step:"any",placeholder:"—"});
        const selected=(action,fields)=>this.edit({action,bone_id:this.selectedBone()?.id,...fields});
        const plane=()=>({axis:this.plane.value,center:this.mirrorCenter.value===""?undefined:this.mirrorCenter.valueAsNumber});
        this.anatomicalSide=el("select",{},el("option",{value:""},t("bone_none")),
            el("option",{value:"L"},t("spatial_anatomy_left")),el("option",{value:"R"},t("spatial_anatomy_right")));
        this.topologyPanel=el("details",{},el("summary",{},t("bone_structure")),
            field(t("bone_label"),this.boneLabel),button(t("save_bone_label"),()=>selected("label",{label:this.boneLabel.value})),
            field(t("bone_role"),this.role),this.digitField,
            button(t("save_bone_role"),()=>selected("role",{role:this.role.value,
                ...(this.role.value==="finger"?{digit:this.digit.value||null}:{})})),
            field(t("spatial_anatomy_side"),this.anatomicalSide),
            button(t("spatial_apply"),()=>selected("side",{side:this.anatomicalSide.value||null})),
            field(t("bone_attachment"),this.boneParent),button(t("reattach_bone"),()=>selected("reparent",{parent_id:this.boneParent.value||null})),
            field(t("mirror_axis"),this.plane),field(t("mirror_center"),this.mirrorCenter),
            field(t("mirror_partner"),this.partner),button(t("save_mirror_pair"),()=>selected("pair",{other:this.partner.value||null,...plane()})),
            button(t("mirror_chain"),()=>this.inspector.review([{action:"mirror_chain",args:{bone_id:this.selectedBone()?.id,...plane()}}])),
            button(t("remove_chain"),()=>selected("remove_chain",{})));
        this.weightHeat=el("input",{type:"checkbox",onchange:()=>this.refreshWeights()});
        this.weightBone=el("select",{onchange:()=>this.refreshWeights()});
        this.weightMode=el("select",{onchange:()=>this.refreshWeights()},
            ...(this.capabilities.weight_modes||[]).map(mode=>el("option",{value:mode},t("weight_"+mode))));
        const span=Math.hypot(...state.bounds[0].map((value,i)=>state.bounds[1][i]-value));
        this.weightRadius=el("input",{type:"number",min:.000001,max:span*.2,step:"any",value:span*.03,
            oninput:()=>this.refreshWeights()});
        this.weightStrength=el("input",{type:"range",min:0,max:1,step:.05,value:.65,oninput:()=>this.refreshWeights()});
        this.weightTarget=el("input",{type:"range",min:0,max:1,step:.05,value:1,oninput:()=>this.refreshWeights()});
        this.weightLock=button(t("weight_lock"),()=>{
            const bone_id=this.weightBone.value;
            return this.edit({action:"weight_lock",bone_id,locked:!this.state.weight_locks?.includes(bone_id)});
        });
        this.weightStatus=el("p",{"aria-live":"polite"});
        this.weightSummary=el("p",{"aria-live":"polite"});
        this.weightPanel=el("details",{},el("summary",{},t("weights")),this.weightStatus,
            field(t("weight_heat"),this.weightHeat),field(t("weight_bone"),this.weightBone),this.weightSummary,this.weightLock,
            field(t("weight_brush"),this.weightMode),field(t("weight_radius"),this.weightRadius),
            field(t("weight_strength"),this.weightStrength),field(t("weight_target"),this.weightTarget),
            hint(t("weight_help")),el("div",{class:"actions"},
                button(t("undo"),()=>this.edit({action:"undo"})),button(t("redo"),()=>this.edit({action:"redo"}))));
        this.fitControls=[this.joint,...this.axes,adjust,this.mirror,this.orientation,this.method,this.fitButton,
            this.fitPresets.element,this.reset,this.moveChildren,this.axis,this.roll,this.applyRoll,this.lockBone];
        this.stepButtons=Object.fromEntries(STEPS.map((step,index)=>[step,
            button(t('step_'+step),()=>this.edit({action:'step',step}),{'data-step':step})]));
        this.panels={
            build:el('section',{'aria-label':t('step_build')},
                el('h3',{},t('step_build')),this.applied,
                el("div",{class:"rig-method-fields"},field(t("method"),this.method),field(t("direction"),this.orientation)),
                this.methodHint,this.fitPresets.element,el("div",{class:"actions"},this.fitButton)),
            fit:el('section',{'aria-label':t('step_fit')},
                el('h3',{},t('step_fit')),hint(t('help_fit')),field(t('joint'),this.joint),
                field(t("move_axis"),this.axis),el('label',{class:'check-row'},this.localAxes,t("spatial_local_axes")),
                el('label',{class:'check-row'},this.mirror,t('mirror')),
                el('label',{class:'check-row'},this.moveChildren,t('move_children')),
                el('details',{},el('summary',{},t('coordinates')),coords,adjust),
                el('details',{},el('summary',{},t('bend_direction')),field(t('roll_degrees'),this.roll),this.applyRoll),
                el('div',{class:'actions'},this.undo,this.redo,this.lockBone),this.inspector.element,this.topologyPanel,
                el('details',{},el('summary',{},t('guided_template')),this.reset),hint(t('edit_hint'))),
            review:el('section',{'aria-label':t('step_review')},
                el('h3',{},t('step_review')),hint(t('help_review')),field(t('bind_method'),this.binder),this.bindPresets.element,
                el('div',{class:'actions'},this.bind),
                el('div',{class:'actions rig-pose-actions'},...Object.values(this.poses)),this.inspector.movement,this.weightPanel),
            export:el('section',{'aria-label':t('step_export')},
                el('h3',{},t('step_export')),hint(t('help_export')),
                el('div',{class:'actions'},this.save,this.openBlender),this.exportLink)
        };
        this.back=button(t('back'),()=>this.navigate(-1));
        this.next=button(t('next'),()=>this.navigate(1),{class:'primary'});
        this.stepStatus=el('p',{class:'rig-step-status','aria-live':'polite'});
        this.toolHint=hint(t('tool_move_hint'));
        replaceContent(this.content,this.agentControls.element,this.source,el('div',{class:'actions'},this.cancel,this.cancelBind),
            el('nav',{class:'rig-steps','aria-label':t('wizard_steps')},...Object.values(this.stepButtons)),
            el('div',{class:'rig-workbench'},
                this.parts,
                el('div',{class:'rig-view-column'},el('div',{class:'actions'},this.front,this.side,this.rear,this.oblique,this.frameJoint),this.viewport.element,this.inspector.previewPanel,
                    field(t('mesh_opacity'),this.opacity),
                    el('div',{class:'actions rig-tools','aria-label':t('viewport_tools')},...Object.values(this.tools)),this.toolHint),
                el('aside',{class:'rig-sidebar'},...Object.values(this.panels))),
            el('div',{class:'rig-navigation'},this.back,this.stepStatus,this.next));
        await this.update(state);
        if(this.closed)return;
        const lease=await request("rigging/live",{id:state.id,browser:this.browser,opened:true});
        this.agentControls.update(lease.agent_control);
        if(this.closed){this.endLive();return;}
        clearInterval(this.heartbeat);
        this.heartbeat=setInterval(()=>request("rigging/live",{id:state.id,browser:this.browser})
            .then(lease=>{if(!this.closed&&this.state.id===state.id)this.agentControls.update(lease.agent_control);})
            .catch(()=>{}),12000);
        // Reopening watches the existing worker; it never resubmits a job.
        const [fit,bind]=await Promise.all([request(path(state.id)+'/fit'),request(path(state.id)+'/bind-status')]);
        if(fit.status==='running')void this.act(()=>this.watchOperation('fit',fit));
        else if(bind.status==='running')void this.act(()=>this.watchOperation('bind',bind));
    }

    async update(state){
        if(this.closed||!this.viewport||this.state.id!==state.id||state.revision<this.state.revision)return;
        const reorient=state.orientation!==this.state.orientation;
        if(state.rig_revision!==this.state.rig_revision)this.clearAgentPreview();
        if(state.recommended_binding!==this.state.recommended_binding){
            this.binder.value=state.recommended_binding;
        }
        this.state=state;
        this.agentControls.update(state.agent_control);
        if(this.author&&this.author.revision!==state.rig_revision)this.endPart();
        this.root.dataset.rigId=state.id;
        this.root.dataset.rigRevision=String(state.revision);
        this.root.dataset.rigPose=state.pose;
        this.root.dataset.rigFit=state.fit.method;
        this.root.dataset.rigStep=state.step||'fit';
        setText(this.applied,t("current_fit",{method:t(state.fit.method)}));
        setText(this.source,t("source",{asset:state.source.asset_name,file:state.source.name}));
        this.refreshParts();
        this.joint.value=state.selected_joint;
        this.orientation.value=state.orientation;
        this.axes.forEach((field,index)=>{field.value=Number(state.joints[state.selected_joint][index].toFixed(6));});
        this.roll.value=(this.selectedBone()?.roll||0)*180/Math.PI;
        const selected=this.selectedBone();
        this.boneLabel.value=selected?.label||"";
        this.boneParent.value=selected?.parent_id||"";
        this.partner.value=selected?.mirror_id||"";
        this.role.value=selected?.role||"other";
        this.anatomicalSide.value=selected?.side||"";
        this.digit.value=selected?.anatomical_name||"";
        this.digitField.hidden=this.role.value!=="finger";
        setText(this.lockBone,t(this.selectedBone()?.locked?"unlock_bone":"lock_bone"));
        this.refreshControls();
        await this.viewport.show(state,this.capabilities.viewer);
        if(this.closed||this.state!==state)return;
        this.inspector.update(state);
        this.refreshWeights();
        if(reorient&&this.viewport)this.viewport.orient(this.viewport.view);
    }

    label(name){
        const bone=this.state?.skeleton?.bones.find(item=>item.id===name||item.id+"/tip"===name);
        if(!bone||bone.legacy_tip&&bone.label===bone.id)return jointLabel(name);
        if(name.endsWith("/tip"))return t("bone_tip",{bone:bone.label});
        return bone.landmark_label&&bone.label.startsWith("Bone ")?jointLabel(bone.landmark_label):bone.label;
    }

    selectedBone(){
        const id=this.state.selected_joint;
        const bones=this.state.skeleton?.bones||[];
        return bones.find(bone=>bone.id===id)||bones.find(bone=>bone.id+"/tip"===id||bone.legacy_tip===id);
    }

    refreshParts(){
        const bones=this.state.skeleton?.bones||[];
        const groups=new Map();
        for(const bone of bones){
            const part=bone.part_id||"body";
            if(!groups.has(part))groups.set(part,[]);
            groups.get(part).push(bone);
        }
        const joints=Object.keys(this.state.joints);
        const structure=JSON.stringify([bones.map(bone=>[bone.id,bone.label,bone.part_id]),joints]);
        if(this.partKey===structure)return;
        this.partKey=structure;
        replaceContent(this.joint,...joints.map(name=>el("option",{value:name},this.label(name))));
        for(const field of [this.boneParent,this.partner])replaceContent(field,el("option",{value:""},t("bone_none")),
            ...bones.map(bone=>el("option",{value:bone.id},this.label(bone.id))));
        const previousBone=this.weightBone.value;
        replaceContent(this.weightBone,...bones.filter(bone=>bone.deform!==false)
            .map(bone=>el("option",{value:bone.id},this.label(bone.id))));
        if(bones.some(bone=>bone.id===previousBone))this.weightBone.value=previousBone;
        else if(this.selectedBone())this.weightBone.value=this.selectedBone().id;
        const list=[button(t("whole_rig",{count:bones.length}),()=>this.viewport.frame())];
        for(const [name,part] of groups){
            const type=part[0].part_type;
            const label=name==="body"?t("part_body"):type==="hand"&&part[0].side?
                t(part[0].side==="L"?"part_left_hand":"part_right_hand"):t("part_"+type);
            list.push(el("details",{class:"rig-part"},
                el("summary",{},t("part_count",{part:label,count:part.length})),
                button(t("frame_part"),()=>this.viewport.frame(part.flatMap(bone=>[bone.id,bone.legacy_tip||bone.id+"/tip"]))),
                ...part.map(bone=>button(this.label(bone.id),()=>this.edit({action:"select",joint:bone.id}),
                    {"data-bone":bone.id}))));
        }
        replaceContent(this.parts,el("summary",{},t("parts")),this.addPart,this.authorMount,...list);
    }

    startPart(){
        const parent=this.selectedBone();
        if(!parent||this.busy)return;
        this.endPart();
        const revision=this.state.rig_revision,id=this.state.id;
        this.author=new PartAuthor(this.viewport,parent,revision,args=>request(path(id)+"/part-preview",{
            ...args,rig_revision:revision
        }),command=>{
            if(command)this.edit(command);
            else this.endPart();
        });
        this.authorMount.append(this.author.element);
    }

    endPart(){
        this.author?.dispose();
        this.author=null;
        this.authorMount?.replaceChildren();
    }

    refreshControls(){
        this.choose.disabled=Boolean(this.busy);
        if(!this.viewport||!this.state)return;
        const state=this.state;
        const step=state.step||'fit',index=STEPS.indexOf(step);
        this.parts.hidden=step!=="fit";
        this.parts.parentElement?.classList.toggle("rig-with-parts",step==="fit");
        this.viewport.locked=Boolean(this.busy)||step!=='fit';
        for(const [name,panel] of Object.entries(this.panels))panel.hidden=name!==step;
        for(const [name,control] of Object.entries(this.stepButtons)){
            control.disabled=Boolean(this.busy)||(name==='export'&&!state.bound);
            if(name===step)control.setAttribute('aria-current','step');else control.removeAttribute('aria-current');
        }
        this.back.disabled=Boolean(this.busy)||index===0;
        this.next.hidden=index===STEPS.length-1;
        this.next.disabled=Boolean(this.busy)||(step==='review'&&!state.bound);
        setText(this.stepStatus,t('step_count',{current:index+1,total:STEPS.length}));
        setText(this.next,t(step==='build'?'next_fit':step==='fit'?'next_review':'next_export'));
        for(const [tool,control] of Object.entries(this.tools)){
            control.hidden=step!=='fit'&&tool!=='orbit';
            control.disabled=Boolean(this.busy);
            control.setAttribute('aria-pressed',String((step==='fit'?this.viewport.tool:'orbit')===tool));
        }
        setText(this.toolHint,t('tool_'+(step==='fit'?this.viewport.tool:'orbit')+'_hint'));
        for(const control of this.fitControls)control.disabled=Boolean(this.busy)||state.pose!=="rest";
        if(this.method.value==="local_ai"&&!this.capabilities.local_ai.supported_platform)this.fitButton.disabled=true;
        this.bind.disabled=Boolean(this.busy)||state.pose!=="rest";
        this.binder.disabled=this.bind.disabled;
        for(const option of this.binder.options){
            option.disabled=option.value==="learned"?state.recommended_binding!=="learned":
                option.value==="conditioned"&&!this.capabilities.local_ai.supported_platform;
        }
        this.bindPresets.element.hidden=this.binder.value!=="voxel";
        this.bindPresets.element.disabled=this.bind.disabled;
        this.undo.disabled=Boolean(this.busy)||!state.undo_available;
        this.redo.disabled=Boolean(this.busy)||!state.redo_available;
        this.roll.disabled=this.applyRoll.disabled=Boolean(this.busy)||!this.selectedBone()||!!this.selectedBone()?.locked;
        this.lockBone.disabled=Boolean(this.busy)||!this.selectedBone();
        for(const control of this.topologyPanel.querySelectorAll("button,input,select"))
            control.disabled=Boolean(this.busy)||!this.selectedBone()||!!this.selectedBone()?.locked;
        this.addPart.disabled=Boolean(this.busy)||!this.selectedBone()||!!this.selectedBone()?.locked;
        this.save.disabled=this.openBlender.disabled=Boolean(this.busy)||!state.bound;
        for(const [pose,control] of Object.entries(this.poses)){
            control.hidden=state.bound&&!(pose in (state.output?.report?.pose_seconds||{}));
            control.disabled=Boolean(this.busy)||!state.bound;
            control.setAttribute("aria-pressed",String(state.pose===pose));
        }
        this.refreshWeights();
    }

    refreshWeights(){
        if(!this.weightPanel||!this.state)return;
        const state=this.state,bone=this.weightBone.value;
        const available=!!(this.capabilities.weight_tools&&state.weight_preview_url);
        const locked=state.weight_locks?.includes(bone);
        this.weightPanel.hidden=!this.capabilities.weight_tools;
        this.weightHeat.disabled=!available;
        this.weightLock.disabled=!available||this.busy||!bone;
        setText(this.weightLock,t(locked?"weight_unlock":"weight_lock"));
        const count=state.output?.report?.weight_corrections?.changed_vertices??0;
        setText(this.weightStatus,t(!available?"weight_needs_bind":state.bound?"weight_current":"weight_stale",{count}));
        const withinRadius=this.weightRadius.validity.valid&&this.weightRadius.valueAsNumber>0;
        void this.viewport.weights.show(available&&this.weightHeat.checked&&state.step==="review"?
            {bone,revision:state.rig_revision,paint:!this.busy&&state.pose==="rest"&&!locked&&withinRadius,
                mode:this.weightMode.value,maxPoints:this.capabilities.weight_points,
                radius:this.weightRadius.valueAsNumber,strength:this.weightStrength.valueAsNumber,
                target:this.weightTarget.valueAsNumber}:null);
    }

    navigate(direction){
        const step=STEPS[STEPS.indexOf(this.state.step||'fit')+direction];
        if(step)return this.edit({action:'step',step});
    }

    showMethod(){
        const ai=this.method.value==="local_ai";
        this.fitPresets.element.hidden=!ai;
        replaceContent(this.methodHint,ai?setupHint(this.capabilities.local_ai):hint(t("guided_hint")));
        setText(this.fitButton,ai?t("predict_joints"):t("fit_template"));
        if(this.bind)this.refreshControls();
    }

    async fit(){
        const run=this.state;
        const base=path(run.id)+"/fit";
        const payload={revision:run.revision,browser:this.browser,method:this.method.value,orientation:Number(this.orientation.value)};
        if(payload.method==="guided_template"){
            await this.update(await request(base,payload));
            return;
        }
        const job=await request(base,{...payload,...this.fitPresets.payload(),request_id:token()});
        await this.watchOperation('fit',job);
    }

    async watchOperation(kind,job){
        const runId=this.state.id;
        const control=kind==='fit'?this.cancel:this.cancelBind;
        this.operation={kind,requestId:job.request_id};
        control.hidden=false;
        try{
            while(!this.closed&&job.status==="running"){
                const phase=job.phase;
                setText(this.note,t(kind==="fit"||["software","models","predicting"].includes(phase)?"fit_"+phase:"binding"));
                await new Promise(resolve=>setTimeout(resolve,800));
                if(!this.closed)job=await request(path(runId)+(kind==='fit'?'/fit':'/bind-status'));
            }
            if(this.closed)return;
            await this.update(await request(path(runId)));
            if(job.status==='cancelled'){setText(this.note,t('operation_cancelled'));return;}
            if(job.status!=="complete")throw Error(job.error||String(t('operation_interrupted')));
            if(kind==='fit'){
                this.capabilities=await request("rigging/capabilities");
                this.showMethod();
                setText(this.note,t("fit_review"));
            }else setText(this.note,t('bound_status',{bones:this.state.output.report.bones}));
        }finally{
            this.operation=null;
            control.hidden=true;
            control.disabled=false;
        }
    }

    cancelFit(){return this.cancelOperation();}

    async cancelOperation(){
        if(!this.operation)return;
        const {kind,requestId}=this.operation;
        const control=kind==='fit'?this.cancel:this.cancelBind;
        control.disabled=true;
        try{
            await request(path(this.state.id)+'/'+kind+'-cancel',{request_id:requestId,browser:this.browser});
        }catch(error){
            control.disabled=false;
            setText(this.note,sourceMessage(error.message,error.i18n));
        }
    }

    edit(data){
        return this.act(async()=>{
            const {action,revision,rigRevision,drag,dragError,...args}=data;
            if(dragError)throw dragError;
            if(action==="move"){
                args.mirror=this.mirror.checked;
                args.move_children=this.moveChildren.checked;
                if(args.mirror&&!drag){
                    if(rigRevision!==undefined&&rigRevision!==this.state.rig_revision)
                        throw Error(t("spatial_stale").toString());
                    await this.inspector.previewEdits([{action,args}]);
                    return;
                }
            }
            try{
                const endpoint=path(this.state.id);
                const response=COMMANDS.has(action)?
                    await request(endpoint+"/command",{rig_revision:rigRevision??this.state.rig_revision,browser:this.browser,drag,
                        request_id:token(),action,args}):
                    await request(endpoint+"/edit",{revision:revision??this.state.revision,browser:this.browser,action,...args});
                await this.update(response);
            }
            catch(error){
                if(error.code==="FOUNDRY_HTTP_409")await this.update(await request(path(this.state.id)));
                throw error;
            }
        });
    }

    async onEvent(event){
        if(this.closed||!this.viewport||event?.id!==this.state?.id)return;
        if(event.action==="agent-control"){
            this.agentControls.update(event.agent_control);
            if(!event.agent_control.enabled)this.clearAgentPreview();
        }
        if(event.action==="agent-preview"&&event.rig_revision===this.state.rig_revision&&
            this.agentControls.state?.enabled&&!this.agentControls.pending&&!this.viewport.drag){
            this.clearAgentPreview();
            this.agentPreview=event.preview_id;
            this.viewport.agentGhost=event.bones;
            this.agentControls.showActivity("agent_preview",{count:event.count});
            this.viewport.draw();
            this.agentPreviewTimer=setTimeout(()=>this.clearAgentPreview(),120000);
        }
        if(event.action==="agent-preview-ended"&&event.preview_id===this.agentPreview)this.clearAgentPreview();
        if(event.action==="operation"&&event.actor==="agent"){
            this.clearAgentPreview();
            this.agentControls.showActivity(event.kind==="bind"?"agent_binding":"agent_fitting");
        }
        if(event.action==='operation'&&!this.busy){
            void this.act(()=>this.watchOperation(event.kind,event.job));
        }
        if(event.action==="changed"&&event.revision>this.state.revision){
            try{
                await this.update(await request(path(event.id)));
                if(event.actor==="agent"&&!this.agentPreview&&this.state.revision===event.revision){
                    const part=this.label(event.joint);
                    switch(event.operation){
                        case "view": this.agentControls.showActivity("agent_view_requested"); break;
                        case "step": this.agentControls.showActivity("agent_step",{step:t("step_"+this.state.step)}); break;
                        case "pose":
                        case "pose_joint": this.agentControls.showActivity("agent_pose"); break;
                        case "select": this.agentControls.showActivity("agent_selected",{part}); break;
                        default: this.agentControls.showActivity("agent_applied",{part});
                    }
                    if(this.agentControls.following&&!this.viewport.drag){
                        if(event.view==="part"||!event.view)this.viewport.frameSelection();
                        else if(event.view!=="current")this.viewport.orient(event.view);
                    }
                }
            }
            catch(error){setText(this.note,sourceMessage(error.message));}
        }
        if(event.action==="capture"&&event.browser===this.browser){
            try{
                if(event.revision!==this.state.revision)await this.update(await request(path(event.id)));
                if(event.revision!==this.state.revision)return;
                const captured=await this.viewport.capture(event.view,this.capabilities.spatial_tools);
                if(!this.closed)await request("rigging/live/capture-result",
                    {...captured,browser:this.browser,token:event.token,revision:event.revision});
            }catch(error){setText(this.note,sourceMessage(error.message));}
        }
        if(event.action==="probe"&&event.browser===this.browser){
            const identity={browser:this.browser,token:event.token};
            let result;
            try{result={probes:await this.viewport.probe(event.observation,event.pixels,this.capabilities.spatial_tools)};}
            catch{result={failed:true};}
            if(!this.closed)await request("rigging/live/probe-result",{...identity,...result}).catch(()=>{});
        }
        if(event.action==="measure"&&event.browser===this.browser){
            let result;
            try{
                if(event.identity.revision!==this.state.revision)
                    await this.update(await request(path(event.id)));
                await this.viewport.loading;
                result={metrics:this.viewport.measure(event.identity,event.selection,event.pose)};
            }
            catch{result={failed:true};}
            if(!this.closed)await request("rigging/live/measure-result",{
                ...result,browser:this.browser,token:event.token,
            }).catch(()=>{});
        }
    }

    clearAgentPreview(){
        clearTimeout(this.agentPreviewTimer);
        this.agentPreview=null;
        if(this.viewport?.agentGhost){
            this.viewport.agentGhost=null;
            this.viewport.draw();
        }
    }

    async act(work){
        if(this.closed||this.busy)return;
        this.busy=true;
        this.root.setAttribute("aria-busy","true");
        this.refreshControls();
        try{setText(this.note,"");await work();}
        catch(error){setText(this.note,sourceMessage(error.message,error.i18n));}
        finally{this.busy=false;this.root.setAttribute("aria-busy","false");this.refreshControls();}
    }

    endLive(){
        clearInterval(this.heartbeat);
        if(this.state)request("rigging/live",{browser:this.browser,closed:true}).catch(()=>{});
    }

    dispose(){
        this.closed=true;
        this.clearAgentPreview();
        this.endLive();
        this.endPart();
        this.agentControls?.dispose();
        this.viewport?.dispose();
        this.stopLanguage();
        api.removeEventListener(EVENT,this.event);
    }
}
