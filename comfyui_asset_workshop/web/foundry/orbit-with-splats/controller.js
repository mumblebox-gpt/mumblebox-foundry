import {el,button,hint,link} from '../dom.js';
import {msg,setText,sourceMessage} from '../i18n.js';
import {OrbitToMeshWizard} from '../orbit-to-mesh/controller.js';
import {pairedReview,label} from './pair-preview.js';
import {hybridPanel} from './hybrid-render.js';

const stagePages={preparing:2,turnaround:2,orbit:2,cameras:3,views:3,geometry:4,refinement:5,
    texture:5,splat:5,balanced:5,compact:5,quads:5,print:5,package:5};

export class OrbitWithSplatsWizard extends OrbitToMeshWizard {
    constructor(shell,options){
        super(shell,options,{
            key:'orbit-with-splats',stateKey:'foundryOrbitWithSplats',title:label('title'),offset:810000,layout:'orbitSplats',
            titles:['Set up your reference','Review the orbit',label('views'),label('review'),'Finish and export'],
            stagePages,
        });
    }
    artifact(role){return '/mumblebox-foundry/v1/'+this.path('/artifacts/'+role);}
    setup(){
        const root=super.setup();
        if(this.cap.brush?.automatic && !this.cap.brush.present)
            root.prepend(hint(label('brush_auto_setup')));
        else if(this.missing.includes('brush_app.exe'))
            root.prepend(el('section',{class:'turntable-recovery',role:'alert'},hint(label('brush_setup')),
                hint(label('setup_target',{folder:this.cap.brush_folder})),link(label('brush_download'),this.cap.brush_release)));
        return root;
    }
    splatPreset(onChange=()=>this.refreshActions()){
        const {preset}=this.draft.controls.splat;
        const info=el('p',{class:'muted'});
        const refresh=value=>{
            this.draft.controls.splat.preset=value;
            setText(info,label(value+'_help'));
        };
        refresh(preset);
        return el('fieldset',{class:'orbit-splat-preset',disabled:this.busy},
            el('legend',{},label('detail')),
            el('select',{'aria-label':label('detail'),onchange:event=>{
                refresh(event.currentTarget.value);this.remember();onChange();
            }},...Object.keys(this.cap.splat_presets).map(key=>el('option',{value:key,selected:preset===key},label(key)))),
            info,
            button(sourceMessage('Reset to defaults'),()=>{this.draft.controls.splat={...this.cap.defaults.splat};
                this.remember();this.render();if(this.rocketDialog){this.rocketDialog.close();this.openRocket();}},
                {disabled:this.busy}),
            el('details',{class:'turntable-advanced','data-disclosure':'splat'},
                el('summary',{},msg('orbit_splats.advanced')),this.section('splat',label('brush_settings'),{visible:['timeout_minutes'],advanced:false})));
    }
    rocketFields(update){return el('div',{},super.rocketFields(update),this.splatPreset(update));}
    rocketSummary(){
        const summary=super.rocketSummary();
        summary.append(hint(label('rocket_help')));
        return summary;
    }
    reviewViews(){
        return el('div',{},super.reviewViews(),this.splatPreset());
    }
    reviewMesh(){
        if(this.run?.pair&&!this.dirtyStage)return this.reviewPair();
        return el('div',{},super.reviewMesh(),hint(label('finish_help')));
    }
    next(){
        const control=super.next();
        if(this.page===2&&this.complete('cameras')&&!this.dirtyStage)setText(control,label('views'));
        if(this.page===3&&this.complete('geometry')&&!this.dirtyStage)setText(control,label('review'));
        return control;
    }
    reviewPair(){
        const hybrid=hybridPanel(this);
        return el('div',{},pairedReview(this,hybrid.ready),
            el('div',{class:'actions'},...[
                ['paired_mesh','download_mesh','textured-mesh.glb'],
                ['gaussian','download_splat','gaussian-splat.ply'],
                ['pair_zip','download_pair','orbit-with-splats.zip'],
            ].map(([role,key,name])=>el('a',{href:this.artifact(role),download:name},label(key)))),
            hybrid.root);
    }
    finish(){
        return el('div',{},this.run?.pair&&!this.dirtyStage&&!this.busy?this.reviewPair():null,
            this.splatPreset(),super.finish());
    }
}
