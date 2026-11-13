import {sourceMessage} from "../i18n.js";
import {msg, setText, appendContent} from "../i18n.js";
import {problemPanel} from '../problem-panel.js';
import {api} from '/scripts/api.js';
import {app} from '/scripts/app.js';
import {el,button,hint,field,link} from '../dom.js';
import {request} from '../services.js';
import {dialog} from '../dialogs.js';
import {activity,elapsedTime} from '../activity.js';
import {uploadReference,capturePhoto,galleryReference,inputURL} from '../images/references.js';
import {mountMesh} from '../wizard/preview.js';
import {syncSplatGraph,syncSplatOutputs} from './graph.js';
import {page,titles,blurbs} from './pages.js';
const clone=v=>JSON.parse(JSON.stringify(v));
export const fileURL=(id,path,download=false)=>'/mumblebox-foundry/v1/splat/runs/'+id+'/file?'+new URLSearchParams({path,...download?{download:'1'}:{}});

export class SplatWizard{
    constructor(shell,{resume=false,runId=null,handoff=null}={}){
        this.shell=shell;this.node=shell.node;const saved=resume?this.node.properties.foundrySplat:null;
        this.page=runId?6:saved?.page||1;this.runId=runId||saved?.runId;this.draft=saved?.draft;this.handoff=handoff;
        this.host=el('section',{class:'wizard splat-wizard','aria-label':msg("splat.splat_solid_wizard")});this.disposers=[];
        this.sampleProgress=e=>{
            const d=e.detail,p=this.run?.pending;
            if(!p||d.prompt_id!==p.id||!(d.max>0))return;
            const range={generation:[8,34],refinement:[35,69],cleanup:[70,87]}[p.stage];
            if(range)this.overall=Math.max(this.overall||0,Math.floor(range[0]+(range[1]-range[0])*Math.min(1,d.value/d.max)));
            this.updateProgress();
        };
        api.addEventListener('progress',this.sampleProgress);
    }
    async init(){
        this.cap=await request('splat/capabilities');this.draft??=clone(this.cap.defaults);
        if(this.handoff){this.draft.image=this.handoff.references[0].filename;this.draft.name=this.handoff.name;this.runId=null;}
        if(this.runId){this.run=await request('splat/runs/'+this.runId);this.draft=clone(this.run.config);await this.graph('generation',true);syncSplatOutputs(this.run.outputs,this.node);}
        else syncSplatGraph(await request('splat/template'),this.node);
        this.render();this.poll();return this.host;
    }
    remember(){this.node.properties.foundrySplat={page:this.page,runId:this.runId,draft:clone(this.draft)};app.graph.change?.();}
    go(p){this.page=p;this.remember();this.render();this.shell.content.scrollTop=0;}
    active(){return this.working||this.run?.active;}
    async act(fn){if(this.working)return;this.working=true;this.error='';try{await fn();}catch(e){this.error=e.message;}finally{this.working=false;this.remember();this.render();}}
    async save(){this.run=await request(this.runId?'splat/runs/'+this.runId:'splat/runs',this.draft,this.runId?{method:'PATCH'}:{});this.runId=this.run.id;this.remember();}
    async graph(stage,full=false){syncSplatGraph(await request('splat/runs/'+this.runId+'/graph?'+new URLSearchParams({stage,...full?{full:'1'}:{}})),this.node);}
    async start(operation){
        await this.save();await this.graph('generation',true);
        this.overall=0;
        this.run=await request('splat/runs/'+this.runId+'/start',{operation,request_id:crypto.randomUUID(),client_id:api.clientId||''});
        this.page=operation==='generation'?3:operation==='cleanup'?4:6;this.remember();
    }
    rocket(){
        dialog(this.shell,msg("splat.finish_with_rocket_mode"),el('div',{},hint(msg("splat.continue_through_the_remaining_selected_stages_using_these_settings_unchange")),hint(msg("splat.selected_output_files_are_shown_on_generation_options"))),[
            {label:msg("splat.keep_reviewing"),run:close=>close()},
            {label:msg("splat.start_rocket_mode"),primary:true,run:close=>{close();this.act(()=>this.start('rocket'));}}]);
    }
    async poll(){
        if(this.disposed)return;
        try{if(this.runId){
            const next=await request('splat/runs/'+this.runId);if(this.disposed)return;
            const changed=JSON.stringify([next.active,next.status,next.stage,next.dependency,next.package,next.artifacts])!==JSON.stringify([this.run?.active,this.run?.status,this.run?.stage,this.run?.dependency,this.run?.package,this.run?.artifacts]);this.run=next;
            if(next.pending?.id!==this.lastPrompt&&next.pending){this.lastPrompt=next.pending.id;await this.graph(next.pending.stage);}
            syncSplatOutputs(next.outputs,this.node);if(changed)this.render();
            this.updateProgress();
        }}catch(e){this.error=e.message;this.render();}
        finally{if(!this.disposed)this.timer=setTimeout(()=>this.poll(),1200);}
    }
    updateProgress(){
        const percent=this.run?.active?Math.min(99,Math.max(this.run.progress||0,this.overall||0)):this.run?.progress||0;
        if(this.progress)this.progress.value=percent;
        if(this.progressText)setText(this.progressText, msg("splat.overall", {percent: percent, value2: this.run?.stage||''}));
    }
    text(key,label,description){return field(label,el('input',{value:this.draft[key],maxLength:120,oninput:e=>{this.draft[key]=e.target.value;this.remember();}}),description);}
    number(key,label,min,max,step=1){return field(label,el('input',{type:'number',value:this.draft[key],min,max,step,onchange:e=>{this.draft[key]=Number(e.target.value);this.remember();}}));}
    check(key,label,description){return el('label',{class:'check-row'},el('input',{type:'checkbox',checked:this.draft[key],onchange:e=>{this.draft[key]=e.target.checked;this.remember();}}),el('span',{},label,description?hint(description):null));}
    nav({next,nextText=msg("splat.next"),back=this.page-1}={}){
        return el('footer',{class:'wizard-footer'},el('div',{class:'actions'},back>=1?button(msg("splat.back"),()=>this.go(back),{disabled:this.active()}):null,
            next?button(nextText,()=>this.act(next),{class:'primary',disabled:this.active()||!this.draft.image}):null,
            button(msg("splat.choose_a_workflow"),()=>this.shell.open('Choose a Workflow')),
            button(msg("splat.rocket_mode"),()=>this.rocket(),{disabled:this.active()||!this.draft.image}),
            this.run?.active?button(msg("splat.cancel_current_work"),()=>this.act(async()=>{this.run=await request('splat/runs/'+this.runId+'/cancel',{});})) :null));
    }
    async upload(file){if(!file)return;const ref=await uploadReference(file);this.draft.image=ref.filename;this.remember();}
    async gallery(){
        const list=el('div',{class:'hair-gallery'});const modal=dialog(this.shell,msg("splat.choose_a_saved_reference"),list);
        const data=await request('images?limit=100');
        for(const item of data.items||[])for(const [side,id] of Object.entries(item.accepted||{})){
            const url='/mumblebox-foundry/v1/images/'+item.id+'/files/'+id;
            list.append(button([el('img',{src:url,alt:item.name+' '+side,style:'max-width:150px'}),el('span',{},item.name+' · '+side)],()=>this.act(async()=>{
                const handoff=await galleryReference(item.id,side,id);
                this.draft.image=handoff.references[0].filename;this.remember();modal.close();
            })));
        }
        if(!list.children.length)appendContent(list, hint(msg("splat.no_saved_images_yet_upload_a_reference_or_take_a_photo")));
    }
    artifact(role,label,{preview=false}={}){
        const item=this.run?.artifacts?.[role];if(!item)return hint(msg("splat.will_appear_after_its_stage_finishes", {label: label}));
        const url=fileURL(this.runId,item.relative),box=el('section',{class:'preview-card'},el('h3',{},label));
        if(preview){const target=el('div',{class:'mesh-preview',style:'min-height:360px;height:420px'});box.append(target);
            const epoch=this.renderEpoch;
            requestAnimationFrame(()=>{if(!target.isConnected)return;mountMesh(target,url,this.cap.viewer_module,item.relative.split('/').at(-1)).then(d=>{if(this.disposed||epoch!==this.renderEpoch)d();else this.disposers.push(d);}).catch(e=>{if(target.isConnected)target.replaceChildren(hint(sourceMessage(e.message)));});});}
        else if(item.relative.endsWith('.mp4'))box.append(el('video',{src:url,controls:true,loop:true,style:'width:100%'}));
        else if(item.relative.endsWith('.png'))box.append(el('img',{src:url,alt:label,style:'max-width:100%'}));
        appendContent(box, link(msg("splat.download", {label: label}),fileURL(this.runId,item.relative,true)));return box;
    }
    render(){
        this.renderEpoch=(this.renderEpoch||0)+1;this.disposers.splice(0).forEach(d=>d());this.host.replaceChildren();
        const rail=el('aside',{class:'wizard-rail'},el('span',{class:'eyebrow'},msg("splat.idol_splat_solid")),el('h3',{},msg("splat.splat_solid")),el('ol',{class:'wizard-steps'},...titles.map((title,i)=>el('li',{class:i+1===this.page?'current':''},el('span',{},String(i+1)),el('div',{},el('strong',{},title),el('small',{},blurbs[i]))))),hint(msg("splat.visual_detail_from_idol_separate_companion_geometry")));
        const panel=el('div',{class:'wizard-panel'},el('header',{class:'page-head'},el('span',{class:'eyebrow'},msg("splat.page_of_6", {page: this.page})),el('h2',{},this.page===6&&this.active()?msg("splat.creating_your_asset"):titles[this.page-1])));
        if(this.error||this.run?.error)panel.append(problemPanel(this.error||this.run.error));
        if(this.run?.active){const a=activity();a.update({busy:true,label:this.run.stage,detail:this.run.dependency?.name||'Completed stages remain saved.'});this.progress=el('progress',{max:100,value:this.run.progress||0,'aria-label':msg("splat.overall_splat_solid_progress")});this.progressText=el('strong',{},'');panel.append(a.element,elapsedTime(this.run.started_at*1000),this.progress,this.progressText);}
        panel.append(page(this));this.host.append(rail,panel);this.updateProgress();
    }
    dispose(){this.disposed=true;clearTimeout(this.timer);api.removeEventListener('progress',this.sampleProgress);this.disposers.splice(0).forEach(d=>d());this.remember();}
}
