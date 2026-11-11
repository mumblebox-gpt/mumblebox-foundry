import {sourceMessage} from "../i18n.js";
import {msg, setText, replaceContent} from "../i18n.js";
import {problemPanel} from '../problem-panel.js';
import {elapsedTime} from '../activity.js';
import {api} from '/scripts/api.js';
import {app} from '/scripts/app.js';
import {el,button,hint} from '../dom.js';
import {request} from '../services.js';
import {dialog} from '../dialogs.js';
import {syncGuidedBranch,syncGuidedOutputs,setGuidedQuadAvailability} from './graph.js';
import {startingPage,guidePage,enhancementPage,meshPage,exportPage,resultPage} from './pages.js';
import {editConcept} from './editor.js';
import {exportChoices,validateExports} from '../wizard/export-choices.js';

const clone=v=>JSON.parse(JSON.stringify(v));
const titles=[msg("guided.your_object"),msg("guided.concept_and_measured_guides"),msg("guided.enhance_and_choose_views"),msg("guided.reconstruct_refine_and_texture"),msg("guided.output_versions_and_formats"),msg("guided.your_asset_package")];
const stagePage={concept:2,proxy:2,render:2,sheet:3,enhance_sheet:3,split:3,prepare:3,reconstruct:4,refine:4,texture:4};
const stageNames={concept:msg("guided.creating_the_concept_turnaround"),proxy:msg("guided.building_the_rough_mesh"),render:msg("guided.rendering_measured_blender_views"),sheet:msg("guided.assembling_the_guide_sheet"),
    enhance_sheet:msg("guided.enhancing_the_measured_views"),split:msg("guided.separating_views_for_review"),prepare:msg("guided.preparing_selected_camera_frames"),reconstruct:msg("guided.reconstructing_the_mesh"),
    refine:msg("guided.refining_and_cleaning_geometry"),texture:msg("guided.texturing_the_finished_mesh"),balanced:msg("guided.preparing_the_balanced_mesh"),compact:msg("guided.preparing_the_compact_mesh"),
    quads:msg("guided.building_editable_quad_topology_and_baking_detail"),print:msg("guided.preparing_print_geometry"),package:msg("guided.writing_and_checking_your_asset_package")};
export class GuidedWizard{
    constructor(shell,{resume=false,handoff=null,runId=null,binding=null}={}){
        this.shell=shell;this.node=shell.node;this.disposed=false;this.page=1;
        this.key='mumblebox-foundry/guided/'+app.extensionManager.workflow.activeWorkflow.path;
        let saved=resume?this.node.properties.foundryGuided:null;
        if(resume)try{saved=JSON.parse(localStorage.getItem(this.key))||saved;}catch{}
        this.draft=clone(saved?.draft||{name:'Untitled object',original:'',controls:{},selection:null,finishing:{}});
        this.id=runId||saved?.id||null;this.page=saved?.page||1;
        this.agentBinding=binding;
        if(handoff){this.draft.name=handoff.name;this.draft.original=handoff.references[0].filename;this.draft.image_creation=handoff.image_creation;this.draft.controls.asset_description=handoff.references[0].description||'';this.id=null;this.page=1;}
        this.host=el('section',{class:'wizard guided-wizard','aria-label':msg("guided.3d_guided_wizard")});
        this.progressHandler=e=>{if(this.busyText&&this.active())setText(this.busyText, msg("guided.sampling_step_of", {value1: e.detail.value, max: e.detail.max}));};
        api.addEventListener('progress',this.progressHandler);
    }
    async init(){
        this.cap=await request('guided/capabilities');
        this.draft.selection??=clone(this.cap.selection);
        const available=new Set(this.cap.exports.map(item=>item.id));
        this.draft.selection.variants=Object.fromEntries(Object.entries(this.draft.selection.variants).filter(([key])=>available.has(key)));
        if(!this.cap.quad_retopology_enabled)delete this.draft.finishing.quad_count;
        if(this.id){
            this.job=await request('guided/runs/'+this.id);
            if(this.agentBinding){
                const controls=Object.fromEntries((this.cap.controls||[]).map(key=>[key,this.job.spec[key]]).filter(([,value])=>value!==undefined));
                this.draft={name:this.job.name,original:this.job.spec.original,controls,
                    selection:clone(this.job.rocket_selection||this.cap.selection),
                    finishing:clone(this.job.rocket_overrides||{}),image_creation:this.job.image_creation};
                this.page=this.job.finishing?.package?6:stagePage[this.job.current_stage||this.job.awaiting_stage]||1;
                this.remember();
            }
            await this.graph();
        }
        setGuidedQuadAvailability(this.node,this.cap.quad_retopology_enabled);
        await this.live(this.agentBinding);this.render();this.poll();return this.host;
    }
    active(){return !!(this.working||this.job?.active||this.job?.status==='running'||this.job?.preparing||this.job?.finishing?.active);}
    remember(){
        const state=clone({id:this.id,draft:this.draft,page:this.page});this.node.properties.foundryGuided=state;
        localStorage.setItem(this.key,JSON.stringify(state));app.graph.change?.();
    }
    async live(requestId){
        return this.shell.guidedLive(requestId,this.id);
    }
    async graph(){
        const graph=await request('guided/runs/'+this.id+'/graph');syncGuidedBranch(graph,this.node);
        this.outputs();
    }
    outputs(){
        for(const value of Object.values(this.job?.completed||{}))syncGuidedOutputs(value.result?.outputs,this.node);
        syncGuidedOutputs(this.job?.finishing?.outputs,this.node,200000);
    }
    async poll(){
        if(this.disposed)return;
        try{
            await this.live();
            if(this.id){
                const current=await request('guided/runs/'+this.id);
                if(this.disposed)return;
                const changed=JSON.stringify([current.status,current.active,current.preparing,current.current_stage,current.awaiting_stage,Object.keys(current.completed),current.error,current.finishing?.stage,current.finishing?.status,current.finishing?.active,current.finishing?.package])!==
                    JSON.stringify([this.job?.status,this.job?.active,this.job?.preparing,this.job?.current_stage,this.job?.awaiting_stage,Object.keys(this.job?.completed||{}),this.job?.error,this.job?.finishing?.stage,this.job?.finishing?.status,this.job?.finishing?.active,this.job?.finishing?.package]);
                this.job=current;
                if(changed){this.outputs();if(current.rocket){
                    if(current.finishing?.active||current.finishing?.package)this.page=6;
                    else if(current.current_stage)this.page=stagePage[current.current_stage]||this.page;
                }if(current.finishing?.package){this.page=6;this.error='';}this.render();}
                if(this.busyText&&current.dependency)setText(this.busyText, [current.dependency.name,current.dependency.phase].filter(Boolean).join(' · '));
            }
        }catch(error){this.error=error.message;if(!this.active())this.render();}
        if(!this.disposed)this.timer=setTimeout(()=>this.poll(),1800);
    }
    async act(fn){
        if(this.working)return;this.working=true;this.error='';
        try{await fn();}catch(error){this.error=error.message;}
        finally{this.working=false;if(!this.disposed){this.remember();this.render();}}
    }
    async save(){
        if(!this.draft.original)throw Error(msg("guided.upload_or_select_a_starting_image"));
        if(!this.draft.controls.asset_description?.trim())throw Error(msg("guided.describe_your_object_before_starting"));
        if(!this.id){
            this.job=await request('guided/runs',{name:this.draft.name,original:this.draft.original,controls:this.draft.controls,
                client_id:api.clientId||'',workflow_path:app.extensionManager.workflow.activeWorkflow.path,image_creation:this.draft.image_creation});
            this.id=this.job.id;await this.graph();
        }else this.job=await request('guided/runs/'+this.id,this.draft.controls,{method:'PATCH'});
        this.remember();
    }
    async advance(){
        await this.save();await this.live();
        const operation=this.job.status==='ready'?'start':this.job.status==='awaiting_review'?'continue':'resume';
        this.job=await request('guided/runs/'+this.id+'/action',{operation});
        const sequence=['concept','proxy','render','sheet','enhance_sheet','split','prepare','reconstruct','refine','texture'];
        const next=sequence.find(s=>!this.job.completed[s]);this.page=stagePage[next]||4;
    }
    async finish(){
        this.job=await request('guided/runs/'+this.id+'/action',{operation:'finish',selection:this.draft.selection,overrides:this.draft.finishing,request_id:crypto.randomUUID()});
        this.page=6;
    }
    editConcept(){return editConcept(this);}
    rocket(){
        const selection=clone(this.draft.selection);
        const error=el('p',{class:'error-panel',role:'alert',hidden:true});
        dialog(this.shell,msg("guided.finish_with_rocket_mode"),el('div',{},
            hint(msg("guided.run_all_remaining_stages_and_selected_exports_automatically_without_review_s")),
            exportChoices(this.cap.exports,selection),error),[
            {label:msg("guided.keep_working_step_by_step"),run:close=>close()},
            {label:msg("guided.start_rocket_mode"),primary:true,run:close=>{
                try{validateExports(selection);}catch(e){setText(error, sourceMessage(e.message));error.hidden=false;return;}
                this.draft.selection=selection;this.remember();close();this.act(async()=>{
                    await this.save();await this.live();
                    this.job=await request('guided/runs/'+this.id+'/action',{operation:'rocket',selection,overrides:this.draft.finishing});
                    const next=Object.keys(stagePage).find(s=>!this.job.completed[s]);this.page=stagePage[next]||6;
                });
            }}]);
    }
    go(page){this.page=page;this.remember();this.render();this.shell.content.scrollTop=0;}
    image(url,label){return button(el('img',{src:url,alt:label,loading:'lazy'}),()=>dialog(this.shell,label,el('img',{src:url,alt:label,class:'enlarged-image'})),{class:'image-preview','aria-label':msg("guided.enlarge", {label: label})});}
    artifact(key){return this.job?.artifacts?.[key]?.url;}
    previewArtifact(key){const value=this.job?.artifacts?.[key];return value?.preview?'/view?'+new URLSearchParams(value.preview):value?.url;}
    nav({next,label=msg("guided.continue"),note='',back=this.page-1}={}){
        return el('footer',{class:'wizard-footer'},hint(note),el('div',{class:'actions'},
            back>=1?button(msg("guided.back"),()=>this.go(back),{disabled:this.active()}):null,
            next?button(label,()=>this.act(next),{class:'primary',disabled:this.active()}):null,
            next&&this.draft.original?button(msg("guided.rocket_mode"),()=>this.rocket(),{disabled:this.active()}):null,
            button(msg("guided.save_session"),()=>this.act(()=>this.save()),{disabled:this.active()}),
            this.active()?button(msg("guided.cancel_stage"),()=>this.act(async()=>{this.job=await request('guided/runs/'+this.id+'/action',{operation:'cancel'});}),{class:'danger'}):null,
            button(msg("guided.choose_a_method"),()=>{this.remember();this.shell.open('Choose a Workflow');},{disabled:this.active(),class:'quiet'})));
    }
    render(){
        if(this.disposed||!this.cap)return;
        this.previewDispose?.();this.previewDispose=null;
        const rail=el('aside',{class:'wizard-rail','aria-label':msg("guided.3d_guided_progress")},el('span',{class:'eyebrow'},msg("guided.3d_guided")),el('h3',{},msg("guided.one_shape_measured_views")),
            el('ol',{class:'wizard-steps'},...titles.map((t,i)=>el('li',{class:i+1===this.page?'current':'',...(i+1===this.page?{'aria-current':'step'}:{})},
                el('span',{class:'step-number'},String(i+1).padStart(2,'0')),el('div',{},el('strong',{},t))))),
            el('div',{class:'wizard-rail-note'},hint(msg("guided.objects_preset_four_measured_views_defaults_follow_the_completed_chest_workf"))));
        const pages=[startingPage,guidePage,enhancementPage,meshPage,exportPage,resultPage];
        this.busyText=el('span',{class:'muted'});
        const active=this.active();const error=this.error||this.job?.error||this.job?.finishing?.error;
        replaceContent(this.host, rail, el('div',{class:'wizard-panel'},el('div',{class:'page-head'},el('span',{class:'eyebrow'},msg("guided.3d_guided_page_of_6", {page: this.page})),el('h2',{},titles[this.page-1])),
            error?problemPanel(error):null,
            active?el('section',{class:'wizard-busy',role:'status','aria-live':'polite'},el('strong',{},this.job?.preparing?msg("guided.preparing_required_resources"):stageNames[this.job?.finishing?.stage||this.job?.current_stage]||'Starting selected stage'),this.busyText,
                elapsedTime((this.job?.started_at||this.job?.finishing?.started_at)*1000),
                hint(msg("guided.of_10_generation_stages_saved_completed_files_remain_available", {value1: Object.keys(this.job?.completed||{}).length}))):null,
            pages[this.page-1](this)));
        this.remember();
    }
    dispose(){this.disposed=true;clearTimeout(this.timer);this.previewDispose?.();api.removeEventListener('progress',this.progressHandler);}
}
