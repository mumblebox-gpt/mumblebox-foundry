import {api} from '/scripts/api.js';
import {app} from '/scripts/app.js';
import {el,button,field,hint,link} from '../dom.js';
import {currentLanguage,msg,sourceMessage,setText} from '../i18n.js';
import {dialog} from '../dialogs.js';
import {orbitSettings,ux} from './settings.js';
import {firstChangedStage,operations,settingsProblem} from './review-state.js';
import {request} from '../services.js';
import {activity,elapsedTime} from '../activity.js';
import {uploadReference,capturePhoto,inputURL} from '../images/references.js';
import {exportChoices,validateExports} from '../wizard/export-choices.js';
import {mountMesh} from '../wizard/preview.js';
import {orbitMedia} from './media.js';
import {syncTurntableGraph,syncTurntableOutputs} from './graph.js';

const KEY='virtual-turntable';
const TITLES=['Choose an engine','Set up your reference','Review the orbit','Review the mesh','Finish and export'];
const STAGE_PAGES={preparing:3,turnaround:3,orbit:3,frames:3,geometry:4,texture:5,balanced:5,compact:5,quads:5,print:5,package:5};
const LABELS={
    width:'Video width',height:'Video height',length:'Video frames',fps:'Frames per second',prompt:'Prompt',
    side_fraction:'Side guide timing',three_quarter_fraction:'Three-quarter guide timing',back_fraction:'Back guide timing',
    initial_fov:'Horizontal field of view (degrees)',refine:'Use Hi3D refinement',
    max_features:'Maximum image features',band:'Cleanup surface band',
    texture_triangle_target:'Projection triangle limit',texture_triangles:'Texturing triangle limit',
    uv_resolution:'UV resolution',uv_padding:'UV padding',uv_weld_distance:'UV weld distance',memory_gib:'Working memory (GiB)',
};
const human=name=>LABELS[name]||name.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
// The Comfy graph can expose saved node properties through a reactive proxy.
const copy=value=>JSON.parse(JSON.stringify(value));
const translated=value=>sourceMessage(value);

const ADVANCED_GROUPS = {
    turnaround:[['prompt','crops'],['panel_size','seed','sampler','sigmas','video_shift','decode_tile']],
    pixal:[['shape_resolution','seed','structure_shift'],
        ['structure_steps','structure_cfg','structure_sampler','structure_scheduler','structure_denoise'],
        ['shape_steps','shape_cfg','shape_sampler','shape_scheduler','shape_denoise'],
        ['detail_steps','detail_cfg','detail_sampler','detail_scheduler','detail_denoise']],
    meshroom:[['camera_calibration','initial_fov','minimum_checked_fov','maximum_checked_fov','min_2d_motion'],
        ['feature_density','depth_downscale','depth_tile','neighbor_cameras','max_input_points','max_mesh_points','texture_size'],
        ['cpu_threads','timeout_minutes','advanced_overrides']],
    'colmap-openmvs':[['camera_calibration','initial_fov','camera_model','shared_camera','initial_focal_factor','gpu_features','gpu_index','max_features'],
        ['depth_downscale','max_resolution','neighbor_views','refine_mesh','refine_on_gpu','refine_decimation','texture_size'],
        ['cpu_threads','timeout_minutes','advanced_overrides']],
};
const NUMERIC_PRESETS = {
    panel_size:[512,768,1024,1536],decode_tile:[128,256,512,768], decode_frames:[16,32,64],
    max_frames:[24,48,72,120],max_edge:[512,768,1024],batch_size:[1,2,4],
    initial_fov:[10,20,35,60],cpu_threads:[4,8,16],max_features:[4096,8192,16384],
    cleanup_resolution:[256,384,512,768],texture_steps:[12,20,28],
    balanced_triangles:[100000,250000,500000],compact_triangles:[25000,50000,100000],
    quad_count:[10000,25000,50000],print_height_mm:[50,100,150,200],
};

export class VirtualTurntableWizard{
    constructor(shell,{resume=false,runId=null,handoff=null}={},config={}){
        this.key=config.key||KEY;
        this.stateKey=config.stateKey||'foundryVirtualTurntable';
        this.title=config.title||'Virtual Turntable';
        this.titles=config.titles||TITLES;
        this.stagePages=config.stagePages||STAGE_PAGES;
        this.operationPages=config.operationPages||{turnaround:3,orbit:3,frames:3,reconstruct:4,finish:5,rocket:3};
        this.layout=config.layout||'turntable';
        this.offset=config.offset||780000;
        this.shell=shell;
        this.node=shell.node;
        const saved=resume?this.node.properties[this.stateKey]:null;
        this.page=saved?.page||1;
        this.runId=runId||saved?.runId;
        this.draft=saved?.draft?copy(saved.draft):null;
        this.useSavedDraft=Boolean(saved?.draft&&saved.runId===this.runId&&!runId);
        this.disclosures=new Set();
        this.rocketDialog=null;
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
            if(!this.useSavedDraft||this.run.active)this.draft=this.restoreDraft(this.run);
            this.followStage=this.run.operation==='rocket';
            if(this.run.active)this.page=this.stagePages[this.run.stage]||this.page;
            else if(!this.useSavedDraft)this.page=this.run.package?5:this.savedPage();
        }
        this.render();
        this.poll();
        return this.host;
    }
    initialDraft(){return {name:'',image:'',engine:Object.keys(this.cap.engines||{}).find(id=>this.cap.engines[id].recommended)||'',
        controls:copy(this.cap.defaults),selection:copy(this.cap.selection),overrides:{}};}
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
    get missing(){return this.cap.engines?.[this.draft.engine]?.missing||this.cap.missing||[];}
    orbitIssue(){return settingsProblem('orbit',this.draft.controls.orbit);}
    get dirtyStage(){return firstChangedStage(this.draft,this.run);}
    get canStart(){
        return this.ready&&!this.missing.length&&!Object.entries(this.draft.controls)
            .some(([group,values])=>settingsProblem(group,values));
    }
    get canRetry(){return Boolean(this.run?.error&&this.run.operation&&!this.dirtyStage);}
    renderAt(id){
        this.render();
        if(id)this.host.querySelector('[id="'+id+'"]')?.focus({preventScroll:true});
    }
    refreshActions(){
        if(!this.actions)return;
        const {next,rocket,retry,note}=this.actions;
        const action=this.next();
        next.replaceWith(action);
        this.actions.next=action;
        if(rocket)rocket.disabled=this.busy||!this.canStart;
        if(retry)retry.disabled=this.busy||!this.canStart;
        const changed=this.dirtyStage;
        note.hidden=!changed;
        setText(note,changed?ux('changed_stage',{stage:ux(operations[changed])}):'');
    }
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
        if(!this.canStart)return;
        if(operation==='finish'||operation==='rocket')validateExports(this.draft.selection,this.quadChoice());
        await this.save();
        const prerequisite={orbit:'turnaround',cameras:'orbit',views:'cameras',frames:'orbit',reconstruct:this.cap.view_presets?'views':'orbit',finish:'geometry'}[operation];
        if(prerequisite&&!this.complete(prerequisite)){
            this.page=this.savedPage();
            this.error=String(ux('resume_from_saved'));
            return;
        }
        await this.bindGraph();
        this.followStage=operation==='rocket';
        this.run=await request(this.path('/start'),{operation,request_id:crypto.randomUUID(),client_id:api.clientId||''});
        this.page=this.operationPages[operation];
    }
    rocketFields(){return null;}
    rocketSummary(){
        const choice=this.quadChoice();
        const selection=this.draft.selection.variants;
        const names={detailed:'output_detailed',game_balanced:'output_balanced',game_compact:'output_compact',
            quad_light:'output_quads',print:'output_print',quad_detail:'output_quads'};
        const variants=Object.entries(selection).filter(([,value])=>value.formats?.length);
        const stageList=['turnaround','orbit',...(this.cap.view_presets?['cameras','views']:this.cap.frame_review?['frames']:[]),'reconstruct','finish'];
        const completed={turnaround:'turnaround',orbit:'orbit',cameras:'cameras',views:'views',frames:'frames',reconstruct:'geometry',finish:'package'};
        const first=stageList.indexOf(this.dirtyStage);
        const stages=stageList.filter((stage,index)=>stage==='finish'||!this.complete(completed[stage])||(first>=0&&index>=first));
        let error;
        try{validateExports(this.draft.selection,choice);}
        catch(issue){error=issue.message;}
        return el('div',{class:'turntable-rocket-summary'},
            el('section',{},el('h3',{},ux('rocket_runs')),el('ol',{},...stages.map(stage=>el('li',{},ux(operations[stage]))))),
            el('section',{},el('h3',{},ux('rocket_files')),
                variants.length?el('ul',{},...variants.map(([id,value])=>el('li',{},
                    ux('rocket_file',{variant:names[id]?ux(names[id]):id,formats:value.formats.map(format=>format.toUpperCase()).join(', ')}))),
                    el('li',{},translated('Download asset ZIP'))):null),
            error?el('p',{role:'alert',class:'warning'},translated(error)):null);
    }
    openRocket(){
        if(!this.canStart)return;
        const summary=el('div');
        const update=()=>{
            summary.replaceChildren(this.rocketSummary());
            start.disabled=!this.canStart||!!summary.querySelector('[role="alert"]');
        };
        const body=el('div',{class:'turntable-rocket'},
            hint(ux('rocket_intro')),this.cap.engines?.[this.draft.engine]?el('p',{},this.cap.engines[this.draft.engine].name):null,
            this.rocketFields(update),summary,
            el('details',{class:'turntable-advanced'},el('summary',{},ux('edit_output_choices')),
                this.exportSettings(!this.cap.view_presets,update)));
        const modal=dialog(this.shell,ux('review_rocket'),body,[{
            label:ux('start_rocket'),primary:true,run:async close=>{
                close();
                await this.act(()=>this.start('rocket'));
            },
        }]);
        modal.surface.classList.add('turntable-rocket-dialog');
        this.rocketDialog=modal;
        modal.surface.addEventListener('foundry-close',()=>{this.rocketDialog=null;},{once:true});
        const start=modal.surface.querySelector('.dialog-actions button');
        update();
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
    quadChoice(onChange=()=>{}){
        const o=this.draft.overrides;
        return {methods:this.meshCap.quad_methods||[],value:o.quad_method||this.cap.finishing_defaults.quad_method||'quadriflow',
            controls:this.meshCap.quad_options||{},name:this.key+'-quad',
            change:value=>{o.quad_method=value;this.remember();onChange();},
            getOption:(group,id,fallback)=>o.quad_options?.[group]?.[id]??fallback,
            setOption:(group,id,value)=>{((o.quad_options??={})[group]??={})[id]=value;this.remember();onChange();},
        };
    }
    resetGroup(group,label=translated('Reset to defaults')){
        const id=this.key+'-'+group+'-reset';
        return button(label,()=>{
            this.draft.controls[group]=copy(this.cap.defaults[group]);
            this.remember();
            this.renderAt(id);
        },{id,disabled:this.busy});
    }
    numericPreset(label, input, value, fallback, options, description) {
        const numbers=[...new Set([...options,fallback])].filter(number=>
            number>=Number(input.min||'-Infinity')&&number<=Number(input.max||'Infinity')).sort((a,b)=>a-b);
        const fieldId=input.id+'-preset';
        const select=el('select',{id:fieldId,disabled:this.busy,
            onchange:()=>{
                custom.hidden=select.value!=='custom';
                if(custom.hidden){
                    input.value=select.value;
                    input.dispatchEvent(new Event('change'));
                }else input.focus();
            }},
            ...numbers.map(number=>el('option',{value:String(number),selected:number===value},
                number===fallback?ux('default_choice',{label:number.toLocaleString(currentLanguage())}):number.toLocaleString(currentLanguage()))),
            el('option',{value:'custom',selected:!numbers.includes(value)},ux('custom')));
        const custom=field(ux('exact_value',{label}),input);
        custom.hidden=numbers.includes(value);
        return el('div',{class:'turntable-preset-field'},field(label,select,description),custom);
    }
    input(group,name,{change=()=>this.refreshActions()}={}){
        const spec=this.cap.controls[group][name];
        const id=this.key+'-'+group+'-'+name;
        const value=this.draft.controls[group][name];
        const projection=name==='texture_triangle_target'||name==='texture_triangles';
        const warning=projection?el('p',{class:'warning',role:'status',hidden:value!==0},
            msg('virtual_turntable.full_density_warning')):null;
        const label=translated(human(name));
        const set=v=>{
            this.draft.controls[group][name]=v;
            if(warning)warning.hidden=v!==0;
            this.remember();change();
        };
        const attrs={id,disabled:this.busy,'aria-describedby':id+'-help'};
        const defaultValue=typeof spec.default==='string'&&spec.default.length>90?translated('Reset to restore the full text.'):
            spec.default===''?translated('Blank'):typeof spec.default==='boolean'?translated(spec.default?'On':'Off'):translated(String(spec.default));
        const description=msg('virtual_turntable.text_help_default_value',{help:translated(spec.help),value:defaultValue});
        let control;
        if(spec.choices){
            const input=el('select',{...attrs,onchange:e=>set(spec.choices[e.currentTarget.selectedIndex])},
                ...spec.choices.map(choice=>el('option',{value:String(choice),selected:choice===value},
                    projection&&choice===0?msg('virtual_turntable.full_density'):translated(String(choice)))));
            control=field(label,input,description);
        }else if(typeof value==='boolean'){
            const input=el('input',{...attrs,type:'checkbox',checked:value,onchange:e=>set(e.currentTarget.checked)});
            control=el('div',{class:'turntable-toggle'},el('label',{},input,label),hint(description));
        }else if(typeof value==='number'){
            const input=el('input',{...attrs,type:'number',value,min:spec.limits?.[0],max:spec.limits?.[1],
                required:true,step:spec.step||(Number.isInteger(spec.limits?.[0])&&Number.isInteger(spec.limits?.[1])&&Number.isInteger(spec.default)?1:'any'),
                onchange:e=>{
                    const next=e.currentTarget;
                    if(next.checkValidity()&&Number.isFinite(next.valueAsNumber))set(next.valueAsNumber);
                    else {next.reportValidity();next.value=String(this.draft.controls[group][name]);}
                }});
            const options=name==='initial_fov'&&group==='meshroom'?[10,20,35,60]:NUMERIC_PRESETS[name];
            control=options?this.numericPreset(label,input,value,spec.default,options,description):field(label,input,description);
        }else{
            const input=el('textarea',{...attrs,rows:name==='prompt'?4:3,value,onchange:e=>set(e.currentTarget.value)});
            const prompt=['prompt','subject_direction'].includes(name);
            const reset=prompt?button(ux('reset_text'),()=>{
                input.value=spec.default;
                set(spec.default);
                input.focus({preventScroll:true});
            },{disabled:this.busy,'aria-controls':id}):null;
            control=el('div',{class:'turntable-wide turntable-text'},
                el('div',{class:'turntable-field-head'},el('label',{htmlFor:id},label),reset),input,hint(description));
        }
        const help=control.querySelector('.muted');
        if(help)help.id=id+'-help';
        if(warning)control.append(warning);
        return control;
    }
    section(group,label,{visible=[],advanced=true,extra=null}={}){
        const issue=el('p',{class:'turntable-field-error',role:'status',hidden:true});
        const refresh=()=>{
            const problem=settingsProblem(group,this.draft.controls[group]);
            issue.hidden=!problem;
            setText(issue,problem||'');
        };
        const control=key=>this.input(group,key,{change:()=>{
            refresh();this.refreshActions();
        }});
        refresh();
        const keys=Object.keys(this.cap.controls[group]).filter(key=>!visible.includes(key));
        const groups=ADVANCED_GROUPS[group]||[keys];
        const grids=groups.map(list=>list.filter(key=>keys.includes(key))).filter(list=>list.length)
            .map(list=>el('div',{class:'turntable-fields'},...list.map(control)));
        return el('fieldset',{class:'turntable-control-section'},el('legend',{},translated(label)),
            extra,...visible.filter(key=>extra===null||key!=='preset').map(control),
            grids.length?(advanced?el('details',{class:'turntable-advanced','data-disclosure':group},
                el('summary',{},ux('advanced_settings')),...grids,this.resetGroup(group)):el('div',{},...grids,this.resetGroup(group))):null,issue);
    }
    image(extraActions=[]){
        const upload=el('input',{type:'file',hidden:true,accept:'image/png,image/jpeg,image/webp',
            onchange:e=>{const [file]=e.target.files;if(file)this.act(()=>this.setImage(file));}});
        return el('section',{class:'turntable-reference'},
            field(translated('Asset name'),el('input',{value:this.draft.name,maxLength:100,disabled:this.busy,
                oninput:e=>{this.draft.name=e.currentTarget.value;this.remember();this.refreshActions();}}),ux('asset_name_help')),
            !this.draft.image?hint(ux('reference_help')):null,
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
                        id:this.key+'-engine-'+key,onchange:()=>{this.draft.engine=key;this.remember();this.renderAt(this.key+'-engine-'+key);}}),
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
        const engine=this.cap.engines[this.draft.engine];
        return el('div',{},el('div',{class:'turntable-setup-grid'},this.image(),orbitSettings(this)),
            this.section('turnaround','H3 four-view turnaround'),
            this.section('frames','Reconstruction frames',{visible:['max_frames','max_edge']}),
            engine?this.section(this.draft.engine,engine.name,{visible:['camera_calibration','initial_fov']}):null,
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
        return el('div',{},el('div',{class:'turntable-review-media'},this.run?.previews?.sheet?el('img',{class:'turntable-sheet',src:this.run.previews.sheet,
            alt:translated('Four-view turnaround: front, side, three-quarter and back')}):null,this.orbit()),
            hint(translated('Check that the object keeps its shape and details throughout the orbit.')),
            this.frameReview(),
            this.run?.previews?.orbit?el('a',{href:this.run.previews.orbit,download:''},translated('Download orbit video')):null);
    }
    frameReview(){
        if(!this.cap.frame_review||!this.complete('orbit')||['turnaround','orbit'].includes(this.dirtyStage))return null;
        const review=this.run?.frame_review;
        const stale=this.dirtyStage==='frames';
        const video=review?.source_video;
        const summary=review&&!stale?ux('prepared_frames',{count:review.count,width:review.width,height:review.height}):ux('frame_review_description');
        return el('section',{class:'turntable-frame-review'},
            el('h3',{},ux('frame_review_title')),hint(summary),
            video&&!stale&&video.fps!=null?hint(ux('frame_review_video',
                {count:video.frame_count,fps:new Intl.NumberFormat(currentLanguage(),{maximumFractionDigits:2}).format(video.fps)})):null,
            review&&!stale&&this.run.previews.frames?
                el('img',{class:'turntable-sheet',src:this.run.previews.frames,alt:translated('Selected masked orbit frames')}):null);
    }
    reviewMesh(){
        const report=this.run?.reconstruction;
        const registered=report?.registered_cameras??report?.camera_validation?.calibrated_views;
        const coverage=report?.orbit_coverage;
        return el('div',{},this.orbit(this.run?.active&&this.run.stage==='geometry'),
            coverage?.largest_gap_degrees!=null
                ?hint(ux('camera_coverage',{count:coverage.registered_frames,total:coverage.input_frames,
                    angle:new Intl.NumberFormat(currentLanguage(),{maximumFractionDigits:1}).format(coverage.largest_gap_degrees)}))
                :registered!=null?hint(msg('virtual_turntable.text_count_camera_views_aligned',{count:registered})):null,
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
    exportSettings(includeTextureSize,change=()=>this.refreshActions()){
        const names={texture_size:'Baked texture size',balanced_triangles:'Balanced triangle target',compact_triangles:'Compact triangle target',
            quad_count:'Quad target',print_height_mm:'Print height (mm)'};
        if(!includeTextureSize)delete names.texture_size;
        return el('fieldset',{disabled:this.busy,class:'turntable-export-panel'},
            exportChoices(this.cap.exports,this.draft.selection,()=>{this.remember();change();},this.quadChoice(change)),
            el('details',{class:'turntable-advanced','data-disclosure':'exports'},el('summary',{},translated('Advanced export settings')),
                el('div',{class:'turntable-fields'},...Object.entries(names).map(([key,label])=>{
                    const value=this.draft.overrides[key]??this.cap.finishing_defaults[key];
                    const save=next=>{this.draft.overrides[key]=next;this.remember();change();};
                    const control=key==='texture_size'
                        ?el('select',{disabled:this.busy,onchange:e=>save(Number(e.currentTarget.value))},
                            ...[1024,2048,4096].map(size=>el('option',{value:String(size),selected:size===value},String(size))))
                        :el('input',{id:this.key+'-export-'+key,type:'number',min:this.cap.finishing_ranges?.[key]?.[0]??1,max:this.cap.finishing_ranges?.[key]?.[1],step:key==='print_height_mm'?'any':1,disabled:this.busy,value,required:true,
                            onchange:e=>{
                                const input=e.currentTarget;
                                if(input.checkValidity())save(input.valueAsNumber);
                                else {input.reportValidity();input.value=String(this.draft.overrides[key]??this.cap.finishing_defaults[key]);}
                            }});
                    const help=ux('export_'+key,{value:this.cap.finishing_defaults[key]});
                    return NUMERIC_PRESETS[key]
                        ?this.numericPreset(translated(label),control,value,this.cap.finishing_defaults[key],NUMERIC_PRESETS[key],help)
                        :field(translated(label),control,help);
                })),
                button(translated('Reset export settings'),()=>{
                    this.draft.overrides={};this.draft.selection=copy(this.cap.selection);
                    this.remember();this.render();
                    if(this.rocketDialog){this.rocketDialog.close();this.openRocket();}
                },{id:this.key+'-export-reset'})));
    }
    next(){
        if(this.page===1)return button(translated('Next'),()=>this.go(2),
            {class:'primary',disabled:!this.draft.engine||this.busy||!!this.missing.length});
        if(this.page===2)return this.runButton(this.complete('turnaround')&&this.dirtyStage!=='turnaround'
            ?'Review the orbit':'Generate turnaround','turnaround',
            this.complete('turnaround')&&this.dirtyStage!=='turnaround'?()=>this.go(3):null);
        if(this.page===3){
            if(this.dirtyStage==='turnaround')return this.runButton('Generate turnaround','turnaround');
            if(this.complete('orbit')&&this.dirtyStage!=='orbit'){
                if(this.complete('geometry')&&!['frames','reconstruct'].includes(this.dirtyStage))
                    return this.runButton('Review the mesh','reconstruct',()=>this.go(4));
                if(this.cap.frame_review&&(!this.complete('frames')||this.dirtyStage==='frames'))
                    return this.runButton(ux('prepare_frames'),'frames');
                return this.runButton('Reconstruct mesh','reconstruct');
            }
            return this.complete('turnaround')?this.runButton('Generate orbit','orbit'):this.runButton('Generate turnaround','turnaround');
        }
        if(this.page===4){
            if(this.complete('geometry')&&!['turnaround','orbit','frames','reconstruct'].includes(this.dirtyStage))
                return this.runButton('Finish and export','finish',()=>this.go(5));
            if(['turnaround','orbit','frames'].includes(this.dirtyStage))return this.runButton('Back','reconstruct',()=>this.go(3));
            return this.runButton('Reconstruct mesh','reconstruct');
        }
        return this.finishButton();
    }
    runButton(label,operation,review=null){
        return button(typeof label==='string'?translated(label):label,review||(()=>this.act(()=>this.start(operation))),
            {class:'primary',disabled:this.busy||(!review&&!this.canStart),'data-main-action':'true'});
    }
    finishButton(){
        const changed=this.dirtyStage;
        if(changed&&changed!=='finish')return this.runButton(ux('review_earlier_step'),'finish',
            ()=>this.go(changed==='turnaround'?this.cap.view_presets?1:2:changed==='orbit'?this.cap.view_presets?2:3:
                this.cap.view_presets||changed==='frames'?3:4));
        const retry=this.canRetry&&(this.run.operation==='finish'||this.run.operation==='rocket');
        return button(retry?ux('retry_export'):translated('Prepare asset package'),()=>this.act(()=>this.start('finish')),
            {class:'primary',disabled:this.busy||!this.canStart||!this.complete('geometry'),'data-main-action':'true'});
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
        for(const detail of this.host.querySelectorAll('[data-disclosure]')){
            if(detail.open)this.disclosures.add(detail.dataset.disclosure);
            else this.disclosures.delete(detail.dataset.disclosure);
        }
        const body=this.body();
        for(const detail of body.querySelectorAll('[data-disclosure]'))detail.open=this.disclosures.has(detail.dataset.disclosure);
        const error=this.error||this.run?.error;
        const next=this.next();
        const rocket=this.showRocket?button(translated('Rocket Mode'),()=>this.openRocket(),{disabled:this.busy||!this.canStart}):null;
        const note=el('p',{class:'muted',role:'status',hidden:!this.dirtyStage},
            this.dirtyStage?ux('changed_stage',{stage:ux(operations[this.dirtyStage])}):null);
        const retry=this.page!==5&&this.canRetry?button(ux('retry_step'),()=>this.act(()=>this.start(this.run.operation)),
            {disabled:this.busy||!this.canStart}):null;
        this.actions={next,rocket,note,retry};
        this.host.replaceChildren(
            el('aside',{class:'wizard-rail'},el('h2',{},translated(this.title)),
                el('ol',{class:'wizard-steps'},...this.titles.map((title,index)=>el('li',{'aria-current':this.page===index+1?'step':null},el('span',{class:'step-number'},String(index+1)),el('strong',{},translated(title)))))),
            el('main',{class:'wizard-panel'},
                el('header',{class:'page-head'},el('span',{class:'eyebrow'},msg('virtual_turntable.text_step_number_of_total',{number:this.page,total:this.titles.length})),
                    el('h2',{},translated(this.titles[this.page-1]))),
                status,error?el('div',{class:'turntable-recovery'},
                    el('p',{class:'warning',role:'alert'},translated(error)),
                    this.run?.error?hint(ux('saved_steps_help')):null,retry):null,body,
                el('footer',{class:'wizard-footer'},note,el('div',{class:'actions'},
                    this.page>1?button(translated('Back'),()=>this.go(this.page-1),{disabled:this.busy}):null,
                    next,rocket,
                    active?button(translated('Stop current run'),()=>this.act(async()=>{this.run=await request(this.path('/cancel'),{});})):null,
                    button(translated('Choose a Workflow'),()=>this.shell.open('Choose a Workflow'))))));
    }
    dispose(){
        this.disposed=true;
        clearTimeout(this.timer);
        this.rocketDialog?.close();
        for(const release of this.previewDisposers.splice(0))release();
    }
}
