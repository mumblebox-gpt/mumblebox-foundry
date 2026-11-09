import {fontControl,TEXT_SIZES} from './typography.js';
import {el,button,icon,hint} from "./dom.js";
import {activityState,loadedState} from "./activity-state.js";
import {activity} from "./activity.js";
import {UpdateChecks} from "./updates.js";
import {resourceMeter} from "./telemetry.js";
import {request,pollResources} from "./services.js";
import {dialog} from "./dialogs.js";
import {home} from "./views/home.js";
import {showWorkflow} from "./graph-adapter.js";
import {api} from "/scripts/api.js";
import {app} from "/scripts/app.js";
import {launchMessage} from "./app-mode.js";
import {installTextClipboard} from "./clipboard.js";
import {syncGuidedBranch,syncGuidedOutputs} from './guided/graph.js';

export class FoundryShell {
    constructor(host,node) {
        this.statusListeners=new Set();this.node=node; this.host=host; this.tab="Choose a Workflow";
        this.shadow=host.shadowRoot||host.attachShadow({mode:"open"});
        this.shadow.replaceChildren();
        for (const file of ["theme.css","layout.css","images.css","roadmap.css"]) this.shadow.append(el("link",{rel:"stylesheet",href:new URL(file,import.meta.url).href}));
        this.root=el("div",{class:"foundry","data-theme":matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light"});
        this.shadow.append(this.root);
        this.stopTextClipboard=installTextClipboard(this.root);
        // OrbitControls receives pointerup at the shadow root. Let releases
        // reach it; swallowing them leaves the viewer stuck in a drag.
        for(const event of ["pointerdown","click","dblclick","wheel","keydown","contextmenu"])
            this.root.addEventListener(event,e=>e.stopPropagation());
        this.build();
        this.updates=new UpdateChecks(this);
        this.bootstrap();
        this.stopPolling=pollResources(status=>this.resources(status),()=>this.resources(null));
        this.agentRunHandler=event=>{
            if(this.node.graph!==app.graph||!this.host.isConnected)return;
            const id=event.detail?.id;
            if(typeof id==="string"&&/^[a-f0-9]{32}$/.test(id))this.openWizard({runId:id,method:event.detail?.method||"turnaround"});
        };
        api.addEventListener("mumblebox-foundry-run",this.agentRunHandler);
        this.agentImageHandler=event=>{
            if(this.node.graph!==app.graph||!this.host.isConnected)return;
            const id=event.detail?.id;
            if(typeof id==='string'&&/^[a-f0-9]{32}$/.test(id)){this.openImageId=id;this.openImages('Create Images');}
        };
        api.addEventListener('mumblebox-foundry-image',this.agentImageHandler);
        this.agentHairHandler=event=>{
            if(this.node.graph!==app.graph||!this.host.isConnected)return;
            const id=event.detail?.id;
            if(typeof id==='string'&&/^[a-f0-9]{32}$/.test(id))this.openHairWizard({runId:id});
        };
        api.addEventListener('mumblebox-foundry-hair',this.agentHairHandler);
        this.agentSplatHandler=e=>{if(this.node.graph===app.graph&&this.host.isConnected&&/^[a-f0-9]{32}$/.test(e.detail?.id||''))this.openSplatWizard({runId:e.detail.id});};
        api.addEventListener('mumblebox-foundry-splat',this.agentSplatHandler);
        // Native processing belongs to the selected graph, not a particular
        // wizard page. Navigation within Foundry must not disconnect Rocket.
        this.guidedBindHandler=e=>this.bindGuided(e.detail).catch(error=>this.message(error.message,true));
        api.addEventListener('guided.bind',this.guidedBindHandler);
        this.guidedHeartbeat=setInterval(()=>{
            if(this.node.properties.foundryGuided?.id)this.guidedLive().catch(()=>{});
        },15000);
    }
    build() {
        this.version=el("small",{},"Interface loading");
        const languages=el("select",{class:"language","aria-label":"Language"},el("option",{value:"en"},"English"),
            ...["Korean","Japanese","Mandarin","Spanish","Portuguese","German"].map(name=>el("option",{disabled:true},name+" — Coming soon")));
        this.themeButton=button([icon("contrast",18),"Theme"],()=>this.setTheme(this.root.dataset.theme==="dark"?"light":"dark"));
        this.themeButton.setAttribute("aria-label","Switch color theme");
        this.fontControl=fontControl(this);
        this.updateSlot=el("div",{class:"header-update",role:"status","aria-live":"polite"});
        this.settingsButton=button([icon("gear",18),"Settings"],()=>this.settings());
        const donate=button("Coffee",()=>{}, {disabled:true,title:"Coffee link coming soon"});
        const identity=el("div",{class:"identity"},el("div",{class:"brand"},el("div",{class:"brand-lockup"},
            el("h1",{},el("img",{class:"brand-logo",src:new URL("../assets/foundry/logo-approved.png",import.meta.url).href,alt:"Mumblebox 3D Asset Foundry",width:2172,height:724})),this.version)),
            el("div",{class:"header-tools"},el("div",{class:"header-actions"},languages,this.themeButton,this.fontControl.element,this.settingsButton,donate),this.updateSlot));
        this.vram=resourceMeter("VRAM");this.ram=resourceMeter("RAM");this.cpu=resourceMeter("CPU",{percent:true});
        this.loadedDot=el("span",{class:"loaded-dot","aria-hidden":"true"});
        this.loadedLabel=el("small",{},"Model state unavailable");
        this.unload=button([this.loadedDot,"Unload Models"],()=>this.unloadModels(),{disabled:true});
        this.activity=activity();
        this.resourceBar=el("div",{class:"resources"},this.vram.element,this.ram.element,this.cpu.element,
            this.activity.element,el("div",{class:"model-residency"},this.unload,this.loadedLabel));
        this.nav=el("nav",{class:"tabs",role:"tablist","aria-label":"Foundry sections"});
        this.tabs=["Choose a Workflow","Images","History","Integrations","About","Roadmap"];
        this.tabs.forEach((name,i)=>this.nav.append(button([icon(["cube","image","history","plug","info","map"][i],16),name],()=>this.open(name),{class:i===2?"secondary-start":"",role:"tab","aria-selected":name===this.tab,tabindex:name===this.tab?0:-1})));
        this.nav.addEventListener("keydown",e=>{
            if(!["ArrowRight","ArrowLeft","Home","End"].includes(e.key))return;
            e.preventDefault();
            const index=this.tabs.indexOf(this.tab);
            const next=e.key==="Home"?0:e.key==="End"?this.tabs.length-1:(index+(e.key==="ArrowRight"?1:-1)+this.tabs.length)%this.tabs.length;
            this.open(this.tabs[next]);this.nav.children[next].focus();
        });
        this.content=el("main",{class:"content",role:"tabpanel","aria-label":this.tab});
        this.notice=el("div",{class:"status",role:"status","aria-live":"polite"},"Loading Foundry services…");
        this.root.append(el("header",{class:"top"},identity,this.resourceBar),this.nav,this.content,this.notice);
        this.resources(null);this.open(this.tab);
    }
    async bootstrap() {
        try {
            this.data=await request("bootstrap");
            if(!this.node.graph._nodes.some(n=>n.properties?.guidedOwner===this.node.id))
                syncGuidedBranch(await request('guided/template'),this.node);
            this.version.textContent="v"+this.data.version;
            await this.setFontSize(this.data.preferences.font_size||"default",false);
            this.root.dataset.motion=this.data.preferences.busy_motion||"system";
            if(this.data.preferences.theme) await this.setTheme(this.data.preferences.theme,false);
            else await this.setTheme(this.root.dataset.theme,false);
            this.message("Local workspace · Image-to-3D workflow");
            this.open(this.tab);
            this.updates.startup();
        } catch(error) {this.message(error.message,true);}
    }
    async setTheme(theme,save=true) {
        this.root.dataset.theme=theme;
        this.themeButton.title=theme==="dark"?"Switch to light theme":"Switch to dark theme";
        this.themeButton.setAttribute("aria-pressed",String(theme==="dark"));
        if(save)try{await request("preferences",{theme},{method:"PATCH"});}catch(e){this.message(e.message,true);}
    }
    async setFontSize(value,save=true){
        if(!TEXT_SIZES.some(x=>x[0]===value))return;
        const before=this.root.dataset.fontSize||'default';this.root.dataset.fontSize=value;this.fontControl.update(value);
        if(save)try{this.data.preferences=await request('preferences',{font_size:value},{method:'PATCH'});}
        catch(error){this.root.dataset.fontSize=before;this.fontControl.update(before);this.message(error.message,true);}
    }
    message(text,error=false) {this.notice.textContent=text;this.notice.dataset.error=String(error);}
    resources(data) {
        const reconnect=this.disconnected&&!!data;
        this.disconnected=!data;
        launchMessage("connection",data?"online":"offline");
        if(reconnect&&this.content.querySelector('[data-connection-error="true"]'))this.retryView?.();
        const wasRunning=this.status?.running;
        this.status=data;
        this.vram.update(data?.vram_used,data?.vram_total);
        this.ram.update(data?.ram_used,data?.ram_total);
        this.cpu.update(data?.cpu_percent,100);
        const residency=loadedState(data);
        this.loadedDot.dataset.state=residency.state;this.loadedLabel.textContent=residency.label;
        this.activity.update(activityState(this.unloading?{...data,resource_cleanup:{status:"releasing"}}:data));
        this.unload.disabled=!data||data.running||this.unloading;
        this.unload.title=data?.running?"Wait for the current run to finish":"Release loaded models and reusable model caches";
        this.updates?.refreshFlag();for(const listener of this.statusListeners)listener();
        if(wasRunning&&!data?.running&&this.data)request("library/sync",{}).catch(e=>this.message(e.message,true));
    }
    async unloadModels() {
        this.unloading=true;this.resources(this.status);
        try{await request("/asset-workshop/release",{});this.message("Models unloaded. The resource readings will update shortly.");}
        catch(error){this.message(error.message,true);}
        finally{this.unloading=false;this.resources(this.status);}
    }
    async openImages(section="Create Images") {
        this.imageSection=section;
        await this.open("Images");
    }
    async open(name) {
        if(name!=='Images'&&this.imageOrigin?.method==='ccore-image')delete this.imageOrigin;
        this.retryView=()=>this.open(name);
        this.viewDispose?.();this.viewDispose=null;
        this.tab=name;this.sequence=(this.sequence||0)+1;const sequence=this.sequence;
        [...this.nav.children].forEach((n,i)=>{n.setAttribute("aria-selected",String(this.tabs[i]===name));n.tabIndex=this.tabs[i]===name?0:-1;});
        this.content.setAttribute("aria-label",name);this.content.scrollTop=0;
        if(name==="Choose a Workflow"){this.content.replaceChildren(home(this));return;}
        this.content.replaceChildren(el("p",{class:"muted"},"Loading "+name.toLowerCase()+"…"));
        try {
            const files={"About":"about","History":"library","Images":"images","Integrations":"integrations","Roadmap":"roadmap"};
            const module=await import("./views/"+files[name]+".js");
            if(sequence!==this.sequence)return;
            const view=await module.render(this,"mesh");
            if(sequence!==this.sequence){view.dispose?.();return;}
            this.content.replaceChildren(view.element||view);this.viewDispose=view.dispose;
        } catch(error) {if(sequence===this.sequence)this.content.replaceChildren(el("p",{"data-connection-error":String(error.code==="FOUNDRY_OFFLINE")},error.message),button("Retry",()=>this.open(name)));}
    }

    async openWizard({resume=false,runId=null,method="turnaround"}={}){
        this.retryView=()=>this.openWizard({resume,runId,method});
        this.viewDispose?.();this.viewDispose=null;this.sequence=(this.sequence||0)+1;
        const sequence=this.sequence;
        this.tab="Choose a Workflow";
        this.content.replaceChildren(el("p",{},"Opening the image-to-3D workflow…"));
        let wizard;
        try{
            const {Wizard}=await import("./wizard/controller.js");
            wizard=new Wizard(this,{resume,runId,method});
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return;}
            this.content.replaceChildren(element);
            this.content.scrollTop=0;
            [...this.nav.children].forEach((n,i)=>{n.setAttribute("aria-selected",String(i===0));n.tabIndex=i===0?0:-1;});
            this.content.setAttribute("aria-label","Image to 3D wizard");
            this.viewDispose=()=>wizard.dispose();
            this.wizard=wizard;
        }catch(error){wizard?.dispose();this.content.replaceChildren(el("p",{role:"alert","data-connection-error":String(error.code==="FOUNDRY_OFFLINE")},error.message));}
    }

    async chooseMesh(handoff,origin){
        if(origin?.method==='single-image'){
            await this.openWizard({resume:true,method:'single-image'});
            Object.assign(this.wizard.draft,{name:handoff.name,references:handoff.references.slice(0,1),image_creation:handoff.image_creation});
            this.wizard.runId=null;this.wizard.run=null;this.wizard.go(1);return;
        }
        this.pendingMeshHandoff=handoff;this.meshOrigin=origin;
        return this.open('Choose a Workflow');
    }
    async guidedLive(requestId,jobId=this.node.properties.foundryGuided?.id){
        if(this.node.graph!==app.graph||!this.host.isConnected)return;
        if(requestId)this.guidedBinding=requestId;
        return request('guided/live',{selected:true,job_id:jobId||null,client_id:api.clientId||'',
            workflow:app.extensionManager.workflow.activeWorkflow.path,request_id:this.guidedBinding||null});
    }
    async bindGuided(data){
        if(this.node.graph!==app.graph||!this.host.isConnected||data.job_id&&data.job_id!==this.node.properties.foundryGuided?.id)return;
        syncGuidedBranch(data.canvas_graph||data.graph,this.node,{offset:data.offset||(data.finishing?200000:100000),replace:!data.finishing});
        syncGuidedOutputs(data.saved_outputs,this.node);
        await this.guidedLive(data.request_id);
    }
    async openMeshMethod(method){
        const handoff=this.pendingMeshHandoff;
        if(method==='single'){await this.openWizard({method:'single-image',resume:!!this.meshOrigin});if(handoff){Object.assign(this.wizard.draft,{name:handoff.name,references:handoff.references.slice(0,1),image_creation:handoff.image_creation});this.wizard.go(1);}}
        else if(method==='splat'){
            if(await this.openSplatWizard({handoff})===false)return;
        }
        else if(method==='guided'){
            if(await this.openGuidedWizard({handoff})===false)return;
        }
        else{
            await this.openWizard({resume:!!this.meshOrigin});
            const w=this.wizard;
            if(handoff&&w){Object.assign(w.draft,{name:handoff.name,category:handoff.category,references:handoff.references,image_creation:handoff.image_creation});w.runId=null;w.run=null;w.go(1);}
        }
        this.pendingMeshHandoff=null;this.meshOrigin=null;
    }
    async openGuidedWizard(options={}){
        const current=this.node.properties?.foundryGuided?.id;
        if(current&&!options.resume){
            try{
                const run=await request('guided/runs/'+current);
                if(run.active||run.preparing||run.finishing?.active){
                    this.message('The current 3D-Guided asset is still running. Resume it, or wait before starting another object.',true);
                    return false;
                }
            }catch(error){this.message(error.message,true);return false;}
        }
        this.viewDispose?.();this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;
        this.tab='Choose a Workflow';this.content.replaceChildren(hint('Opening the independent 3D-Guided workflow…'));
        let wizard;
        try{
            const {GuidedWizard}=await import('./guided/controller.js');wizard=new GuidedWizard(this,options);
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return;}
            this.content.replaceChildren(element);this.content.scrollTop=0;this.guidedWizard=wizard;
            this.viewDispose=()=>wizard.dispose();this.content.setAttribute('aria-label','3D-Guided wizard');
            [...this.nav.children].forEach((n,i)=>n.setAttribute('aria-selected',String(i===0)));
            return true;
        }catch(error){wizard?.dispose();this.content.replaceChildren(el('p',{role:'alert'},error.message));return false;}
    }

    async openSplatWizard(options={}) {
        const current=this.node.properties.foundrySplat?.runId;
        if(current&&!options.resume){
            const active=await request('splat/runs/'+current);
            if(active.active){this.message('Resume the running splat asset before starting another.',true);return false;}
        }
        this.viewDispose?.();this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;this.tab='Choose a Workflow';
        this.content.replaceChildren(hint('Opening Splat & Solid…'));
        let wizard;
        try {
            const {SplatWizard}=await import('./splat/controller.js');wizard=new SplatWizard(this,options);
            const element=await wizard.init();if(sequence!==this.sequence){wizard.dispose();return false;}
            this.content.replaceChildren(element);this.content.scrollTop=0;this.splatWizard=wizard;
            this.viewDispose=()=>wizard.dispose();this.content.setAttribute('aria-label','Splat & Solid wizard');return true;
        } catch(error){wizard?.dispose();this.content.replaceChildren(el('p',{role:'alert'},error.message));return false;}
    }

    async openCcoreWizard(options={}) {
        if(this.imageOrigin?.method==='ccore-image')delete this.imageOrigin;
        this.viewDispose?.();
        this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;
        this.tab='Choose a Workflow';
        this.content.replaceChildren(hint('Opening the CCORE prop workflow…'));
        let wizard;
        try {
            const {CcoreWizard}=await import('./ccore/controller.js');
            wizard=new CcoreWizard(this,options);
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return;}
            this.content.replaceChildren(element);
            this.content.scrollTop=0;
            this.content.setAttribute('aria-label',options.image?'CCORE Image + Text wizard':'CCORE text-only prop wizard');
            this.viewDispose=()=>wizard.dispose();
            [...this.nav.children].forEach((node,index)=>node.setAttribute('aria-selected',String(index===0)));
        } catch(error) {
            wizard?.dispose();
            if(sequence===this.sequence)this.content.replaceChildren(el('p',{role:'alert'},error.message));
        }
    }

    async openHairWizard(options={}) {
        this.viewDispose?.();this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;
        this.tab='Choose a Workflow';this.content.replaceChildren(hint('Opening the HairDeck workflow…'));
        try{
            const {HairWizard}=await import('./hair/controller.js');
            const {ensureHairBranch}=await import('./hair/graph.js');
            const capabilities=await request('hair/capabilities');
            const {presentation}=await import('./app-mode.js');const inApp=presentation.current===this.node;
            if(capabilities.graph_template&&await ensureHairBranch(capabilities.graph_template)){
                const node=app.graph.getNodeById(this.node.id);
                if(!node?.shell)throw Error('The updated HairDeck graph did not reopen its Foundry interface.');
                await node.shell.openHairWizard(options);if(inApp)presentation.show(node);return;
            }
            const wizard=new HairWizard(this,{...options,capabilities});
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return;}
            this.content.replaceChildren(element);this.content.scrollTop=0;this.hairWizard=wizard;
            this.viewDispose=()=>wizard.dispose();this.content.setAttribute('aria-label','HairDeck creation wizard');
            [...this.nav.children].forEach((n,i)=>n.setAttribute('aria-selected',String(i===0)));
        }catch(error){this.content.replaceChildren(el('p',{role:'alert'},error.message));}
    }

    async settings(options={}) {
        try{const module=await import("./views/settings.js");return module.render(this,options);}
        catch(error){this.message(error.message,true);}
    }
    dispose() {this.fontControl.dispose();this.statusListeners.clear();api.removeEventListener('mumblebox-foundry-splat',this.agentSplatHandler);clearInterval(this.guidedHeartbeat);api.removeEventListener('guided.bind',this.guidedBindHandler);this.stopTextClipboard?.();this.updates.dispose();api.removeEventListener("mumblebox-foundry-run",this.agentRunHandler);api.removeEventListener('mumblebox-foundry-image',this.agentImageHandler);api.removeEventListener('mumblebox-foundry-hair',this.agentHairHandler);this.stopPolling?.();this.viewDispose?.();this.imageCreator?.dispose();this.activeDialog?.close();this.root.remove();this.sequence++;}
}
