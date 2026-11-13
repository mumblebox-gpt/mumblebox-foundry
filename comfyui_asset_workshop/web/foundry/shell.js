import {sourceMessage} from "./i18n.js";
import {languages as supportedLanguages, setLanguage as activateLanguage, currentLanguage, onLanguageChange} from "./i18n.js";
import {msg, setText, bindAttribute, replaceContent} from "./i18n.js";
import {fontControl,TEXT_SIZES} from './typography.js';
import {el,button,icon,hint} from "./dom.js";
import {activityState,loadedState} from "./activity-state.js";
import {activity} from "./activity.js";
import {UpdateChecks} from "./updates.js";
import {AgentSetup} from "./agent-setup/controller.js";
import {resourceMeter} from "./telemetry.js";
import {request,pollResources} from "./services.js";
import {dialog} from "./dialogs.js";
import {home} from "./views/home.js";
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
        for (const file of ["theme.css","layout.css","images.css","roadmap.css","agent-setup/style.css","virtual-turntable/style.css"]) this.shadow.append(el("link",{rel:"stylesheet",href:new URL(file,import.meta.url).href}));
        this.root=el("div",{class:"foundry","data-theme":matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light"});
        this.shadow.append(this.root);
        this.root.lang=currentLanguage();
        this.stopLanguage=onLanguageChange(locale=>{
            this.root.lang=locale;
            if(this.language)this.language.value=locale;
            if(this.status)this.resources(this.status);
        });
        this.stopTextClipboard=installTextClipboard(this.root);
        // OrbitControls receives pointerup at the shadow root. Let releases
        // reach it; swallowing them leaves the viewer stuck in a drag.
        for(const event of ["pointerdown","click","dblclick","wheel","keydown","contextmenu"])
            this.root.addEventListener(event,e=>e.stopPropagation());
        this.agentSetup=new AgentSetup(this);
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
        this.agentWorkflowHandlers = {
            'mumblebox-foundry-ccore': data => this.openCcoreWizard({runId:data.id,image:data.with_image}),
            'mumblebox-foundry-turntable': data => this.openVirtualTurntable({runId:data.id}),
            'mumblebox-foundry-orbit': data => this.openOrbitToMesh({runId:data.id}),
            'mumblebox-foundry-garment': data => this.openGarmentWizard({runId:data.id}),
            'mumblebox-foundry-guided': data => this.openGuidedWizard({runId:data.id,binding:data.request_id}),
            'mumblebox-foundry-workspace': data => this.openAgentSection(data.section),
        };
        for (const [eventName, show] of Object.entries(this.agentWorkflowHandlers)) {
            const listener = event => {
                if (this.node.graph !== app.graph || !this.host.isConnected) return;
                if (eventName !== 'mumblebox-foundry-workspace' && !/^[a-f0-9]{32}$/.test(event.detail?.id || '')) return;
                show(event.detail).catch(error => this.message(sourceMessage(error.message), true));
            };
            this.agentWorkflowHandlers[eventName] = listener;
            api.addEventListener(eventName, listener);
        }
        // Native processing belongs to the selected graph, not a particular
        // wizard page. Navigation within Foundry must not disconnect Rocket.
        this.guidedBindHandler=e=>this.bindGuided(e.detail).catch(error=>this.message(sourceMessage(error.message),true));
        api.addEventListener('guided.bind',this.guidedBindHandler);
        this.guidedHeartbeat=setInterval(()=>{
            if(this.node.properties.foundryGuided?.id)this.guidedLive().catch(()=>{});
        },15000);
    }
    build() {
        this.version=el("small",{},msg("common.interface_loading"));
        this.previewRelease=el("strong",{class:"preview-release",hidden:true},msg("common.preview_release"));
        this.language=el("select", {class:"language", "aria-label":msg("common.language"),
            onchange:event=>this.setLanguage(event.target.value)},
            ...supportedLanguages.map(language=>el("option", {value:language.id}, language.label)));
        this.themeButton=button([icon("contrast",18),msg("common.theme")],()=>this.setTheme(this.root.dataset.theme==="dark"?"light":"dark"));
        bindAttribute(this.themeButton,"aria-label",msg("common.switch_color_theme"));
        this.fontControl=fontControl(this);
        this.updateSlot=el("div",{class:"header-update",role:"status","aria-live":"polite"});
        this.settingsButton=button([icon("gear",18),msg("common.settings")],()=>this.settings());
        const donate=button(msg("common.coffee"),()=>{}, {disabled:true,title:msg("common.coffee_link_coming_soon")});
        const identity=el("div",{class:"identity"},el("div",{class:"brand"},el("div",{class:"brand-lockup"},
            el("h1",{},el("img",{class:"brand-logo",src:new URL("../assets/foundry/logo-approved.png",import.meta.url).href,alt:msg("common.mumblebox_3d_asset_foundry"),width:2172,height:724})),
            el("div",{class:"brand-version"},this.previewRelease,this.version))),
            el("div",{class:"header-tools"},el("div",{class:"header-actions"},el("div",{class:"language-picker"},icon("globe",20),this.language),this.themeButton,this.agentSetup.header,this.fontControl.element,this.settingsButton,donate),this.updateSlot));
        this.vram=resourceMeter("VRAM");this.ram=resourceMeter("RAM");this.cpu=resourceMeter("CPU",{percent:true});
        this.loadedDot=el("span",{class:"loaded-dot","aria-hidden":"true"});
        this.loadedLabel=el("small",{"aria-live":"polite"},msg("common.model_state_unavailable"));
        this.unload=button([this.loadedDot,msg("common.unload_models")],()=>this.unloadModels(),{disabled:true});
        this.activity=activity();
        this.resourceBar=el("div",{class:"resources"},this.vram.element,this.ram.element,this.cpu.element,
            this.activity.element,el("div",{class:"model-residency"},this.unload,this.loadedLabel));
        this.nav=el("nav",{class:"tabs",role:"tablist","aria-label":msg("common.foundry_sections")});
        this.tabs=["Choose a Workflow","Images","History","Integrations","About","Roadmap"];
        const tabLabels=["choose_a_workflow","images","history","integrations","about","roadmap"];
        this.tabs.forEach((name,i)=>this.nav.append(button([icon(["cube","image","history","plug","info","map"][i],16),msg("common."+tabLabels[i])],()=>this.open(name),{class:i===2?"secondary-start":"",role:"tab","aria-selected":name===this.tab,tabindex:name===this.tab?0:-1})));
        this.nav.addEventListener("keydown",e=>{
            if(!["ArrowRight","ArrowLeft","Home","End"].includes(e.key))return;
            e.preventDefault();
            const index=this.tabs.indexOf(this.tab);
            const next=e.key==="Home"?0:e.key==="End"?this.tabs.length-1:(index+(e.key==="ArrowRight"?1:-1)+this.tabs.length)%this.tabs.length;
            this.open(this.tabs[next]);this.nav.children[next].focus();
        });
        this.content=el("main",{class:"content",role:"tabpanel","aria-label":this.tab});
        this.notice=el("div",{class:"status",role:"status","aria-live":"polite"},msg("common.loading_foundry_services"));
        this.root.append(el("header",{class:"top"},identity,this.resourceBar),this.nav,this.content,this.notice);
        this.resources(null);this.open(this.tab);
    }
    async bootstrap() {
        try {
            this.data=await request("bootstrap");
            activateLanguage(this.data.preferences.language);
            if(!this.node.graph._nodes.some(n=>n.properties?.guidedOwner===this.node.id))
                syncGuidedBranch(await request('guided/template'),this.node);
            setText(this.version, "v"+this.data.version);
            this.previewRelease.hidden=!/-preview(?:\.|$)/i.test(this.data.version);
            await this.setFontSize(this.data.preferences.font_size||"default",false);
            this.root.dataset.motion=this.data.preferences.busy_motion||"system";
            if(this.data.preferences.theme) await this.setTheme(this.data.preferences.theme,false);
            else await this.setTheme(this.root.dataset.theme,false);
            this.message(msg("common.local_workspace_image_to_3d_workflow"));
            this.open(this.tab);
            this.updates.startup();
        } catch(error) {this.message(sourceMessage(error.message),true);}
    }
    async setLanguage(locale) {
        const previous=currentLanguage();
        this.language.disabled=true;
        try {
            this.data.preferences=await request("preferences",{language:locale},{method:"PATCH"});
            activateLanguage(this.data.preferences.language);
        } catch(error) {
            this.language.value=previous;
            this.message(sourceMessage(error.message),true);
        } finally {
            this.language.disabled=false;
        }
    }
    async setTheme(theme,save=true) {
        this.root.dataset.theme=theme;
        bindAttribute(this.themeButton, "title", theme==="dark"?msg("common.switch_to_light_theme"):msg("common.switch_to_dark_theme"));
        this.themeButton.setAttribute("aria-pressed",String(theme==="dark"));
        if(save)try{await request("preferences",{theme},{method:"PATCH"});}catch(e){this.message(sourceMessage(e.message),true);}
    }
    async setFontSize(value,save=true){
        if(!TEXT_SIZES.some(x=>x[0]===value))return;
        const before=this.root.dataset.fontSize||'default';this.root.dataset.fontSize=value;this.fontControl.update(value);
        if(save)try{this.data.preferences=await request('preferences',{font_size:value},{method:'PATCH'});}
        catch(error){this.root.dataset.fontSize=before;this.fontControl.update(before);this.message(sourceMessage(error.message),true);}
    }
    message(text,error=false) {setText(this.notice, text);this.notice.dataset.error=String(error);}
    resources(data) {
        const reconnect=this.disconnected&&!!data;
        this.disconnected=!data;
        launchMessage("connection",data?"online":"offline");
        if(reconnect&&this.content.querySelector('[data-connection-error="true"]'))this.retryView?.();
        const wasRunning=this.status?.running;
        this.status=data;
        this.agentSetup.update(data?.agent_presence);
        this.vram.update(data?.vram_used,data?.vram_total);
        this.ram.update(data?.ram_used,data?.ram_total);
        this.cpu.update(data?.cpu_percent,100);
        const residency=loadedState(data);
        this.loadedDot.dataset.state=residency.state;
        if(this.loadedLabel.textContent!==residency.label)setText(this.loadedLabel, residency.label);
        this.activity.update(activityState(this.unloading?{...data,resource_cleanup:{status:"releasing"}}:data));
        this.unload.disabled=!data||data.running||this.unloading;
        bindAttribute(this.unload, "title", data?.running?msg("common.wait_for_the_current_run_to_finish"):msg("common.release_loaded_models_and_reusable_model_caches"));
        this.updates?.refreshFlag();for(const listener of this.statusListeners)listener();
        if(wasRunning&&!data?.running&&this.data)request("library/sync",{}).catch(e=>this.message(sourceMessage(e.message),true));
    }
    async unloadModels() {
        this.unloading=true;this.resources(this.status);
        try{await request("/asset-workshop/release",{});this.message(msg("common.models_unloaded_the_resource_readings_will_update_shortly"));}
        catch(error){this.message(sourceMessage(error.message),true);}
        finally{this.unloading=false;this.resources(this.status);}
    }
    async openAgentSection(section) {
        if (section === "settings") {
            this.data = await request("bootstrap");
            return this.settings();
        }
        if (section === "images" || section === "gallery") {
            return this.openImages(section === "gallery" ? "Gallery" : "Create Images");
        }
        const sections = {workflow:"Choose a Workflow", history:"History", integrations:"Integrations", about:"About", roadmap:"Roadmap"};
        if (Object.hasOwn(sections, section)) return this.open(sections[section]);
    }
    async openImages(section="Create Images") {
        this.imageSection=section;
        await this.open("Images");
    }
    async open(name) {
        if(name!=='Images'&&['ccore-image','virtual-turntable','orbit-to-mesh'].includes(this.imageOrigin?.method))delete this.imageOrigin;
        this.retryView=()=>this.open(name);
        this.viewDispose?.();this.viewDispose=null;
        this.tab=name;this.sequence=(this.sequence||0)+1;const sequence=this.sequence;
        [...this.nav.children].forEach((n,i)=>{n.setAttribute("aria-selected",String(this.tabs[i]===name));n.tabIndex=this.tabs[i]===name?0:-1;});
        const label=msg("common."+({
            "Choose a Workflow":"choose_a_workflow",Images:"images",History:"history",Integrations:"integrations",About:"about",Roadmap:"roadmap"
        })[name]);
        bindAttribute(this.content,"aria-label",label);this.content.scrollTop=0;
        if(name==="Choose a Workflow"){this.content.replaceChildren(home(this));return;}
        replaceContent(this.content, el("p",{class:"muted"},msg("common.loading", {value1:label})));
        try {
            const files={"About":"about","History":"library","Images":"images","Integrations":"integrations","Roadmap":"roadmap"};
            const module=await import("./views/"+files[name]+".js");
            if(sequence!==this.sequence)return;
            const view=await module.render(this,"mesh");
            if(sequence!==this.sequence){view.dispose?.();return;}
            this.content.replaceChildren(view.element||view);this.viewDispose=view.dispose;
        } catch(error) {if(sequence===this.sequence)replaceContent(this.content, el("p",{"data-connection-error":String(error.code==="FOUNDRY_OFFLINE")},sourceMessage(error.message)), button(msg("common.retry"),()=>this.open(name)));}
    }

    async openWizard({resume=false,runId=null,method="turnaround"}={}){
        this.retryView=()=>this.openWizard({resume,runId,method});
        this.viewDispose?.();this.viewDispose=null;this.sequence=(this.sequence||0)+1;
        const sequence=this.sequence;
        this.tab="Choose a Workflow";
        replaceContent(this.content, el("p",{},msg("common.opening_the_image_to_3d_workflow")));
        let wizard;
        try{
            const {Wizard}=await import("./wizard/controller.js");
            wizard=new Wizard(this,{resume,runId,method});
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return;}
            this.content.replaceChildren(element);
            this.content.scrollTop=0;
            [...this.nav.children].forEach((n,i)=>{n.setAttribute("aria-selected",String(i===0));n.tabIndex=i===0?0:-1;});
            bindAttribute(this.content, "aria-label", msg("common.image_to_3d_wizard"));
            this.viewDispose=()=>wizard.dispose();
            this.wizard=wizard;
        }catch(error){wizard?.dispose();this.content.replaceChildren(el("p",{role:"alert","data-connection-error":String(error.code==="FOUNDRY_OFFLINE")},sourceMessage(error.message)));}
    }

    async chooseMesh(handoff,origin){
        if(origin?.method==='orbit-to-mesh')return this.openOrbitToMesh({resume:true,handoff});
        if(origin?.method==='virtual-turntable'){
            return this.openVirtualTurntable({resume:true,handoff});
        }
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
        else if(method==='orbit-to-mesh'){
            if(await this.openOrbitToMesh({handoff})===false)return;
        }
        else if(method==='virtual-turntable'){
            if(await this.openVirtualTurntable({handoff})===false)return;
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
        if(current&&!options.resume&&current!==options.runId){
            try{
                const run=await request('guided/runs/'+current);
                if(run.active||run.preparing||run.finishing?.active){
                    this.message(msg("common.the_current_3d_guided_asset_is_still_running_resume_it_or_wait_before_starti"),true);
                    return false;
                }
            }catch(error){this.message(sourceMessage(error.message),true);return false;}
        }
        this.viewDispose?.();this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;
        this.tab='Choose a Workflow';replaceContent(this.content, hint(msg("common.opening_the_independent_3d_guided_workflow")));
        let wizard;
        try{
            const {GuidedWizard}=await import('./guided/controller.js');wizard=new GuidedWizard(this,options);
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return;}
            this.content.replaceChildren(element);this.content.scrollTop=0;this.guidedWizard=wizard;
            this.viewDispose=()=>wizard.dispose();bindAttribute(this.content, 'aria-label', msg("common.3d_guided_wizard"));
            [...this.nav.children].forEach((n,i)=>n.setAttribute('aria-selected',String(i===0)));
            return true;
        }catch(error){wizard?.dispose();this.content.replaceChildren(el('p',{role:'alert'},sourceMessage(error.message)));return false;}
    }

    openVirtualTurntable(options={}){
        return this.openOrbitWizard(options,false);
    }

    openOrbitToMesh(options={}){
        return this.openOrbitWizard(options,true);
    }

    async openOrbitWizard(options,orbit){
        const key=orbit?'orbit-to-mesh':'virtual-turntable';
        const title=orbit?'Orbit to Mesh':'Virtual Turntable';
        if(this.imageOrigin?.method===key)delete this.imageOrigin;
        this.viewDispose?.();
        this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;
        this.tab='Choose a Workflow';
        replaceContent(this.content,hint(orbit?msg('orbit.opening'):sourceMessage('Opening Virtual Turntable')));
        let wizard;
        try{
            const Wizard=orbit?(await import('./orbit-to-mesh/controller.js')).OrbitToMeshWizard:
                (await import('./virtual-turntable/controller.js')).VirtualTurntableWizard;
            wizard=new Wizard(this,options);
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return false;}
            this.content.replaceChildren(element);
            this.content.scrollTop=0;
            this.viewDispose=()=>wizard.dispose();
            bindAttribute(this.content,'aria-label',orbit?msg('orbit.wizard'):sourceMessage(title+' wizard'));
            [...this.nav.children].forEach((node,index)=>node.setAttribute('aria-selected',String(index===0)));
            return true;
        }catch(error){
            wizard?.dispose();
            if(sequence===this.sequence)this.content.replaceChildren(el('p',{role:'alert'},sourceMessage(error.message)));
            return false;
        }
    }

    async openSplatWizard(options={}) {
        const current=this.node.properties.foundrySplat?.runId;
        if(current&&!options.resume){
            const active=await request('splat/runs/'+current);
            if(active.active){this.message(msg("common.resume_the_running_splat_asset_before_starting_another"),true);return false;}
        }
        this.viewDispose?.();this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;this.tab='Choose a Workflow';
        replaceContent(this.content, hint(msg("common.opening_splat_solid")));
        let wizard;
        try {
            const {SplatWizard}=await import('./splat/controller.js');wizard=new SplatWizard(this,options);
            const element=await wizard.init();if(sequence!==this.sequence){wizard.dispose();return false;}
            this.content.replaceChildren(element);this.content.scrollTop=0;this.splatWizard=wizard;
            this.viewDispose=()=>wizard.dispose();bindAttribute(this.content, 'aria-label', msg("common.splat_solid_wizard"));return true;
        } catch(error){wizard?.dispose();this.content.replaceChildren(el('p',{role:'alert'},sourceMessage(error.message)));return false;}
    }

    async openCcoreWizard(options={}) {
        if(this.imageOrigin?.method==='ccore-image')delete this.imageOrigin;
        this.viewDispose?.();
        this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;
        this.tab='Choose a Workflow';
        replaceContent(this.content, hint(msg("common.opening_the_ccore_prop_workflow")));
        let wizard;
        try {
            const {CcoreWizard}=await import('./ccore/controller.js');
            wizard=new CcoreWizard(this,options);
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return;}
            this.content.replaceChildren(element);
            this.content.scrollTop=0;
            bindAttribute(this.content, 'aria-label', options.image?msg("common.ccore_image_text_wizard"):msg("common.ccore_text_only_prop_wizard"));
            this.viewDispose=()=>wizard.dispose();
            [...this.nav.children].forEach((node,index)=>node.setAttribute('aria-selected',String(index===0)));
        } catch(error) {
            wizard?.dispose();
            if(sequence===this.sequence)this.content.replaceChildren(el('p',{role:'alert'},sourceMessage(error.message)));
        }
    }

    async openGarmentWizard(options = {}) {
        this.viewDispose?.();
        this.viewDispose = null;
        const sequence = this.sequence = (this.sequence || 0) + 1;
        this.tab = 'Choose a Workflow';
        replaceContent(this.content, hint(msg("common.opening_garment_particles")));
        let wizard;
        try {
            const {GarmentWizard} = await import('./garment/controller.js');
            wizard = new GarmentWizard(this, options);
            const element = await wizard.init();
            if (sequence !== this.sequence) {wizard.dispose();return;}
            this.content.replaceChildren(element);
            this.content.scrollTop = 0;
            bindAttribute(this.content, 'aria-label', msg("common.garment_particles_wizard"));
            this.viewDispose = () => wizard.dispose();
            [...this.nav.children].forEach((node, index) => node.setAttribute('aria-selected', String(index === 0)));
        } catch (error) {
            wizard?.dispose();
            if (sequence === this.sequence) this.content.replaceChildren(el('p', {role:'alert'}, sourceMessage(error.message)));
        }
    }

    async openHairWizard(options={}) {
        this.viewDispose?.();this.viewDispose=null;
        const sequence=this.sequence=(this.sequence||0)+1;
        this.tab='Choose a Workflow';replaceContent(this.content, hint(msg("common.opening_the_hairdeck_workflow")));
        try{
            const {HairWizard}=await import('./hair/controller.js');
            const {ensureHairBranch}=await import('./hair/graph.js');
            const capabilities=await request('hair/capabilities');
            const {presentation}=await import('./app-mode.js');const inApp=presentation.current===this.node;
            if(capabilities.graph_template&&await ensureHairBranch(capabilities.graph_template)){
                const node=app.graph.getNodeById(this.node.id);
                if(!node?.shell)throw Error(msg("common.the_updated_hairdeck_graph_did_not_reopen_its_foundry_interface"));
                await node.shell.openHairWizard(options);if(inApp)presentation.show(node);return;
            }
            const wizard=new HairWizard(this,{...options,capabilities});
            const element=await wizard.init();
            if(sequence!==this.sequence){wizard.dispose();return;}
            this.content.replaceChildren(element);this.content.scrollTop=0;this.hairWizard=wizard;
            this.viewDispose=()=>wizard.dispose();bindAttribute(this.content, 'aria-label', msg("common.hairdeck_creation_wizard"));
            [...this.nav.children].forEach((n,i)=>n.setAttribute('aria-selected',String(i===0)));
        }catch(error){this.content.replaceChildren(el('p',{role:'alert'},sourceMessage(error.message)));}
    }

    async settings(options={}) {
        try{const module=await import("./views/settings.js");return module.render(this,options);}
        catch(error){this.message(sourceMessage(error.message),true);}
    }
    dispose() {this.stopLanguage?.();for(const [name,listener] of Object.entries(this.agentWorkflowHandlers))api.removeEventListener(name,listener);this.fontControl.dispose();this.statusListeners.clear();api.removeEventListener('mumblebox-foundry-splat',this.agentSplatHandler);clearInterval(this.guidedHeartbeat);api.removeEventListener('guided.bind',this.guidedBindHandler);this.stopTextClipboard?.();this.updates.dispose();api.removeEventListener("mumblebox-foundry-run",this.agentRunHandler);api.removeEventListener('mumblebox-foundry-image',this.agentImageHandler);api.removeEventListener('mumblebox-foundry-hair',this.agentHairHandler);this.stopPolling?.();this.viewDispose?.();this.imageCreator?.dispose();this.activeDialog?.close();this.root.remove();this.sequence++;}
}
