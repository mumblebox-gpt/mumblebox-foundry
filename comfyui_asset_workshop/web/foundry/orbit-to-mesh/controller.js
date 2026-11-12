import {el,button,field,hint,link} from '../dom.js';
import {msg,sourceMessage} from '../i18n.js';
import {chooseSavedReference} from '../images/references.js';
import {VirtualTurntableWizard} from '../virtual-turntable/controller.js';

const t=(key,values)=>msg('orbit.'+key,values);
const stagePages={preparing:2,turnaround:2,orbit:2,cameras:3,views:3,geometry:4,
    refinement:5,texture:5,balanced:5,compact:5,quads:5,print:5,package:5};

export class OrbitToMeshWizard extends VirtualTurntableWizard{
    constructor(shell,options){
        super(shell,options,{
            key:'orbit-to-mesh',stateKey:'foundryOrbitToMesh',title:'Orbit to Mesh',offset:790000,layout:'orbit',
            titles:['Set up your reference','Review the orbit','Choose mesh views','Review the mesh','Finish and export'],
            stagePages,operationPages:{turnaround:2,orbit:2,cameras:3,views:3,reconstruct:4,finish:5,rocket:2},
        });
    }
    initialDraft(){return {...super.initialDraft(),engine:'pixal3d',exclude_views:[]};}
    restoreDraft(run){return {...super.restoreDraft(run),exclude_views:run.exclude_views||[]};}
    handoffPage(){return 1;}
    savedPage(){return this.complete('geometry')?4:this.complete('cameras')?3:this.complete('turnaround')?2:1;}
    get showRocket(){return true;}
    get ready(){return super.ready&&!this.cap.missing.length;}
    get viewsChanged(){return JSON.stringify(this.run?.controls?.views)!==JSON.stringify(this.draft.controls.views);}
    body(){return [this.setup,this.reviewOrbit,this.reviewViews,this.reviewMesh,this.finish][this.page-1].call(this);}
    setup(){
        const useSaved=()=>chooseSavedReference(this.shell,handoff=>this.act(async()=>{
            this.draft.image=handoff.references[0].filename;
            this.draft.name||=handoff.name;
            this.draft.image_creation=handoff.image_creation;
        }));
        const presets=Object.entries(this.cap.orbit_presets);
        const orbit=this.draft.controls.orbit;
        const matches=preset=>Object.entries(preset).every(([key,value])=>orbit[key]===value);
        return el('div',{},hint(sourceMessage(this.cap.description)),hint(sourceMessage(this.cap.tip)),
            this.cap.missing.length?el('div',{class:'warning',role:'alert'},
                hint(t('missing_tools',{files:this.cap.missing.join(', ')})),
                link(t('get_colmap'),this.cap.setup_source)):null,
            this.image([button(msg('mesh.choose_from_gallery'),useSaved,{disabled:this.busy})]),
            el('fieldset',{class:'turntable-control-section'},
                el('legend',{},t('orbit_preset')),
                ...presets.map(([id,values])=>el('label',{class:'check-row'},
                    el('input',{type:'radio',name:'orbit-video-preset',checked:matches(values),disabled:this.busy,
                        onchange:()=>{Object.assign(orbit,values);this.remember();this.render();}}),
                    el('span',{},t('preset_'+id),hint(t('preset_'+id+'_help')))))),
            this.section('turnaround','H3 four-view turnaround'),
            this.section('orbit','360° orbit settings',{visible:['subject_direction']}),
            el('details',{},el('summary',{},t('rocket_outputs')),
                this.input('views','preset'),this.input('texture','texture_size'),this.exportSettings(false)),
            el('details',{},el('summary',{},sourceMessage('Model credits and terms')),
                hint(sourceMessage(this.cap.license_note)),
                ...Object.entries(this.cap.license_links).map(([label,url])=>el('p',{},link(label,url)))));
    }
    reviewOrbit(){
        return el('div',{},super.reviewOrbit(),
            this.complete('orbit')?hint(t('orbit_review_help')):null);
    }
    reviewViews(){
        const frames=this.run?.views||[];
        const exclusions=this.draft.exclude_views;
        const selected=frames.filter(frame=>!exclusions.includes(frame.source_frame)).length;
        return el('div',{},this.orbit(this.run?.active),
            hint(t('frame_review_help')),
            this.section('views','Pixal3D views',{visible:['preset']}),
            el('details',{},el('summary',{},t('advanced_camera')),
                this.section('frames','Reconstruction frames',{advanced:false}),
                this.section('camera','Camera alignment',{advanced:false})),
            frames.length&&!this.viewsChanged?el('section',{},el('h3',{},t('selected_views',{count:selected,total:frames.length})),
                el('div',{class:'orbit-view-grid'},...frames.map((frame,index)=>{
                    const checked=!exclusions.includes(frame.source_frame);
                    const name=index?t('frame_angle',{frame:frame.source_frame,angle:Math.round(frame.solved_degrees)}):t('front_frame');
                    return el('label',{class:'orbit-view','data-selected':String(checked)},
                        el('img',{src:frame.image,alt:name,loading:'lazy'}),
                        el('span',{class:'format-check'},
                            el('input',{type:'checkbox',checked,disabled:this.busy||index===0||checked&&selected<=2,
                                'aria-label':name,onchange:event=>{
                                    this.draft.exclude_views=event.target.checked?exclusions.filter(id=>id!==frame.source_frame)
                                        :[...exclusions,frame.source_frame];
                                    this.remember();this.render();
                                }}),name));
                }))):null,
            this.section('pixal','Pixal3D reconstruction'));
    }
    reviewMesh(){
        return el('div',{},this.orbit(this.run?.active),this.preview('raw','Original reconstruction'),
            hint(t('mesh_review_help')));
    }
    finish(){
        return el('div',{},this.section('refinement','Hi3D and cleanup'),
            this.section('texture','TRELLIS.2 texturing',{visible:['texture_size','texture_triangles']}),
            this.section('bake','Baking and floor placement'),
            this.exportSettings(false),
            this.preview('clean','Clean geometry'),this.preview('texture','Finished textured mesh'),
            this.run?.package?.download?el('a',{href:this.run.package.download,download:''},sourceMessage('Download asset ZIP')):null,
            el('div',{class:'actions'},button(t('copy_recipe'),()=>this.act(async()=>{
                const {controls,overrides,selection,exclude_views}=this.draft;
                await navigator.clipboard.writeText(JSON.stringify({workflow:'orbit-to-mesh',controls,overrides,selection,exclude_views},null,2));
                this.shell.message(t('recipe_copied'));
            }),{disabled:this.busy})));
    }
    next(){
        let operation,label,disabled=this.busy;
        if(this.page===1){
            operation='turnaround';label=sourceMessage('Generate turnaround');disabled||=!this.ready;
        }else if(this.page===2){
            operation=this.complete('orbit')?'cameras':this.complete('turnaround')?'orbit':'turnaround';
            label=operation==='cameras'?t('align_cameras'):sourceMessage(operation==='orbit'?'Generate orbit':'Generate turnaround');
        }else if(this.page===3){
            const cameraChanged=['camera','frames'].some(key=>JSON.stringify(this.run?.controls?.[key])!==JSON.stringify(this.draft.controls[key]));
            operation=!this.complete('cameras')||cameraChanged?'cameras':!this.complete('views')||this.viewsChanged?'views':'reconstruct';
            label=operation==='cameras'?t('align_cameras'):operation==='views'?t('refresh_views'):sourceMessage('Reconstruct mesh');
        }else if(this.page===4&&this.complete('geometry')){
            return button(sourceMessage('Finish and export'),()=>this.go(5),{class:'primary',disabled});
        }else{
            operation=this.page===4?'reconstruct':'finish';
            label=sourceMessage(operation==='finish'?'Prepare asset package':'Reconstruct mesh');
            disabled||=operation==='finish'&&!this.complete('geometry');
        }
        return button(label,()=>this.act(()=>this.start(operation)),{class:'primary',disabled});
    }
    async start(operation){
        if(operation==='views'||operation==='cameras')this.draft.exclude_views=[];
        await super.start(operation);
    }
}
