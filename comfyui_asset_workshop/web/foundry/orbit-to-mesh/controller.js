import {el,button,field,hint,link} from '../dom.js';
import {msg,sourceMessage} from '../i18n.js';
import {chooseSavedReference} from '../images/references.js';
import {VirtualTurntableWizard} from '../virtual-turntable/controller.js';
import {orbitSettings,ux,viewCount} from '../virtual-turntable/settings.js';

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
    get viewsChanged(){return JSON.stringify(this.run?.controls?.views)!==JSON.stringify(this.draft.controls.views);}
    body(){return [this.setup,this.reviewOrbit,this.reviewViews,this.reviewMesh,this.finish][this.page-1].call(this);}
    setup(){
        const useSaved=()=>chooseSavedReference(this.shell,handoff=>this.act(async()=>{
            this.draft.image=handoff.references[0].filename;
            this.draft.name||=handoff.name;
            this.draft.image_creation=handoff.image_creation;
        }));
        return el('div',{},hint(sourceMessage(this.cap.description)),hint(sourceMessage(this.cap.tip)),
            this.missing.length?el('div',{class:'turntable-recovery',role:'alert'},
                hint(t('missing_tools',{files:this.missing.join(', ')})),
                link(t('get_colmap'),this.cap.setup_source)):null,
            el('div',{class:'turntable-setup-grid'},
                this.image([button(msg('mesh.choose_from_gallery'),useSaved,{disabled:this.busy})]),
                orbitSettings(this)),
            this.section('turnaround','H3 four-view turnaround'),
            el('details',{},el('summary',{},sourceMessage('Model credits and terms')),
                hint(sourceMessage(this.cap.license_note)),
                ...Object.entries(this.cap.license_links).map(([label,url])=>el('p',{},link(label,url)))));
    }
    rocketFields(update){return viewCount(this,update);}
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
            this.section('views','Pixal3D views',{visible:['preset'],extra:viewCount(this,()=>{
                this.refreshActions();
                const notice=this.host.querySelector('.orbit-stale-views');
                if(notice)notice.hidden=!this.viewsChanged;
                const grid=this.host.querySelector('.orbit-matched-views');
                if(grid)grid.hidden=this.viewsChanged;
            })}),
            el('details',{},el('summary',{},t('advanced_camera')),
                this.section('frames','Reconstruction frames',{advanced:false}),
                this.section('camera','Camera alignment',{advanced:false})),
            frames.length?el('p',{class:'muted orbit-stale-views',role:'status',hidden:!this.viewsChanged},ux('refresh_views_help')):null,
            frames.length?el('section',{class:'orbit-matched-views',hidden:this.viewsChanged},el('h3',{},t('selected_views',{count:selected,total:frames.length})),
                el('div',{class:'orbit-view-grid'},...frames.map((frame,index)=>{
                    const checked=!exclusions.includes(frame.source_frame);
                    const name=index?t('frame_angle',{frame:frame.source_frame,angle:Math.round(frame.solved_degrees)}):t('front_frame');
                    return el('label',{class:'orbit-view','data-selected':String(checked)},
                        el('img',{src:frame.image,alt:name,loading:'lazy'}),
                        el('span',{class:'format-check'},
                            el('input',{type:'checkbox',checked,disabled:this.busy||index===0||checked&&selected<=2,
                                id:this.key+'-frame-'+frame.source_frame,'aria-label':name,onchange:event=>{
                                    this.draft.exclude_views=event.target.checked?exclusions.filter(id=>id!==frame.source_frame)
                                        :[...exclusions,frame.source_frame];
                                    this.remember();this.renderAt(this.key+'-frame-'+frame.source_frame);
                                }}),name));
                }))):null,
            this.section('pixal','Pixal3D reconstruction',{visible:['shape_resolution']}));
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
        const changed=this.dirtyStage;
        if(this.page===1){
            return this.complete('turnaround')&&changed!=='turnaround'
                ?this.runButton('Review the orbit','orbit',()=>this.go(2))
                :this.runButton('Generate turnaround','turnaround');
        }
        if(this.page===2){
            if(!this.complete('turnaround')||changed==='turnaround')return this.runButton('Generate turnaround','turnaround');
            if(!this.complete('orbit')||changed==='orbit')return this.runButton('Generate orbit','orbit');
            if(!this.complete('cameras')||changed==='cameras')return this.runButton(t('align_cameras'),'cameras');
            return this.runButton('Choose mesh views','views',()=>this.go(3));
        }
        if(this.page===3){
            if(changed==='turnaround'||changed==='orbit')return this.runButton(ux('review_earlier_step'),'orbit',()=>this.go(2));
            if(!this.complete('cameras')||changed==='cameras')return this.runButton(t('align_cameras'),'cameras');
            if(!this.complete('views')||this.viewsChanged)return this.runButton(t('refresh_views'),'views');
            if(this.complete('geometry')&&changed!=='reconstruct')
                return this.runButton('Review the mesh','reconstruct',()=>this.go(4));
            return this.runButton('Reconstruct mesh','reconstruct');
        }
        if(this.page===4){
            if(['turnaround','orbit','cameras','views'].includes(changed))
                return this.runButton(ux('review_earlier_step'),'reconstruct',()=>this.go(changed==='turnaround'||changed==='orbit'?2:3));
            return this.complete('geometry')&&changed!=='reconstruct'
                ?this.runButton('Finish and export','finish',()=>this.go(5))
                :this.runButton('Reconstruct mesh','reconstruct');
        }
        return this.finishButton();
    }
    async start(operation){
        if(operation==='views'||operation==='cameras')this.draft.exclude_views=[];
        await super.start(operation);
    }
}
