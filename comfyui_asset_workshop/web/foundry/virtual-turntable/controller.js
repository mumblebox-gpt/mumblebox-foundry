import {api} from '/scripts/api.js';
import {app} from '/scripts/app.js';
import {el,button,field,hint,link} from '../dom.js';
import {msg,sourceMessage} from '../i18n.js';
import {request} from '../services.js';
import {activity,elapsedTime} from '../activity.js';
import {uploadReference,capturePhoto,inputURL} from '../images/references.js';
import {exportChoices,validateExports} from '../wizard/export-choices.js';
import {mountMesh} from '../wizard/preview.js';
import {orbitMedia} from './media.js';
import {showTurntableGraph,syncTurntableGraph,syncTurntableOutputs} from './graph.js';

const KEY='virtual-turntable';
const TITLES=['Choose an engine','Set up your reference','Review the orbit','Review the mesh','Finish and export'];
const STAGE_PAGES={preparing:3,turnaround:3,orbit:3,geometry:4,texture:5,balanced:5,compact:5,quads:5,print:5,package:5};
const LABELS={
    width:'Video width',height:'Video height',length:'Video frames',fps:'Frames per second',prompt:'Prompt',
    side_fraction:'Side guide timing',three_quarter_fraction:'Three-quarter guide timing',back_fraction:'Back guide timing',
    initial_fov:'Horizontal field of view (degrees)',refine:'Use Hi3D refinement',
    max_features:'Maximum image features',band:'Cleanup surface band',
    texture_triangle_target:'Projection triangle limit',texture_triangles:'Texturing triangle limit',
    uv_resolution:'UV resolution',uv_padding:'UV padding',uv_weld_distance:'UV weld distance',memory_gib:'Working memory (GiB)',
};
const human=name=>LABELS[name]||name.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const copy=structuredClone;
const translated=value=>sourceMessage(value);

export class VirtualTurntableWizard{
    constructor(shell,{resume=false,runId=null,handoff=null}={},config={}){
        this.key=config.key||KEY;
        this.stateKey=config.stateKey||'foundryVirtualTurntable';
        this.title=config.title||'Virtual Turntable';
        this.titles=config.titles||TITLES;
        this.stagePages=config.stagePages||STAGE_PAGES;
        this.operationPages=config.operationPages||{turnaround:3,orbit:3,reconstruct:4,finish:5,rocket:3};
        this.layout=config.layout||'turntable';
        this.offset=config.offset||780000;
        this.shell=shell;
        this.node=shell.node;
        const saved=resume?this.node.properties[this.stateKey]:null;
        this.page=saved?.page||1;
        this.runId=runId||saved?.runId;
        this.draft=saved?.draft;
        this.handoff=handoff;
        this.host=el('section',{class:'wizard turntable-wizard','aria-label':translated(this.title)});
        this.previewDisposers=[];
    }
    async init(){
        this.cap=await request(this.key+'/capabilities');
        this.meshCap=await request('wizard/capabilities');
        this.draft??=this.initialDraft();
        this.draft.controls=Object.fromEntries(Object.entries(this.cap.defaults).map(([key,values])=>
            [key,{...values,...this.draft.controls[key]}]));
        if(this.handoff){
            this.draft={...this.draft,name:this.handoff.name,image:this.handoff.references[0].filename,image_creation:this.handoff.image_creation};
            this.runId=null;this.page=this.handoffPage();
        }
        if(this.runId){
            this.run=await request(this.path());
            this.draft=this.restoreDraft(this.run);
            this.followStage=this.run.operation==='rocket';
            if(this.run.active)this.page=this.stagePages[this.run.stage]||this.page;
            else if(this.run.package)this.page=5;
            else if(!this.node.properties[this.stateKey]?.runId||this.runId!==this.node.properties[this.stateKey].runId){
                this.page=this.savedPage();
            }
        }
        this.render();
        this.poll();
        return this.host;
    }
    initialDraft(){return {name:'',image:'',engine:'',controls:copy(this.cap.defaults),selection:copy(this.cap.selection),overrides:{}};}
    restoreDraft(run){return {name:run.name,image:run.references[0].filename,engine:run.engine,
        controls:copy(run.controls),selection:copy(run.selection),overrides:copy(run.overrides),image_creation:run.image_creation};}
    handoffPage(){return this.draft.engine?2:1;}
    savedPage(){return this.complete('geometry')?4:this.complete('turnaround')?3:1;}
    path(suffix=''){return this.key+'/runs/'+this.runId+suffix;}
    remember(){
        this.node.properties[this.stateKey]={page:this.page,runId:this.runId,draft:copy(this.draft)};
        app.graph.change?.();
    }
    go(page){this.page=page;this.remember();this.render();this.shell.content.scrollTop=0;}
    get busy(){return Boolean(this.sending||this.run?.active);}
    get ready(){return Boolean(this.draft.engine&&this.draft.image&&this.draft.name.trim());}
    complete(stage){return this.run?.completed.includes(stage);}
    async act(action){
        if(this.sending)return;
        this.sending=true;
        this.error='';
        this.render();
        try{await action();}
        catch(error){this.error=error.message;}
        finally{this.sending=false;if(!this.disposed){this.remember();this.render();}}
    }
    async save(){
        const route=this.runId?this.path():this.key+'/runs';
        this.run=await request(route,this.draft,this.runId?{method:'PATCH'}:{});
        this.runId=this.run.id;
        this.remember();
    }
    async start(operation){
        if(operation==='finish'||operation==='rocket')validateExports(this.draft.selection,this.quadChoice());
        await this.save();
        await this.bindGraph();
        this.followStage=operation==='rocket';
        this.run=await request(this.path('/start'),{operation,request_id:crypto.randomUUID(),client_id:api.clientId||''});
        this.page=this.operationPages[operation];
    }
    async bindGraph(stage){
        const suffix=stage?'?'+new URLSearchParams({stage}):'';
        const graph=await request(this.runId?this.path('/graph')+suffix:this.key+'/template');
        if(!this.disposed)syncTurntableGraph(graph,this.node,this.layout);
    }
    async poll(){
        if(this.disposed)return;
        try{
            if(this.runId&&!this.sending){
                const run=await request(this.path());
                if(this.disposed)return;
                const signature=state=>JSON.stringify([state?.active,state?.stage,state?.status,state?.pending?.prompt_id,state?.dependency?.name,state?.previews,state?.error]);
                const changed=signature(run)!==signature(this.run);
                this.run=run;
                if(run.pending&&run.pending.prompt_id!==this.lastPrompt){
                    this.lastPrompt=run.pending.prompt_id;
                    await this.bindGraph(run.pending.stage);
                }
                syncTurntableOutputs(run.outputs,this.node,this.layout);
                if(this.followStage&&run.active&&run.stage!=='preparing')this.page=this.stagePages[run.stage]||this.page;
                if(changed){this.remember();this.render();}
            }
        }catch(error){if(!this.disposed){this.error=error.message;this.render();}}
        finally{if(!this.disposed)this.timer=setTimeout(()=>this.poll(),1200);}
    }
    async setImage(file){
        const result=await uploadReference(file);
        this.draft.image=result.filename;
        this.draft.name||=file.name.replace(/\.[^.]+$/,'');
        delete this.draft.image_creation;
    }
    quadChoice(){
        const o=this.draft.overrides;
        return {methods:this.meshCap.quad_methods||[],value:o.quad_method||this.cap.finishing_defaults.quad_method||'quadriflow',
            controls:this.meshCap.quad_options||{},name:this.key+'-quad',
            change:value=>{o.quad_method=value;this.remember();},
            getOption:(group,id,fallback)=>o.quad_options?.[group]?.[id]??fallback,
            setOption:(group,id,value)=>{((o.quad_options??={})[group]??={})[id]=value;this.remember();},
        };
    }
    input(group,name){
        const spec=this.cap.controls[group][name];
        const id=this.key+'-'+group+'-'+name;
        const value=this.draft.controls[group][name];
        const projection=name==='texture_triangle_target';
        const warning=projection?el('p',{class:'warning',role:'status',hidden:value!==0},
            msg('virtual_turntable.full_density_warning')):null;
        const set=v=>{
            this.draft.controls[group][name]=v;
            if(warning)warning.hidden=v!==0;
            this.remember();
        };
        const attrs={id,disabled:this.busy};
        let input;
        if(spec.choices){
            input=el('select',{...attrs,onchange:e=>set(spec.choices[e.currentTarget.selectedIndex])},
                ...spec.choices.map(choice=>el('option',{selected:choice===value},
                    projection&&choice===0?msg('virtual_turntable.full_density'):translated(String(choice)))));
        }else if(typeof value==='boolean'){
            input=el('input',{...attrs,type:'checkbox',checked:value,onchange:e=>set(e.currentTarget.checked)});
        }else if(typeof value==='number'){
            input=el('input',{...attrs,type:'number',value,min:spec.limits?.[0],max:spec.limits?.[1],step:spec.step||'any',
                onchange:e=>{const n=e.currentTarget;if(n.checkValidity()&&Number.isFinite(n.valueAsNumber))set(n.valueAsNumber);else n.reportValidity();}});
        }else{
            input=el('textarea',{...attrs,rows:name==='prompt'?5:3,value,onchange:e=>set(e.currentTarget.value)});
        }
        const defaultValue=typeof spec.default==='string'&&spec.default.length>90?'Reset to restore the full text.':(spec.default===''?translated('Blank'):typeof spec.default==='boolean'?translated(spec.default?'On':'Off'):translated(String(spec.default)));
        const control=field(translated(human(name)),input,msg('virtual_turntable.text_help_default_value',{help:translated(spec.help),value:typeof defaultValue==='string'?translated(defaultValue):defaultValue}));
        if(warning)control.append(warning);
        return control;
    }
    section(group,label,{visible=[],advanced=true}={}){
        const keys=Object.keys(this.cap.controls[group]);
        const controls=keys.filter(key=>!visible.includes(key)).map(key=>this.input(group,key));
        return el('fieldset',{class:'turntable-control-section'},el('legend',{},translated(label)),
            ...visible.map(key=>this.input(group,key)),
            controls.length?(advanced?el('details',{},el('summary',{},translated('Advanced')),...controls):el('div',{},...controls)):null,
            button(translated('Reset to defaults'),()=>{
                this.draft.controls[group]=copy(this.cap.defaults[group]);
                this.remember();this.render();
            },{disabled:this.busy}));
    }
    image(extraActions=[]){
        const upload=el('input',{type:'file',hidden:true,accept:'image/png,image/jpeg,image/webp',
            onchange:e=>{const [file]=e.target.files;if(file)this.act(()=>this.setImage(file));}});
        return el('section',{class:'turntable-reference'},
            field(translated('Asset name'),el('input',{value:this.draft.name,maxLength:100,disabled:this.busy,
                onchange:e=>{this.draft.name=e.currentTarget.value;this.remember();this.render();}})),
            this.draft.image?el('img',{src:inputURL(this.draft.image),alt:translated('Starting reference image')}):null,
            upload,el('div',{class:'actions'},
                button(translated('Upload an image'),()=>upload.click(),{disabled:this.busy}),
                button(translated('Create an image'),()=>{
                    this.remember();
                    this.shell.imageOrigin={method:this.key};
                    this.shell.openImages('Create Images');
                },{disabled:this.busy}),
                button(translated('Use webcam'),()=>capturePhoto(this.shell,file=>this.act(()=>this.setImage(file))),
                    {disabled:this.busy||!navigator.mediaDevices}),...extraActions));
    }
    engine(){
        return el('div',{},hint(translated(this.cap.description)),hint(translated(this.cap.tip)),
            el('fieldset',{},el('legend',{},translated('Reconstruction engine')),
                ...Object.entries(this.cap.engines).map(([key,value])=>el('label',{class:'check-row'},
                    el('input',{type:'radio',name:'turntable-engine',value:key,checked:this.draft.engine===key,disabled:this.busy,
                        onchange:()=>{this.draft.engine=key;this.remember();this.render();}}),
                    el('span',{},value.name,value.recommended?el('span',{class:'badge'},translated('Recommended')):null,
                        hint(translated(value.description)),
                        value.missing?.length?hint(msg('virtual_turntable.text_local_setup_required_files',{files:value.missing.join(', ')})):null)))),
            this.draft.engine&&this.cap.engines[this.draft.engine].missing?.length
                ?link(translated('Get the selected engine'),this.cap.engines[this.draft.engine].source):null,
            el('aside',{class:'note-panel','aria-labelledby':'turntable-author-note-title'},
                el('strong',{id:'turntable-author-note-title'},msg('virtual_turntable.author_note_title')),
                hint(msg('virtual_turntable.author_note_body')),
                link(msg('virtual_turntable.author_note_link'),'https://beta.pinokio.co/apps/github-com-mumblebox-gpt-mumblebox-foundry')),
            el('details',{open:true},el('summary',{},translated('Model credits and terms')),
                hint(translated(this.cap.license_note)),...Object.entries(this.cap.license_links).map(([label,url])=>el('p',{},link(label,url)))));
    }
    setup(){
        const presets=[
            ['Standard · 3 seconds',{width:768,height:768,length:73,steps:28,turbo:false,sampler:'res_multistep',scheduler:'simple'}],
            ['Long · 10 seconds',{width:768,height:768,length:243,steps:8,turbo:true,sampler:'euler',scheduler:'beta'}],
            ['Lower VRAM · 3 seconds',{width:512,height:512,length:73,steps:28,turbo:false,sampler:'res_multistep',scheduler:'simple'}],
        ];
        return el('div',{},this.image(),this.section('turnaround','H3 four-view turnaround'),
            el('div',{class:'actions'},...presets.map(([label,values])=>button(translated(label),()=>{
                Object.assign(this.draft.controls.orbit,values);this.remember();this.render();
            },{disabled:this.busy}))),
            this.section('orbit','360° orbit settings',{visible:['subject_direction','length']}),
            this.section('frames','Reconstruction frames'),
            this.section(this.draft.engine,this.cap.engines[this.draft.engine].name),
            button(translated('Reset all workflow settings'),()=>{
                this.draft.controls=copy(this.cap.defaults);this.draft.overrides={};this.draft.selection=copy(this.cap.selection);
                this.remember();this.render();
            },{disabled:this.busy}));
    }
    orbit(playing=false){
        const media=orbitMedia(this.run, this.offset+40, playing);
        if(media.release)this.previewDisposers.push(media.release);
        return media.element;
    }
    preview(role,label){
        const url=this.run?.previews?.[role];
        if(!url)return null;
        const mount=el('div',{class:'turntable-mesh-preview'});
        const owner=this.renderEpoch;
        queueMicrotask(async()=>{
            if(this.disposed||owner!==this.renderEpoch)return;
            try{
                const release=await mountMesh(mount,url,this.cap.viewer);
                if(this.disposed||owner!==this.renderEpoch)release();else this.previewDisposers.push(release);
            }catch(error){if(owner===this.renderEpoch)mount.replaceChildren(hint(translated(error.message)));}
        });
        return el('section',{},el('h3',{},translated(label)),mount);
    }
    reviewOrbit(){
        return el('div',{},this.run?.previews?.sheet?el('img',{class:'turntable-sheet',src:this.run.previews.sheet,
            alt:translated('Four-view turnaround: front, side, three-quarter and back')}):null,this.orbit(),
            hint(translated('Check that the object keeps its shape and details throughout the orbit.')),
            this.run?.previews?.orbit?el('a',{href:this.run.previews.orbit,download:''},translated('Download orbit video')):null);
    }
    reviewMesh(){
        const report=this.run?.reconstruction;
        const registered=report?.registered_cameras??report?.camera_validation?.calibrated_views;
        return el('div',{},this.orbit(this.run?.active&&this.run.stage==='geometry'),
            registered!=null?hint(msg('virtual_turntable.text_count_camera_views_aligned',{count:registered})):null,
            this.run?.previews?.frames?el('details',{},el('summary',{},translated('Review the masked reconstruction frames')),
                el('img',{class:'turntable-sheet',src:this.run.previews.frames,alt:translated('Selected masked orbit frames')})):null,
            this.preview('raw','Original reconstruction'));
    }
    finish(){
        const appearance=this.draft.engine==='meshroom'?'meshroom_finish':'openmvs_finish';
        return el('div',{},this.section('refinement','Hi3D and cleanup',{visible:['refine']}),
            this.section(appearance,'Photo texture and material',
                {visible:appearance==='openmvs_finish'?['texture_triangle_target']:[]}),
            this.exportSettings(true),
            this.preview('clean','Clean geometry'),this.preview('texture','Finished textured mesh'),
            this.run?.package?.download?link(translated('Download asset ZIP'),this.run.package.download,{download:true}):null);
    }
    exportSettings(includeTextureSize){
        const names={texture_size:'Baked texture size',balanced_triangles:'Balanced triangle target',compact_triangles:'Compact triangle target',
            quad_count:'Quad target',print_height_mm:'Print height (mm)'};
        if(!includeTextureSize)delete names.texture_size;
        return el('fieldset',{disabled:this.busy,class:'turntable-export-panel'},
            exportChoices(this.cap.exports,this.draft.selection,()=>this.remember(),this.quadChoice()),
            el('details',{},el('summary',{},translated('Advanced export settings')),
                ...Object.entries(names).map(([key,label])=>{
                    const value=this.draft.overrides[key]??this.cap.finishing_defaults[key];
                    const save=next=>{this.draft.overrides[key]=next;this.remember();};
                    const control=key==='texture_size'
                        ?el('select',{disabled:this.busy,onchange:e=>save(Number(e.currentTarget.value))},
                            ...[1024,2048,4096].map(size=>el('option',{value:String(size),selected:size===value},String(size))))
                        :el('input',{type:'number',min:1,step:1,disabled:this.busy,value,onchange:e=>save(e.currentTarget.valueAsNumber)});
                    return field(translated(label),control,
                    msg('virtual_turntable.text_sets_the_target_for_this_export_default_value',{value:this.cap.finishing_defaults[key]}));}),
                button(translated('Reset export settings'),()=>{this.draft.overrides={};this.draft.selection=copy(this.cap.selection);this.remember();this.render();})));
    }
    next(){
        if(this.page===1)return button(translated('Next'),()=>this.go(2),{class:'primary',disabled:!this.draft.engine||this.busy});
        if(this.page===2)return button(translated('Generate turnaround'),()=>this.act(()=>this.start('turnaround')),{class:'primary',disabled:!this.ready||this.busy});
        if(this.page===3){
            const orbit=this.complete('orbit');
            return button(translated(orbit?'Reconstruct mesh':this.complete('turnaround')?'Generate orbit':'Generate turnaround'),
                ()=>this.act(()=>this.start(orbit?'reconstruct':this.complete('turnaround')?'orbit':'turnaround')),{class:'primary',disabled:!this.ready||this.busy});
        }
        if(this.page===4)return button(translated(this.complete('geometry')?'Finish and export':'Reconstruct mesh'),
            ()=>this.complete('geometry')?this.go(5):this.act(()=>this.start('reconstruct')),{class:'primary',disabled:this.busy});
        return button(translated('Prepare asset package'),()=>this.act(()=>this.start('finish')),
            {class:'primary',disabled:this.busy||!this.complete('geometry')});
    }
    get showRocket(){return this.page>1;}
    body(){return [this.engine,this.setup,this.reviewOrbit,this.reviewMesh,this.finish][this.page-1].call(this);}
    render(){
        this.renderEpoch=(this.renderEpoch||0)+1;
        for(const release of this.previewDisposers.splice(0))release();
        this.clock=null;
        const active=this.run?.active;
        const feedback=active?activity():null;
        feedback?.update({busy:true,label:translated(this.run?.stage_label||'Preparing')});
        const status=active?el('div',{class:'turntable-progress'},
            feedback.element,elapsedTime(this.run.started_at*1000),el('progress',{'aria-label':translated('Stage progress')})):null;
        const body=this.body();
        const error=this.error||this.run?.error;
        this.host.replaceChildren(
            el('aside',{class:'wizard-rail'},el('h2',{},translated(this.title)),
                el('ol',{class:'wizard-steps'},...this.titles.map((title,index)=>el('li',{'aria-current':this.page===index+1?'step':null},el('span',{class:'step-number'},String(index+1)),el('strong',{},translated(title)))))),
            el('main',{class:'wizard-panel'},
                el('header',{class:'page-head'},el('span',{class:'eyebrow'},msg('virtual_turntable.text_step_number_of_total',{number:this.page,total:this.titles.length})),
                    el('h2',{},translated(this.titles[this.page-1]))),
                status,error?el('p',{class:'warning',role:'alert'},translated(error)):null,body,
                el('footer',{class:'wizard-footer'},el('div',{class:'actions'},
                    this.page>1?button(translated('Back'),()=>this.go(this.page-1),{disabled:this.busy}):null,
                    this.next(),
                    this.showRocket?button(translated('Rocket Mode'),()=>this.act(()=>this.start('rocket')),
                        {disabled:!this.ready||this.busy}):null,
                    active?button(translated('Stop current run'),()=>this.act(async()=>{this.run=await request(this.path('/cancel'),{});})):null,
                    button(translated('View graph'),()=>this.act(async()=>{await this.bindGraph();showTurntableGraph(this.node,this.layout);}),{disabled:this.busy}),
                    button(translated('Choose a Workflow'),()=>this.shell.open('Choose a Workflow'))))));
    }
    dispose(){
        this.disposed=true;
        clearTimeout(this.timer);
        for(const release of this.previewDisposers.splice(0))release();
    }
}
