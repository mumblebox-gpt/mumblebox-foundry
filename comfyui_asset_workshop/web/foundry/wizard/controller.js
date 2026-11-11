import {sourceMessage} from "../i18n.js";
import {msg, setText, appendContent} from "../i18n.js";
import {api} from "/scripts/api.js";
import {el,button,hint} from "../dom.js";
import {request} from "../services.js";
import {dialog} from "../dialogs.js";
import {modelAccessError} from "../connection-help.js";
import {referenceFilename,syncWizardGraph,syncWizardOutputs,wizardStateKey,clearWizardState,savedWizardState,savedSingleWizardState,rememberPreviousSession} from "../graph-adapter.js";
import {initialState,copyRunConfiguration} from "./session.js";
import {exportChoices,validateExports} from "./export-choices.js";
import {FIRST_USE_MESSAGE} from "../activity-state.js";
import {overallProgress} from "../overall-progress.js";
import {elapsedTime} from "../activity.js";
import {inputPage,reviewPage,optionsPage,finishingPage,resultPage} from "./pages.js";
import {singleInputPage,singleOptionsPage} from '../single/pages.js';
import {syncSingleGraph,syncSingleOutputs} from '../single/graph.js';
const singleTitles=[msg("mesh.your_starting_image"),msg("mesh.mesh_and_refinement"),msg("mesh.refined_mesh_and_exports"),msg("mesh.your_asset_package")];
const clone=value=>JSON.parse(JSON.stringify(value));
const titles=[msg("mesh.your_starting_images"),msg("mesh.review_the_four_views"),msg("mesh.mesh_and_refinement"),msg("mesh.refined_mesh_and_exports"),msg("mesh.your_asset_package")];
const stepLabels=[msg("mesh.starting_images"),msg("mesh.four_views"),msg("mesh.mesh_settings"),msg("mesh.refine_export"),msg("mesh.asset_package")];
const singleStepLabels=[msg("mesh.starting_image"), ...stepLabels.slice(2)];
const stepDescriptions=[msg("mesh.references_and_image_model"),msg("mesh.review_the_turnaround"),msg("mesh.detail_and_refinement_controls"),msg("mesh.preview_and_output_choices"),msg("mesh.files_and_production_record")];
const stageNames={turnaround:msg("mesh.qwen_image_2_1_creating_four_views"),geometry:msg("mesh.pixal3d_trellis_2_building_the_initial_mesh"),
 refinement:msg("mesh.hi3d_refining_and_cleaning_the_geometry"),texture:msg("mesh.trellis_2_texturing_the_finished_geometry"),
 balanced:msg("mesh.baking_the_balanced_game_mesh"),compact:msg("mesh.baking_the_compact_game_mesh"),quads:msg("mesh.retopology_uvs_and_detail_baking"),
 print:msg("mesh.preparing_and_measuring_the_print_mesh"),package:msg("mesh.writing_exports_readme_and_zip"),cleanup:msg("mesh.releasing_models_and_temporary_work")};
export class Wizard {
    constructor(shell,{resume=false,runId=null,method="turnaround"}={}) {
        this.shell=shell;this.node=shell.node;this.page=1;this.disposed=false;this.previewDispose=null;
        this.method=method;this.single=method==="single-image";
        const saved=this.single?clone(savedSingleWizardState(this.node)):savedWizardState(this.node);
        if(!resume&&!this.single)rememberPreviousSession(this.node);
        const state=initialState(saved,resume);
        this.draft=state.draft;if(this.single)this.draft.method=method;this.sessionId=state.sessionId||crypto.randomUUID();
        this.draft.turnaround_model??="qwen21";
        this.runId=state.runId;this.page=state.page;
        this.agentRunId=runId;
        if(runId)this.runId=runId;
        this.host=el("section",{class:"wizard","aria-label":msg("mesh.image_to_3d_wizard")});
        this.progressHandler=e=>{
            if(!this.run?.active||e.detail?.prompt_id&&e.detail.prompt_id!==this.run.pending?.prompt_id)return;
            const value=e.detail?.value,max=e.detail?.max;
            if(Number.isFinite(value)&&max>0&&this.sampleProgress)setText(this.sampleProgress, msg("mesh.current_step_of", {value1: value, max: max}));
            if(Number.isFinite(value)&&max>0)this.updateOverall(value/max);
        };
        api.addEventListener("progress",this.progressHandler);
    }
    async init(){
        this.cap=await request("wizard/capabilities");
        if(this.single)this.cap={...this.cap,defaults:this.cap.single_defaults};
        this.draft.selection??=structuredClone(this.cap.selection);
        this.draft.profile=this.shell.data?.preferences?.profile||"default";
        if(this.runId){
            try{
                this.run=await request("wizard/runs/"+this.runId);
                if(this.agentRunId){
                    const r=this.run;
                    this.draft=copyRunConfiguration(this.draft,r);
                    this.page=this.single?(r.operation==='rocket'||r.package?4:r.completed.includes('refinement')?3:2):r.operation==="rocket"||r.package?5:r.completed.includes("refinement")?4:r.completed.includes("turnaround")?2:1;
                    if(this.single)syncSingleGraph(await request('wizard/single-template'),this.node,r);
                    else {const branch=await request("wizard/runs/"+this.runId+"/turnaround-graph");syncWizardGraph(r,this.node,branch);}
                    this.remember();
                }
                this.applyRun();
            }
            catch(error){this.error=error.message;this.runId=null;this.page=1;}
        }
        this.shell.message(msg("mesh.local_workspace_image_to_3d_workflow"));
        this.render();this.poll();
        return this.host;
    }
    remember(){
        const state={page:this.page,draft:clone(this.draft),runId:this.runId,sessionId:this.sessionId};
        this.node.properties[this.single?'foundrySingle':'foundryWizard']=state;
        localStorage.setItem(wizardStateKey()+(this.single?':single':''),JSON.stringify(state));
        this.node.graph?.change?.();
    }
    applyRun(){
        if(this.single)syncSingleOutputs(this.run.outputs,this.node);else syncWizardOutputs(this.run.outputs,this.node);
        if(!this.run.geometry_audit&&this.run.outputs?.["2015"]?.text?.[0]){
            try{this.run.geometry_audit=JSON.parse(this.run.outputs["2015"].text[0]);}catch{}
        }
        if(this.run.status==="complete")this.error="";
        else if(this.run.error)this.error=this.run.error;
    }
    async poll(){
        if(this.disposed)return;
        try{
            if(this.runId){
                const current=await request("wizard/runs/"+this.runId);
                if(this.disposed)return;
                const changed=JSON.stringify([current.status,current.active,current.stage,current.pending?.prompt_id,current.events?.at(-1),current.dependency?.name,current.dependency?.phase])!==
                    JSON.stringify([this.run?.status,this.run?.active,this.run?.stage,this.run?.pending?.prompt_id,this.run?.events?.at(-1),this.run?.dependency?.name,this.run?.dependency?.phase]);
                this.run=current;
                this.updateOverall();
                if(changed){this.applyRun();this.render();}
                if(current.dependency&&this.sampleProgress){
                    const d=current.dependency;
                    setText(this.sampleProgress, [d.name,d.phase,d.total?Math.round((d.bytes||0)/d.total*100)+"%":""].filter(Boolean).join(" · "));
                }
            }
        }catch(error){if(!this.disposed)this.shell.message(sourceMessage(error.message),true);}
        if(!this.disposed)this.timer=setTimeout(()=>this.poll(),1800);
    }
    async act(fn){
        if(this.working)return;
        this.working=true;this.error="";
        try{await fn();this.shell.message(msg("mesh.local_workspace_image_to_3d_workflow"));}
        catch(error){this.error=error.message;this.shell.message(sourceMessage(error.message),true);}
        finally{this.working=false;if(!this.disposed)this.render();}
    }
    async save(){
        const data=clone(this.draft);
        this.run=await request(this.runId?"wizard/runs/"+this.runId:"wizard/runs",data,this.runId?{method:"PATCH"}:{});
        this.runId=this.run.id;this.remember();
        if(this.single)syncSingleGraph(await request('wizard/single-template'),this.node,this.run);
        else {const branch=await request("wizard/runs/"+this.runId+"/turnaround-graph");syncWizardGraph(this.run,this.node,branch);}
    }
    async start(operation){
        await this.save();
        this.run=await request("wizard/runs/"+this.runId+"/start",{operation,client_id:api.clientId||"",request_id:crypto.randomUUID()});
        this.page=this.single?(operation==="mesh"?3:4):operation==="turnaround"?2:operation==="mesh"?4:5;
        this.remember();this.render();
    }
    go(page){this.page=page;this.remember();this.render();this.shell.content.scrollTop=0;}
    quadChoice(overrides=this.draft.overrides){
        const remember=()=>{if(overrides===this.draft.overrides)this.remember();};
        return {
            methods:this.cap.quad_methods||[], value:overrides.quad_method||this.cap.defaults.quad_method||"quadriflow",
            controls:this.cap.quad_options||{}, name:"foundry-quad-"+this.sessionId,
            change:value=>{overrides.quad_method=value;remember();},
            getOption:(group,id,fallback)=>overrides.quad_options?.[group]?.[id]??fallback,
            setOption:(group,id,value)=>{
                const options=overrides.quad_options??={};
                (options[group]??={})[id]=value;
                remember();
            },
        };
    }
    rocket(){
        const selection=structuredClone(this.draft.selection);
        const overrides=structuredClone(this.draft.overrides);
        const quad=this.quadChoice(overrides);
        quad.name+="-rocket";
        const error=el("p",{class:"error-panel",role:"alert",hidden:true});
        dialog(this.shell,msg("mesh.finish_this_asset_with_rocket_mode"),el("div",{class:"rocket-confirmation"},
            hint(msg("mesh.continue_from_this_point_using_your_current_settings_saved_unchanged_stages")),
            exportChoices(this.cap.exports,selection,undefined,quad),error),[
            {label:msg("mesh.keep_working_manually"),run:close=>close()},
            {label:msg("mesh.start_rocket_mode"),primary:true,run:close=>{
                try{validateExports(selection,quad);}catch(e){setText(error, sourceMessage(e.message));error.hidden=false;return;}
                this.draft.overrides=overrides;this.draft.selection=selection;this.remember();close();this.act(()=>this.start("rocket"));
            }}]);
    }
    confirmReset(){
        dialog(this.shell,msg("mesh.start_over"),hint(msg("mesh.return_to_workflow_selection_your_saved_images_meshes_and_packages_will_rema")),
            [{label:msg("mesh.keep_working"),run:close=>close()},{label:msg("mesh.start_over_2"),primary:true,run:close=>{
                close();if(this.single)delete this.node.properties.foundrySingle;else clearWizardState(this.node);this.shell.open("Choose a Workflow");
            }}]);
    }
    cancel(){
        dialog(this.shell,msg("mesh.cancel_this_stage"),hint(msg("mesh.completed_stages_will_remain_available_only_this_wizard_s_queued_or_running")),
            [{label:msg("mesh.keep_running"),run:close=>close()},{label:msg("mesh.cancel_stage"),run:close=>{
                close();this.act(async()=>{this.run=await request("wizard/runs/"+this.runId+"/cancel",{});});
            }}]);
    }
    image(url,label){
        const img=el("img",{src:url,alt:label,loading:"lazy"});
        return button(img,()=>dialog(this.shell,label,el("img",{src:url,alt:label,class:"enlarged-image"})),
            {class:"image-preview","aria-label":msg("mesh.enlarge", {label: label})});
    }
    nav({next,nextText=msg("mesh.next"),note="",back=this.page-1}={}){
        const active=!!this.run?.active||this.working;
        return el("footer",{class:"wizard-footer"},note?hint(note):null,
            el("div",{class:"actions"},back>=1?button(msg("mesh.back"),()=>this.go(back),{disabled:active}):null,
                next?button(nextText,()=>this.act(next),{class:"primary",disabled:active}):null,
                next&&this.draft.references.length?button(msg("mesh.rocket_mode"),()=>this.rocket(),{disabled:active,title:msg("mesh.choose_exports_then_finish_the_remaining_stages_automatically")}):null,
                this.run?.active?button(msg("mesh.cancel"),()=>this.cancel(),{class:"danger"}):null,
                button(msg("mesh.start_over_3"),()=>this.confirmReset(),{disabled:active,class:"quiet"})));
    }
    busy(){
        if(!this.run?.active)return null;
        this.sampleProgress=el("span",{class:"muted"});
        const elapsed=elapsedTime((this.run.started_at||this.run.pending?.started)*1000);
        this.overallText=el("strong",{class:"overall-label"});
        this.overallMeter=el("progress",{max:1,"aria-label":msg("mesh.overall_completion")});
        this.overallCount=el("small",{class:"muted"});
        this.updateOverall();
        const p=this.run.progress;
        const stages=p?el("details",{class:"selected-stages"},el("summary",{},msg("mesh.selected_stages")),
            el("ol",{},...p.stages.map(stage=>el("li",{'data-state':p.completed.includes(stage)?'complete':p.current===stage?'current':'remaining'},
                (p.completed.includes(stage)?"Complete · ":p.current===stage?"Current · ":"Remaining · ")+(stageNames[stage]||stage))))):null;
        return el("div",{class:"wizard-busy",role:"status","aria-live":"polite"},
            el("img",{src:new URL("../../assets/foundry-chaos-star.svg",import.meta.url).href,alt:"",class:"working-star"}),
            el("div",{class:"stage-progress"},this.overallText,this.overallMeter,this.overallCount,
                el("strong",{},this.run.dependency?msg("mesh.preparing_required_models"):this.run.stage==="turnaround"?msg("mesh.creating_four_views", {value1: this.run.turnaround?.name||"Image model"}):stageNames[this.run.progress?.current||this.run.stage]||"Preparing the next stage"),this.sampleProgress,elapsed,
                hint(this.run.dependency?FIRST_USE_MESSAGE:this.run.stage==="quads"?((this.cap.quad_methods||[]).find(m=>m.id===(this.run.settings?.quad_method||"quadriflow"))?.description||"Preparing editable quads."):this.run.stage==="refinement"?msg("mesh.refinement_can_take_several_minutes_the_saved_initial_mesh_is_retained"):msg("mesh.your_completed_stages_are_saved_as_the_workflow_progresses")),stages));
    }
    updateOverall(sample=0){
        const p=this.run?.progress;if(!p||!this.overallMeter)return;
        const key=this.run.id+":"+this.run.request_id;
        if(this.overallKey!==key){this.overallKey=key;this.overallValue=0;}
        this.overallValue=overallProgress(p,sample,this.overallValue,this.run.status==="complete"&&p.fraction===1);
        this.overallMeter.value=this.overallValue;
        setText(this.overallText, msg("mesh.overall_completion_2", {value1: Math.floor(this.overallValue*100)}));
        setText(this.overallCount, msg("mesh.of_selected_stages_complete_measures_work_not_time", {value1: p.completed.length, total: p.total}));
    }
    render(){
        if(this.disposed)return;
        this.previewDispose?.();this.previewDispose=null;
        const rail=el("aside",{class:"wizard-rail","aria-label":msg("mesh.workflow_progress")},
            el("span",{class:"eyebrow"},msg("mesh.image_to_3d")),el("h3",{},this.single?msg("mesh.single_image_or_text"):msg("mesh.from_reference_to_asset")),
            el("ol",{class:"wizard-steps"},...(this.single?singleStepLabels:stepLabels).map((title,i)=>el("li",{
                class:i+1===this.page?"current":i+1<this.page?"visited":"",
                ...(i+1===this.page?{"aria-current":"step"}:{})},
                el("span",{class:"step-number","aria-hidden":"true"},String(i+1).padStart(2,"0")),
                el("div",{},el("strong",{},title),el("small",{},(this.single?["Upload, create or choose","Detail and refinement controls","Preview and output choices","Files and production record"]:stepDescriptions)[i]))))),
            el("div",{class:"wizard-rail-note"},el("strong",{},msg("mesh.defaults_are_loaded")),
                hint(msg("mesh.start_with_the_loaded_defaults_open_advanced_whenever_you_want_more_control"))));
        const header=el("div",{class:"page-head"},el("div",{},el("span",{class:"eyebrow"},msg("mesh.page_of", {page: this.page, value2: this.single?4:5})),
            el("h2",{tabindex:-1},(this.single?singleTitles:titles)[this.page-1])));
        const pages=this.single?[singleInputPage,singleOptionsPage,finishingPage,resultPage]:[inputPage,reviewPage,optionsPage,finishingPage,resultPage];
        const problem=this.error?modelAccessError(this.shell,this.error):null;
        if(problem&&!this.run?.active&&this.runId)appendContent(problem, el('div',{class:'actions'},
            button(msg("mesh.retry_remaining_stages"),()=>this.act(()=>this.start(this.run.operation||'mesh')),{class:'primary'}),
            button(msg("mesh.review_output_choices"),()=>this.go(this.single?3:4))));
        const panel=el("div",{class:"wizard-panel"},header,problem,this.busy(),pages[this.page-1](this));
        this.host.replaceChildren(rail,panel);
        // Native DOM append does not accept null. Filtered via the shared helper.
        this.host.querySelector("h2")?.scrollIntoView({block:"nearest"});
        this.remember();
    }
    dispose(){this.disposed=true;clearTimeout(this.timer);this.previewDispose?.();api.removeEventListener("progress",this.progressHandler);}
}
