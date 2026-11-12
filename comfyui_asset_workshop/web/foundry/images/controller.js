import {sourceMessage} from "../i18n.js";
import {msg, setText} from "../i18n.js";
import {api} from '/scripts/api.js';
import {app} from '/scripts/app.js';
import {el} from '../dom.js';
import {request} from '../services.js';
import {creator} from './creator.js';
import {showImageStage} from './graph.js';

export function creatorOrigin(shell){
    const method=shell.imageOrigin?.method;
    return !shell.openImageId&&['single-image','ccore-image','virtual-turntable','orbit-to-mesh'].includes(method)?method:'';
}

export class ImageCreator{
    constructor(shell){
        this.shell=shell;this.node=shell.node;this.host=el('section',{class:'image-creator','aria-label':msg("images.image_creator")});
        this.origin=creatorOrigin(shell);
        this.singleOrigin=Boolean(this.origin);
        this.ccoreOrigin=this.origin==='ccore-image';
        this.turntableOrigin=this.origin==='virtual-turntable';
        this.orbitOrigin=this.origin==='orbit-to-mesh';
        this.stateProperty=this.orbitOrigin?'foundryImageCreatorOrbit':this.turntableOrigin?'foundryImageCreatorTurntable':this.ccoreOrigin?'foundryImageCreatorCcore':this.singleOrigin?'foundryImageCreatorSingle':'foundryImageCreator';
        this.storageKey='foundry-image-creator:'+app.extensionManager.workflow.activeWorkflow.path+':'+this.node.id+
            (this.orbitOrigin?':orbit-to-mesh':this.turntableOrigin?':virtual-turntable':this.ccoreOrigin?':ccore':this.singleOrigin?':single':'');
        let saved=this.node.properties[this.stateProperty]||{};
        try{const local=JSON.parse(localStorage.getItem(this.storageKey)||'null');if(local?.updated>(saved.updated||0))saved=local;}catch{}
        // Restored Comfy node properties may be reactive proxies, not cloneable objects.
        this.draft=JSON.parse(JSON.stringify(saved.draft||{name:'Untitled image',category:this.singleOrigin?'general':'characters',model:'klein4',description:'',front:'',back:'',references:[],loras:[],settings:{seed:-1}}));
        if(this.singleOrigin)this.draft.category='general';
        this.openedSaved=!!shell.openImageId;this.id=shell.openImageId||saved.id;delete shell.openImageId;
        this.progress=e=>{if(this.run?.active&&(!e.detail?.prompt_id||e.detail.prompt_id===this.run.pending?.prompt_id)&&this.progressText)
            setText(this.progressText, msg("images.sampling_of", {value1: e.detail.value, max: e.detail.max}));};
        api.addEventListener('progress',this.progress);
    }
    async init(){
        [this.cap,this.loras,this.checkpoints]=await Promise.all([request('images/capabilities'),
            request('/asset-workshop/v2/loras'),request('/asset-workshop/v2/civitai/installed')]);
        if(this.id){try{this.run=await request('images/'+this.id);if(this.openedSaved||!this.draft.description&&!this.draft.references.length)this.draft=structuredClone(this.run.config);}catch(error){this.id=null;this.error=error.message;}}
        this.render();this.poll();return this.host;
    }
    model(){return this.cap.models.find(m=>m.id===this.draft.model)||this.cap.models[0];}
    paired(){return this.cap.categories.find(c=>c.id===this.draft.category)?.paired;}
    referenceLimit(){return this.model()[this.paired()?'pair_references':'single_references'];}
    remember(){
        const state={id:this.id,draft:structuredClone(this.draft),updated:Date.now()};
        this.node.properties[this.stateProperty]=state;
        try{localStorage.setItem(this.storageKey,JSON.stringify(state));}catch{}
    }
    detach(){this.detached=true;this.observer?.disconnect();this.remember();}
    attach(){this.detached=false;this.render();return this.host;}
    render(){
        if(this.disposed||this.detached)return;
        this.observer?.disconnect();this.host.replaceChildren(creator(this));
        this.observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){
            this.host.querySelectorAll('.creator-rail button').forEach(b=>b.setAttribute('aria-current',String(b.dataset.section===entry.target.id)));
        }},{root:this.shell.content,rootMargin:'-5% 0px -65% 0px'});
        this.host.querySelectorAll('.creator-section').forEach(s=>this.observer.observe(s));
    }
    async act(action){
        if(this.working)return;this.working=true;this.error='';
        try{return await action();}catch(error){this.error=error.message;this.shell.message(sourceMessage(error.message),true);}
        finally{this.working=false;this.remember();this.render();}
    }
    async configure(){
        if(this.singleOrigin)this.draft.category='general';
        const payload=this.ccoreOrigin&&!this.id?{...this.draft,graph_scope:'ccore-reference'}:this.draft;
        this.run=await request(this.id?'images/'+this.id:'images',payload,this.id?{method:'PATCH'}:{});
        this.id=this.run.id;this.draft=structuredClone(this.run.config);this.remember();
    }
    async generate(operation='generate'){await this.configure();this.run=await request('images/'+this.id+'/start',{request_id:crypto.randomUUID(),client_id:api.clientId||'',operation});this.render();}
    async poll(){
        if(this.disposed)return;
        try{if(this.id){const run=await request('images/'+this.id);if(this.disposed)return;
            const changed=JSON.stringify([run.status,run.active,run.stage,run.accepted,run.candidate,run.pending?.prompt_id,run.dependency])!==
                JSON.stringify([this.run?.status,this.run?.active,this.run?.stage,this.run?.accepted,this.run?.candidate,this.run?.pending?.prompt_id,this.run?.dependency]);
            this.run=run;showImageStage(run,this.node);if(changed){this.error=run.error||'';this.render();}
            if(this.connectionFailed){this.connectionFailed=false;this.shell.message(msg("images.image_workflow_connected"));}
        }}catch(error){if(!this.disposed){this.connectionFailed=true;this.shell.message(sourceMessage(error.message),true);}}
        if(!this.disposed)this.timer=setTimeout(()=>this.poll(),1500);
    }
    revision(side){return this.run?.revisions.find(r=>r.id===this.run.accepted[side]);}
    async save(destination){
        this.run=await request('images/'+this.id+'/save',{});
        if(destination==='another'){this.id=null;this.run=null;this.draft={...this.draft,name:'Untitled image',description:'',front:'',back:'',references:[]};this.remember();this.render();this.shell.content.scrollTop=0;}
        else if(destination==='gallery')await this.shell.openImages('Gallery');
        else if(destination==='3d'){
            const handoff=await request('images/'+this.id+'/handoff',this.singleOrigin?{mode:'single'}:{});
            const origin=this.shell.imageOrigin;delete this.shell.imageOrigin;
            if(this.ccoreOrigin)await this.shell.openCcoreWizard({image:true,handoff});
            else await this.shell.chooseMesh(handoff,origin);
        }
    }
    async edit(side){const {editImage}=await import('./editor.js');return editImage(this,side);}
    dispose(){this.disposed=true;clearTimeout(this.timer);this.observer?.disconnect();api.removeEventListener('progress',this.progress);this.remember();}
}
