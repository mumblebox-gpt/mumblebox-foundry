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
const singleTitles=['Your starting image','Mesh and refinement','Refined mesh and exports','Your asset package'];
const clone=value=>JSON.parse(JSON.stringify(value));
const titles=["Your starting images","Review the four views","Mesh and refinement","Refined mesh and exports","Your asset package"];
const stepLabels=["Starting images","Four views","Mesh settings","Refine & export","Asset package"];
const stepDescriptions=["References and image model","Review the turnaround","Detail and refinement controls","Preview and output choices","Files and production record"];
const stageNames={turnaround:"Qwen Image 2.1 · Creating four views",geometry:"Pixal3D / TRELLIS.2 · Building the initial mesh",
 refinement:"Hi3D · Refining and cleaning the geometry",texture:"TRELLIS.2 · Texturing the finished geometry",
 balanced:"Baking the balanced game mesh",compact:"Baking the compact game mesh",quads:"QuadriFlow · Retopology, UVs and detail baking",
 print:"Preparing and measuring the print mesh",package:"Writing exports, README and ZIP",cleanup:"Releasing models and temporary work"};
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
        this.host=el("section",{class:"wizard","aria-label":"Image to 3D wizard"});
        this.progressHandler=e=>{
            if(!this.run?.active||e.detail?.prompt_id&&e.detail.prompt_id!==this.run.pending?.prompt_id)return;
            const value=e.detail?.value,max=e.detail?.max;
            if(Number.isFinite(value)&&max>0&&this.sampleProgress)this.sampleProgress.textContent="Current step · "+value+" of "+max;
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
        this.shell.message("Local workspace · Image-to-3D workflow");
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
                    this.sampleProgress.textContent=[d.name,d.phase,d.total?Math.round((d.bytes||0)/d.total*100)+"%":""].filter(Boolean).join(" · ");
                }
            }
        }catch(error){if(!this.disposed)this.shell.message(error.message,true);}
        if(!this.disposed)this.timer=setTimeout(()=>this.poll(),1800);
    }
    async act(fn){
        if(this.working)return;
        this.working=true;this.error="";
        try{await fn();this.shell.message("Local workspace · Image-to-3D workflow");}
        catch(error){this.error=error.message;this.shell.message(error.message,true);}
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
    rocket(){
        const selection=structuredClone(this.draft.selection);
        const error=el("p",{class:"error-panel",role:"alert",hidden:true});
        dialog(this.shell,"Finish this asset with Rocket Mode?",el("div",{class:"rocket-confirmation"},
            hint("Continue from this point using your current settings. Saved, unchanged stages are reused. The remaining stages run automatically without further Next clicks."),
            exportChoices(this.cap.exports,selection),error),[
            {label:"Keep working manually",run:close=>close()},
            {label:"Start Rocket Mode",primary:true,run:close=>{
                try{validateExports(selection);}catch(e){error.textContent=e.message;error.hidden=false;return;}
                this.draft.selection=selection;this.remember();close();this.act(()=>this.start("rocket"));
            }}]);
    }
    confirmReset(){
        dialog(this.shell,"Start over?",hint("Return to workflow selection? Your saved images, meshes and packages will remain on disk."),
            [{label:"Keep working",run:close=>close()},{label:"Start over",primary:true,run:close=>{
                close();if(this.single)delete this.node.properties.foundrySingle;else clearWizardState(this.node);this.shell.open("Choose a Workflow");
            }}]);
    }
    cancel(){
        dialog(this.shell,"Cancel this stage?",hint("Completed stages will remain available. Only this wizard's queued or running job will be cancelled."),
            [{label:"Keep running",run:close=>close()},{label:"Cancel stage",run:close=>{
                close();this.act(async()=>{this.run=await request("wizard/runs/"+this.runId+"/cancel",{});});
            }}]);
    }
    image(url,label){
        const img=el("img",{src:url,alt:label,loading:"lazy"});
        return button(img,()=>dialog(this.shell,label,el("img",{src:url,alt:label,class:"enlarged-image"})),
            {class:"image-preview","aria-label":"Enlarge "+label});
    }
    nav({next,nextText="Next",note="",back=this.page-1}={}){
        const active=!!this.run?.active||this.working;
        return el("footer",{class:"wizard-footer"},note?hint(note):null,
            el("div",{class:"actions"},back>=1?button("Back",()=>this.go(back),{disabled:active}):null,
                next?button(nextText,()=>this.act(next),{class:"primary",disabled:active}):null,
                next&&this.draft.references.length?button("Rocket Mode",()=>this.rocket(),{disabled:active,title:"Choose exports, then finish the remaining stages automatically"}):null,
                this.run?.active?button("Cancel",()=>this.cancel(),{class:"danger"}):null,
                button("Start Over",()=>this.confirmReset(),{disabled:active,class:"quiet"})));
    }
    busy(){
        if(!this.run?.active)return null;
        this.sampleProgress=el("span",{class:"muted"});
        const elapsed=elapsedTime((this.run.started_at||this.run.pending?.started)*1000);
        this.overallText=el("strong",{class:"overall-label"});
        this.overallMeter=el("progress",{max:1,"aria-label":"Overall completion"});
        this.overallCount=el("small",{class:"muted"});
        this.updateOverall();
        const p=this.run.progress;
        const stages=p?el("details",{class:"selected-stages"},el("summary",{},"Selected stages"),
            el("ol",{},...p.stages.map(stage=>el("li",{'data-state':p.completed.includes(stage)?'complete':p.current===stage?'current':'remaining'},
                (p.completed.includes(stage)?"Complete · ":p.current===stage?"Current · ":"Remaining · ")+(stageNames[stage]||stage))))):null;
        return el("div",{class:"wizard-busy",role:"status","aria-live":"polite"},
            el("img",{src:new URL("../../assets/foundry-chaos-star.svg",import.meta.url).href,alt:"",class:"working-star"}),
            el("div",{class:"stage-progress"},this.overallText,this.overallMeter,this.overallCount,
                el("strong",{},this.run.dependency?"Preparing required models":this.run.stage==="turnaround"?(this.run.turnaround?.name||"Image model")+" · Creating four views":stageNames[this.run.progress?.current||this.run.stage]||"Preparing the next stage"),this.sampleProgress,elapsed,
                hint(this.run.dependency?FIRST_USE_MESSAGE:this.run.stage==="quads"?"QuadriFlow uses the CPU. High CPU use and spikes are normal. Retopology can take several minutes.":this.run.stage==="refinement"?"Refinement can take several minutes. The saved initial mesh is retained.":"Your completed stages are saved as the workflow progresses."),stages));
    }
    updateOverall(sample=0){
        const p=this.run?.progress;if(!p||!this.overallMeter)return;
        const key=this.run.id+":"+this.run.request_id;
        if(this.overallKey!==key){this.overallKey=key;this.overallValue=0;}
        this.overallValue=overallProgress(p,sample,this.overallValue,this.run.status==="complete"&&p.fraction===1);
        this.overallMeter.value=this.overallValue;
        this.overallText.textContent="Overall completion · "+Math.floor(this.overallValue*100)+"%";
        this.overallCount.textContent=p.completed.length+" of "+p.total+" selected stages complete · measures work, not time";
    }
    render(){
        if(this.disposed)return;
        this.previewDispose?.();this.previewDispose=null;
        const rail=el("aside",{class:"wizard-rail","aria-label":"Workflow progress"},
            el("span",{class:"eyebrow"},"IMAGE TO 3D"),el("h3",{},this.single?"Single Image\nor Text":"From reference\nto asset"),
            el("ol",{class:"wizard-steps"},...(this.single?["Starting image","Mesh settings","Refine & export","Asset package"]:stepLabels).map((title,i)=>el("li",{
                class:i+1===this.page?"current":i+1<this.page?"visited":"",
                ...(i+1===this.page?{"aria-current":"step"}:{})},
                el("span",{class:"step-number","aria-hidden":"true"},String(i+1).padStart(2,"0")),
                el("div",{},el("strong",{},title),el("small",{},(this.single?["Upload, create or choose","Detail and refinement controls","Preview and output choices","Files and production record"]:stepDescriptions)[i]))))),
            el("div",{class:"wizard-rail-note"},el("strong",{},"Defaults are loaded"),
                hint("Start with the loaded defaults. Open Advanced whenever you want more control.")));
        const header=el("div",{class:"page-head"},el("div",{},el("span",{class:"eyebrow"},"PAGE "+this.page+" OF "+(this.single?4:5)),
            el("h2",{tabindex:-1},(this.single?singleTitles:titles)[this.page-1])));
        const pages=this.single?[singleInputPage,singleOptionsPage,finishingPage,resultPage]:[inputPage,reviewPage,optionsPage,finishingPage,resultPage];
        const problem=this.error?modelAccessError(this.shell,this.error):null;
        if(problem&&!this.run?.active&&this.runId)problem.append(el('div',{class:'actions'},
            button('Retry remaining stages',()=>this.act(()=>this.start(this.run.operation||'mesh')),{class:'primary'}),
            button('Review output choices',()=>this.go(this.single?3:4))));
        const panel=el("div",{class:"wizard-panel"},header,problem,this.busy(),pages[this.page-1](this));
        this.host.replaceChildren(rail,panel);
        // Native DOM append does not accept null. Filtered via the shared helper.
        this.host.querySelector("h2")?.scrollIntoView({block:"nearest"});
        this.remember();
    }
    dispose(){this.disposed=true;clearTimeout(this.timer);this.previewDispose?.();api.removeEventListener("progress",this.progressHandler);}
}
