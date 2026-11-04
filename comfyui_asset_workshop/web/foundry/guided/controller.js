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
const titles=['Your object','Concept and measured guides','Enhance and choose views','Reconstruct, refine and texture','Output versions and formats','Your asset package'];
const stagePage={concept:2,proxy:2,render:2,sheet:3,enhance_sheet:3,split:3,prepare:3,reconstruct:4,refine:4,texture:4};
const stageNames={concept:'Creating the concept turnaround',proxy:'Building the rough mesh',render:'Rendering measured Blender views',sheet:'Assembling the guide sheet',
    enhance_sheet:'Enhancing the measured views',split:'Separating views for review',prepare:'Preparing selected camera frames',reconstruct:'Reconstructing the mesh',
    refine:'Refining and cleaning geometry',texture:'Texturing the finished mesh',balanced:'Preparing the balanced mesh',compact:'Preparing the compact mesh',
    quads:'Building editable quad topology and baking detail',print:'Preparing print geometry',package:'Writing and checking your asset package'};
export class GuidedWizard{
    constructor(shell,{resume=false,handoff=null}={}){
        this.shell=shell;this.node=shell.node;this.disposed=false;this.page=1;
        this.key='mumblebox-foundry/guided/'+app.extensionManager.workflow.activeWorkflow.path;
        let saved=resume?this.node.properties.foundryGuided:null;
        if(resume)try{saved=JSON.parse(localStorage.getItem(this.key))||saved;}catch{}
        this.draft=clone(saved?.draft||{name:'Untitled object',original:'',controls:{},selection:null,finishing:{}});
        this.id=saved?.id||null;this.page=saved?.page||1;
        if(handoff){this.draft.name=handoff.name;this.draft.original=handoff.references[0].filename;this.draft.image_creation=handoff.image_creation;this.draft.controls.asset_description=handoff.references[0].description||'';this.id=null;this.page=1;}
        this.host=el('section',{class:'wizard guided-wizard','aria-label':'3D-Guided wizard'});
        this.progressHandler=e=>{if(this.busyText&&this.active())this.busyText.textContent='Sampling step '+e.detail.value+' of '+e.detail.max;};
        api.addEventListener('progress',this.progressHandler);
    }
    async init(){
        this.cap=await request('guided/capabilities');
        this.draft.selection??=clone(this.cap.selection);
        const available=new Set(this.cap.exports.map(item=>item.id));
        this.draft.selection.variants=Object.fromEntries(Object.entries(this.draft.selection.variants).filter(([key])=>available.has(key)));
        if(!this.cap.quad_retopology_enabled)delete this.draft.finishing.quad_count;
        if(this.id){this.job=await request('guided/runs/'+this.id);await this.graph();}
        setGuidedQuadAvailability(this.node,this.cap.quad_retopology_enabled);
        await this.live();this.render();this.poll();return this.host;
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
                if(this.busyText&&current.dependency)this.busyText.textContent=[current.dependency.name,current.dependency.phase].filter(Boolean).join(' · ');
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
        if(!this.draft.original)throw Error('Upload or select a starting image.');
        if(!this.draft.controls.asset_description?.trim())throw Error('Describe your object before starting.');
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
        dialog(this.shell,'Finish with Rocket Mode?',el('div',{},
            hint('Run all remaining stages and selected exports automatically, without review stops. Rocket uses your current settings and selected views. If you have not reviewed the generated views, all four preset views are selected by default. Only a failure or cancellation stops the run.'),
            exportChoices(this.cap.exports,selection),error),[
            {label:'Keep working step by step',run:close=>close()},
            {label:'Start Rocket Mode',primary:true,run:close=>{
                try{validateExports(selection);}catch(e){error.textContent=e.message;error.hidden=false;return;}
                this.draft.selection=selection;this.remember();close();this.act(async()=>{
                    await this.save();await this.live();
                    this.job=await request('guided/runs/'+this.id+'/action',{operation:'rocket',selection,overrides:this.draft.finishing});
                    const next=Object.keys(stagePage).find(s=>!this.job.completed[s]);this.page=stagePage[next]||6;
                });
            }}]);
    }
    go(page){this.page=page;this.remember();this.render();this.shell.content.scrollTop=0;}
    image(url,label){return button(el('img',{src:url,alt:label,loading:'lazy'}),()=>dialog(this.shell,label,el('img',{src:url,alt:label,class:'enlarged-image'})),{class:'image-preview','aria-label':'Enlarge '+label});}
    artifact(key){return this.job?.artifacts?.[key]?.url;}
    previewArtifact(key){const value=this.job?.artifacts?.[key];return value?.preview?'/view?'+new URLSearchParams(value.preview):value?.url;}
    nav({next,label='Continue',note='',back=this.page-1}={}){
        return el('footer',{class:'wizard-footer'},hint(note),el('div',{class:'actions'},
            back>=1?button('Back',()=>this.go(back),{disabled:this.active()}):null,
            next?button(label,()=>this.act(next),{class:'primary',disabled:this.active()}):null,
            next&&this.draft.original?button('Rocket Mode',()=>this.rocket(),{disabled:this.active()}):null,
            button('Save session',()=>this.act(()=>this.save()),{disabled:this.active()}),
            this.active()?button('Cancel stage',()=>this.act(async()=>{this.job=await request('guided/runs/'+this.id+'/action',{operation:'cancel'});}),{class:'danger'}):null,
            button('Choose a method',()=>{this.remember();this.shell.open('Choose a Workflow');},{disabled:this.active(),class:'quiet'})));
    }
    render(){
        if(this.disposed||!this.cap)return;
        this.previewDispose?.();this.previewDispose=null;
        const rail=el('aside',{class:'wizard-rail','aria-label':'3D-Guided progress'},el('span',{class:'eyebrow'},'3D-GUIDED'),el('h3',{},'One shape.\nMeasured views.'),
            el('ol',{class:'wizard-steps'},...titles.map((t,i)=>el('li',{class:i+1===this.page?'current':'',...(i+1===this.page?{'aria-current':'step'}:{})},
                el('span',{class:'step-number'},String(i+1).padStart(2,'0')),el('div',{},el('strong',{},t))))),
            el('div',{class:'wizard-rail-note'},hint('Objects preset · four measured views. Defaults follow the completed chest workflow.')));
        const pages=[startingPage,guidePage,enhancementPage,meshPage,exportPage,resultPage];
        this.busyText=el('span',{class:'muted'});
        const active=this.active();const error=this.error||this.job?.error||this.job?.finishing?.error;
        this.host.replaceChildren(rail,el('div',{class:'wizard-panel'},el('div',{class:'page-head'},el('span',{class:'eyebrow'},'3D-GUIDED / PAGE '+this.page+' OF 6'),el('h2',{},titles[this.page-1])),
            error?el('p',{class:'error-panel',role:'alert'},error):null,
            active?el('section',{class:'wizard-busy',role:'status','aria-live':'polite'},el('strong',{},this.job?.preparing?'Preparing required resources':stageNames[this.job?.finishing?.stage||this.job?.current_stage]||'Starting selected stage'),this.busyText,
                hint(Object.keys(this.job?.completed||{}).length+' of 10 generation stages saved. Completed files remain available.')):null,
            pages[this.page-1](this)));
        this.remember();
    }
    dispose(){this.disposed=true;clearTimeout(this.timer);this.previewDispose?.();api.removeEventListener('progress',this.progressHandler);}
}
