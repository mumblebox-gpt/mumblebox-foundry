import {msg, setText, appendContent} from "../i18n.js";
import {problemPanel} from '../problem-panel.js';
import {api} from '/scripts/api.js';
import {app} from '/scripts/app.js';
import {el,button,hint,field} from '../dom.js';
import {request} from '../services.js';
import {dialog} from '../dialogs.js';
import {activity,elapsedTime} from '../activity.js';
import {uploadReference,capturePhoto,galleryReference,inputURL} from '../images/references.js';
import {hairFileURL,displayFiles,imageSheet,hairViewer,variationCards,preprocessingWarnings} from './review.js';

const titles=[msg("hair.starting_image"),msg("hair.generation_options"),msg("hair.generate_and_review"),msg("hair.head_and_materials"),msg("hair.motion_and_exports"),msg("hair.finished_result")];
const blurbs=['A clear view of the hairstyle','Defaults and optional variations','Compare saved hair and chains','Fit and surface appearance','Static or skinned deliverables','Files, measurements and History'];
const clone=value=>JSON.parse(JSON.stringify(value));
const fileURL=hairFileURL;

export class HairWizard {
    constructor(shell,{resume=false,runId=null,capabilities=null}={}){
        this.shell=shell;this.providedCapabilities=capabilities;this.host=el('section',{class:'wizard hair-wizard','aria-label':msg("hair.hairdeck_creation_wizard")});
        const saved=resume?shell.node.properties.foundryHair:null;
        this.page=saved?.page||1;this.runId=runId||saved?.runId;this.draft=saved?.draft;this.selected=saved?.selected;this.reviewState=saved?.reviewState||{};this.resuming=!!saved;this.fromAgent=!!runId;this.disposers=[];
    }
    async init(){
        this.cap=this.providedCapabilities||await request('hair/capabilities');
        this.draft=this.draft?{...clone(this.cap.defaults),colors:false,...this.draft}:clone(this.cap.defaults);
        if(this.runId){this.run=await request('hair/runs/'+this.runId);if(!this.resuming)this.draft=clone(this.run.config);this.selected??=this.run.selected||0;
            if(this.fromAgent||this.run.active)this.page=this.run.package||this.run.operation==='export'?6:this.run.operation==='preview'?4:['motion_preview','avatar_preview'].includes(this.run.operation)?5:this.run.variants.length||this.run.active?3:1;}
        if(!this.shell.root.querySelector('link[data-hair]'))this.shell.root.append(el('link',{rel:'stylesheet',href:new URL('./hair.css',import.meta.url).href,'data-hair':''}));
        if(!this.shell.root.querySelector('link[data-hair-review]'))this.shell.root.append(el('link',{rel:'stylesheet',href:new URL('./review.css',import.meta.url).href,'data-hair-review':''}));
        this.render();this.poll();return this.host;
    }
    remember(){this.shell.node.properties.foundryHair={page:this.page,runId:this.runId,selected:this.selected||0,reviewState:clone(this.reviewState||{}),draft:clone(this.draft)};app.graph.setDirtyCanvas(true);}
    go(page){this.page=page;this.remember();this.render();this.shell.content.scrollTop=0;}
    async act(action){
        if(this.working)return;this.working=true;this.error='';
        try{await action();}catch(error){this.error=error.message;}finally{this.working=false;this.remember();this.render();}
    }
    async save(){
        if(!this.runId){this.run=await request('hair/runs',this.draft);this.runId=this.run.id;}
        else this.run=await request('hair/runs/'+this.runId,this.draft,{method:'PATCH'});
        this.remember();
    }
    async start(operation){
        await this.save();
        const graph=await request('hair/runs/'+this.runId+'/graph?'+new URLSearchParams({operation,selected:operation==='generate'?Math.min(this.run.variants.length,this.draft.variations-1):this.selected||0}));
        this.syncGraph({pending:{graph}});
        this.run=await request('hair/runs/'+this.runId+'/start',{operation,selected:this.selected||0,request_id:crypto.randomUUID(),client_id:api.clientId||''});
        if(operation==='generate')this.page=3;else if(operation==='export')this.page=6;
        if(operation==='generate'||operation==='export')this.shell.content.scrollTop=0;
        this.remember();
    }
    async poll(){
        if(this.disposed)return;
        try{
            if(this.runId){
                const next=await request('hair/runs/'+this.runId);
                if(this.disposed)return;
                const changed=JSON.stringify([next.active,next.status,next.stage,next.error,next.dependency,next.variants.map(v=>v.checkpoint),next.export?.model,next.preview?.model,next.avatar_preview?.model,next.motion_preview?.model,next.package])!==JSON.stringify([this.run?.active,this.run?.status,this.run?.stage,this.run?.error,this.run?.dependency,this.run?.variants?.map(v=>v.checkpoint),this.run?.export?.model,this.run?.preview?.model,this.run?.avatar_preview?.model,this.run?.motion_preview?.model,this.run?.package]);
                this.run=next;
                if(next.pending)this.syncGraph(next);
                if(changed)this.render();
                this.paintProgress();
            }
        }catch(error){this.error=error.message;this.render();}
        finally{if(!this.disposed)this.timer=setTimeout(()=>this.poll(),1000);}
    }
    syncGraph(run){
        // Only these independently grouped nodes are touched. The body and image
        // workflows keep their widgets, links and completed preview state.
        for(const [id,item] of Object.entries(run.pending.graph)){
            const node=app.graph.getNodeById(+id);if(!node)continue;
            for(const [key,value] of Object.entries(item.inputs)){
                if(Array.isArray(value))continue;
                const widget=node.widgets?.find(w=>w.name===key||(id==='70000'&&key==='filename'&&w.name==='image'));
                if(widget)widget.value=value;
            }
        }
    }
    paintProgress(){
        const value=this.run?.progress||0;
        const overall=this.run?.operation==='generate'?Math.round(value*.6):['preview','motion_preview'].includes(this.run?.operation)?60+Math.round(value*.1):70+Math.round(value*.3);
        if(this.progress)this.progress.value=overall;
        if(this.progressText)setText(this.progressText, msg("hair.overall", {overall: overall, stage: this.run.stage}));
    }
    text(key,label,description){return field(label,el('input',{value:this.draft[key],maxLength:120,oninput:e=>{this.draft[key]=e.target.value;this.remember();}}),description);}
    number(key,label,min,max,step=1){return field(label,el('input',{type:'number',value:this.draft[key],min,max,step,onchange:e=>{this.draft[key]=Number(e.target.value);this.remember();}}));}
    select(key,label,choices,description){return field(label,el('select',{onchange:e=>{this.draft[key]=e.target.value;this.remember();}},...choices.map(choice=>{
        const [value,name]=Array.isArray(choice)?choice:[choice,choice];return el('option',{value,selected:this.draft[key]===value},name);
    })),description);}
    check(key,label,description){return el('label',{class:'hair-check'},el('input',{type:'checkbox',checked:this.draft[key],onchange:e=>{
        this.draft[key]=e.target.checked;if(key==='bones'&&!e.target.checked){this.draft.vrm=false;this.draft.motion=false;}
        this.remember();if(key==='bones')this.render();}}),el('span',{},el('strong',{},label),description?hint(description):null));}
    async add(file){this.draft.image=(await uploadReference(file)).filename;this.remember();}
    async gallery(){
        let cursor='';const list=el('div',{class:'hair-gallery'});
        const more=button(msg("hair.more_images"),()=>this.act(load));
        const load=async()=>{
            const page=await request('images?limit=12'+(cursor?'&cursor='+cursor:''));cursor=page.next_cursor;
            for(const item of page.items){for(const [side,id] of Object.entries(item.accepted||{})){
                const url='/mumblebox-foundry/v1/images/'+item.id+'/files/'+id;
                list.append(button([el('img',{src:url,alt:item.name+' '+side}),el('span',{},item.name+' · '+side)],()=>this.act(async()=>{
                    const handoff=await galleryReference(item.id,side,id);
                    this.draft.image=handoff.references[0].filename;this.remember();modal.close();
                }),{class:'image-preview'}));
            }}more.hidden=!cursor;if(!list.children.length)appendContent(list, hint(msg("hair.no_saved_images_yet_upload_a_reference_or_take_a_photo")));
        };
        const modal=dialog(this.shell,msg("hair.choose_a_saved_hairstyle_reference"),el('div',{},list,more));await load();
    }
    examples(){
        const list=el('div',{class:'hair-gallery'});
        const modal=dialog(this.shell,msg("hair.try_an_official_hairdeck_reference"),el('div',{},list,hint(msg("hair.reference_examples_provided_by_the_hairdeck_authors"))));
        for(const item of this.cap.examples||[]){
            appendContent(list, button([el('img',{src:item.url,alt:msg("hair.hairdeck_reference", {label: item.label})}),el('span',{},item.label)],()=>this.act(async()=>{
                const reference=await request('hair/examples/'+item.id+'/use',{});
                this.draft.image=reference.filename;this.remember();modal.close();
            }),{class:'image-preview'}));
        }
    }
    inputPage(){
        const input=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,onchange:e=>this.act(()=>this.add(e.target.files[0]))});
        const drag=e=>{e.preventDefault();e.stopPropagation();if(e.dataTransfer)e.dataTransfer.dropEffect='copy';};
        return el('div',{},this.text('name','Asset name'),hint(this.cap.reference),
            el('div',{class:'creator-drop',ondragenter:drag,ondragover:drag,ondrop:e=>{
                drag(e);const file=e.dataTransfer?.files?.[0];if(file)this.act(()=>this.add(file));
            },tabIndex:0,onpaste:e=>{const file=[...(e.clipboardData?.items||[])].find(x=>x.type.startsWith('image/'))?.getAsFile();if(file){e.preventDefault();this.act(()=>this.add(file));}}},input,
                this.draft.image?el('img',{class:'hair-reference',src:inputURL(this.draft.image),alt:msg("hair.starting_hairstyle_reference")}):hint(msg("hair.drop_one_head_or_upper_body_reference_here")),
                el('div',{class:'actions'},button(msg("hair.upload_image"),()=>input.click()),button(msg("hair.take_a_photo_with_connected_camera"),()=>capturePhoto(this.shell,file=>this.act(()=>this.add(file))),{disabled:!navigator.mediaDevices}),button(msg("hair.choose_from_gallery"),()=>this.act(()=>this.gallery())),button(msg("hair.try_a_hairdeck_example"),()=>this.examples()))),
            hint(msg("hair.keep_the_whole_hairstyle_in_frame_avoid_heavy_occlusion_and_cropped_hair_hai")));
    }
    optionsPage(){
        const advanced=el('details',{},el('summary',{},msg("hair.advanced_generation_settings")),el('div',{class:'hair-grid'},this.number('steps','Sampling steps',1,200),this.number('cfg','Guidance (CFG)',1,4,.25)),hint(msg("hair.recommended_50_steps_cfg_2_chain_generation_uses_hairdeck_s_matching_50_step")));
        for(const [role,current] of Object.entries(this.draft.checkpoints)){
            const names=this.cap.checkpoints[role]?.length?this.cap.checkpoints[role]:[current];
            advanced.append(field(role.replaceAll('_',' '),el('select',{onchange:e=>{this.draft.checkpoints[role]=e.target.value;this.remember();}},...names.map(name=>el('option',{value:name,selected:name===current},name)))));
        }
        return el('div',{},hint(msg("hair.hairdeck_generates_volumetric_hair_cards_and_can_generate_matching_spring_bo")),
            el('div',{class:'hair-grid'},this.number('seed','Seed',0,Number.MAX_SAFE_INTEGER-16),this.number('variations','Variations',1,4)),
            this.check('colors','Preserve the reference’s per-card colors','HairDeck’s color model predicts 16 colors along every card, including colored tips and ribbons. Turn off for a single measured hair color.'),
            this.check('bones','Generate spring bones','Required for rigged VRM and the motion preview. Variations run sequentially to limit memory use.'),advanced,
            hint(msg("hair.before_generation_foundry_prepares_all_required_weights_and_selected_rig_exp")));
    }
    viewer(item){return hairViewer(this,item);}
    reviewPage(){
        const item=this.run?.variants?.[this.selected||0];
        return el('div',{},hint(msg("hair.compare_every_variation_then_select_the_one_to_fit_style_and_export_these_ar")),
            variationCards(this),item?this.measurements(item):null,
            item&&!item.bone_model?button(msg("hair.add_spring_bones_to_this_saved_variation"),()=>this.act(async()=>{
                this.draft.bones=true;await this.start('rig');
            }),{disabled:this.run?.active}):null,
            item?el('section',{class:'hair-sheet-section'},el('h3',{},msg("hair.what_hairdeck_interpreted")),hint(msg("hair.review_the_crop_and_segmentation_before_continuing_if_the_hairstyle_is_cropp")),
                ...preprocessingWarnings(item).map(text=>el('p',{class:'warning-panel',role:'status'},text)),imageSheet(this,item,'input')):null,
            item?el('section',{class:'hair-sheet-section'},el('h3',{},msg("hair.generated_hair_multi_view_sheet")),imageSheet(this,item,'result')):null);
    }
    colorControl(){
        const automatic=this.draft.color==='auto';
        const chosen=/^#[0-9a-f]{6}$/i.test(this.draft.color)?this.draft.color:(this.customColor||'#884422');
        const picker=el('input',{type:'color',value:chosen,'aria-label':msg("hair.choose_hair_color")});
        const hex=el('input',{type:'text',value:chosen,maxLength:7,spellcheck:false,'aria-label':msg("hair.hair_color_hex_code")});
        const custom=el('div',{class:'hair-color-custom',hidden:automatic},picker,hex);
        const set=value=>{this.draft.color=value;this.customColor=value;this.remember();};
        picker.addEventListener('input',()=>{hex.value=picker.value;hex.removeAttribute('aria-invalid');set(picker.value);});
        hex.addEventListener('input',()=>{const valid=/^#[0-9a-f]{6}$/i.test(hex.value);hex.setAttribute('aria-invalid',String(!valid));if(valid)picker.value=hex.value;set(hex.value);});
        return el('div',{class:'hair-color-control'},field(msg("hair.hair_color"),el('select',{'aria-label':msg("hair.hair_color_source"),onchange:e=>{
            custom.hidden=e.target.value==='auto';this.draft.color=custom.hidden?'auto':picker.value;this.remember();
        }},el('option',{value:'auto',selected:automatic},msg("hair.use_reference_colors")),el('option',{value:'custom',selected:!automatic},msg("hair.choose_a_color")))),custom,
        hint(msg("hair.reference_colors_preserve_hairdeck_s_prediction_a_chosen_color_replaces_it_t")));
    }
    materialsPage(){
        const selected=this.run?.variants?.[this.selected||0];
        const item=this.run?.export?.checkpoint===selected?.checkpoint?this.run.export:
            selected?.reviews?.preview||(this.run?.preview?.checkpoint===selected?.checkpoint?this.run.preview:selected);
        const fitting=el('details',{},el('summary',{},msg("hair.fitting_adjustments")),this.number('scale','Uniform hair scale',.25,4,.01),
            ...['X','Y','Z'].map((axis,index)=>field(msg("hair.offset_metres", {axis: axis}),el('input',{type:'number',step:.005,min:-1,max:1,value:this.draft.offset[index],onchange:e=>{this.draft.offset[index]=Number(e.target.value);this.remember();}}))),
            hint(msg("hair.moves_and_scales_the_generated_hair_and_its_matching_chains_together_it_does")));
        return el('div',{},el('div',{class:'hair-materials'},el('div',{},this.viewer(item),imageSheet(this,item,'result')),el('div',{},
            this.select('head_profile','Reference head',this.cap.heads.map(x=>[x,x==='upstream'?'HairDeck reference head':x])),
            this.check('show_head','Include reference head in static GLB','The VRM export includes its reference avatar.'),fitting,
            this.colorControl(),
            this.select('material','Material preset',[['volume',msg("hair.volumetric_locks")],['ribbon',msg("hair.transparent_hair_cards")],['solid',msg("hair.solid_geometry_diagnostic")],['checker',msg("hair.uv_checker")]]),
            this.select('uv_mode','UV layout',[['shared',msg("hair.shared_atlas_recommended")],['unique',msg("hair.unique_areas_for_painting")]]),this.select('texture_size','Texture resolution',['1K','2K','4K']),
            this.draft.colors?hint(msg("hair.predicted_per_card_colors_use_unique_uv_areas_so_each_card_keeps_its_own_roo")):null,
            button(msg("hair.preview_these_changes"),()=>this.act(()=>this.start('preview')),{disabled:this.run?.active,class:'primary'}),hint(msg("hair.applies_fitting_color_and_material_choices_to_the_saved_hair_no_new_hair_gen")))),
            el('section',{class:'hair-sheet-section'},el('h3',{},msg("hair.material_maps_and_uv_layout")),hint(msg("hair.these_are_the_maps_used_by_this_saved_preview_click_a_map_to_inspect_it_at_f")),imageSheet(this,item,'material')));
    }
    exportPage(){
        const selected=this.run?.variants?.[this.selected||0];
        const motionItem=selected?.reviews?.motion_preview||(this.run?.motion_preview?.checkpoint===selected?.checkpoint?this.run.motion_preview:null);
        const motion=motionItem?.files?.find(f=>f.filename.endsWith('.mp4'));
        const avatar=selected?.reviews?.avatar_preview||(this.run?.avatar_preview?.checkpoint===selected?.checkpoint?this.run.avatar_preview:motionItem);
        return el('div',{},hint(msg("hair.choose_the_files_to_deliver_the_package_includes_an_accurate_readme_measurem")),
        selected?el('h3',{},msg("hair.variation_seed", {value1: (this.selected||0)+1, seed: selected.measurements.seed})):null,
        this.draft.bones?el('div',{class:'actions'},button(msg("hair.preview_rigged_avatar"),()=>this.act(()=>this.start('avatar_preview')),{disabled:this.run?.active}),button(msg("hair.preview_hair_motion"),()=>this.act(()=>this.start('motion_preview')),{disabled:this.run?.active})):null,
        this.draft.bones?this.check('motion_chains','Show predicted chains in the motion video','An optional diagnostic overlay. The clean static GLB remains free of display chains.'):null,
        motion?el('section',{},el('h3',{},msg("hair.hairdeck_spring_bone_motion")),el('video',{controls:true,loop:true,preload:'metadata',class:'hair-motion',src:fileURL(this.runId,motion.subfolder+'/'+motion.filename)}),hint(msg("hair.hairdeck_s_head_turn_simulation_this_is_not_a_360_degree_orbit_or_an_exporta"))):null,
        avatar?el('section',{},el('h3',{},msg("hair.skinned_avatar_review")),imageSheet(this,avatar,'result'),this.measurements(avatar),hint(avatar.measurements.rig?.ok?msg("hair.vrm_validation_passed_skinning_and_spring_groups_were_checked"):msg("hair.review_the_rig_validation_before_exporting"))):null,
        this.check('glb','Static GLB','Portable hair geometry, UVs and material. Contains no spring-bone rig.'),
        this.draft.bones?this.check('vrm','Rigged VRM 0.x','Hair bound to the selected reference avatar, with skinning and spring-bone groups.'):hint(msg("hair.spring_bones_are_off_return_to_generation_options_to_enable_vrm_or_motion")),
        this.draft.bones?this.check('motion','Head-turn motion preview (MP4)','A rendered demonstration, not an animation clip. This adds processing time.'):null,
        this.check('diagnostics','Preprocessing and review images','Hair/face masks, model-input crop and review renders.'),this.check('source_data','Editable source data','Card and chain curves, sampled tokens and generated surface arrays.'),
        hint(msg("hair.material_maps_and_uv_layout_accompany_the_selected_geometry_a_zip_and_saved")));
    }
    measurements(item){const m=item.measurements||{};return el('dl',{class:'hair-stats'},...Object.entries({Cards:m.hair_cards,'Predicted chains':m.generated_chains,'Spring groups':m.rig?.n_spring_groups,'Hair vertices':m.geometry?.vertices,'Hair triangles':m.geometry?.triangles,'Seed':m.seed}).filter(([,value])=>value!==undefined).map(([label,value])=>el('div',{},el('dt',{},label),el('dd',{},String(value)))));}
    finishedPage(){
        const item=this.run?.export;
        const downloads=(item?.files||[]).filter(f=>this.draft.glb&&f.filename.endsWith('.glb')||this.draft.vrm&&f.filename.endsWith('.vrm')||this.draft.motion&&f.filename.endsWith('.mp4'));
        return el('div',{},this.viewer(item),item?this.measurements(item):null,imageSheet(this,item,'result'),
            this.run?.package?el('div',{class:'actions'},el('a',{class:'primary',href:fileURL(this.runId,this.run.package.path,true)},msg("hair.download_zip")),button(msg("hair.open_history"),()=>this.shell.open('History'))):null,
            ...downloads.map(f=>el('p',{},el('a',{href:fileURL(this.runId,f.subfolder+'/'+f.filename,true)},f.filename))),
            item?.files.find(f=>f.filename.endsWith('.mp4'))?el('video',{controls:true,preload:'metadata',class:'hair-motion',src:fileURL(this.runId,item.files.find(f=>f.filename.endsWith('.mp4')).subfolder+'/'+item.files.find(f=>f.filename.endsWith('.mp4')).filename)}):null,
            hint(msg("hair.static_glb_is_unrigged_vrm_contains_skinning_and_spring_data_inspect_it_with")));
    }
    render(){
        this.disposers.splice(0).forEach(f=>f());
        this.host.dataset.page=String(this.page);
        const busy=!!this.run?.active||this.working;
        const rail=el('aside',{class:'wizard-rail'},el('span',{class:'eyebrow'},msg("hair.hairdeck_hair")),el('h3',{},msg("hair.hairdeck_stylized_hair")),el('ol',{class:'wizard-steps'},...titles.map((title,i)=>el('li',{class:i+1===this.page?'current':''},el('span',{},String(i+1)),el('div',{},el('strong',{},title),el('small',{},blurbs[i]))))),hint(msg("hair.one_image_hair_cards_matching_spring_bones")));
        const panel=el('div',{class:'wizard-panel'},el('header',{class:'page-head'},el('span',{class:'eyebrow'},msg("hair.page_of_6", {page: this.page})),el('h2',{},titles[this.page-1])));
        if(this.run?.active){const a=activity();a.update({busy:true,label:msg("hair.hairdeck", {stage: this.run.stage}),detail:this.run.dependency?.message||this.run.dependency?.name||'Completed hair variations remain saved.'});this.progress=el('progress',{max:100,value:this.run.progress||0,'aria-label':msg("hair.overall_hairdeck_workflow_progress")});this.progressText=el('strong',{},'');panel.append(el('div',{class:'hair-progress'},a.element,elapsedTime(this.run.started_at*1000),this.progress,this.progressText));}
        const error=this.error||this.run?.error;if(error)panel.append(problemPanel(error));
        const navigation=()=>el('footer',{class:'wizard-footer actions'},this.page>1?button(msg("hair.back"),()=>this.go(this.page-1),{disabled:busy}):null,
            this.page<6?button(msg("hair.next"),()=>this.act(async()=>{
                if(this.page===2)await this.start('generate');else if(this.page===5)await this.start('export');else this.go(this.page+1);
            }),{class:'primary',disabled:busy||this.page===1&&!this.draft.image||this.page===3&&!this.run?.variants?.length}):null,
            this.run?.active?button(msg("hair.cancel_stage"),()=>this.act(async()=>{this.run=await request('hair/runs/'+this.runId+'/cancel',{});})):null,
            this.page===6&&!busy?button(msg("hair.make_a_new_hair_asset"),()=>this.shell.openHairWizard(),{class:'primary'}):null,
            !busy&&['failed','interrupted','cancelled'].includes(this.run?.status)?button(msg("hair.retry_remaining_work"),()=>this.act(()=>this.start(this.run.operation))):null,
            button(msg("hair.choose_a_workflow"),()=>this.shell.open('Choose a Workflow')));
        panel.append(this[['inputPage','optionsPage','reviewPage','materialsPage','exportPage','finishedPage'][this.page-1]]());
        appendContent(panel, hint(this.page===2?msg("hair.clicking_next_generates_hair_cards_and_matching_spring_chains"):this.page===5?msg("hair.clicking_next_prepares_the_selected_outputs_package_and_history_entry"):''), navigation());
        this.host.replaceChildren(rail,panel);this.paintProgress();
        if(this.page===6&&this.run?.export&&!busy)requestAnimationFrame(()=>{
            if(this.disposed||this.page!==6)return;
            const viewer=this.host.querySelector('.hair-viewer'),content=this.shell.content;
            if(!viewer)return;
            const frame=viewer.getBoundingClientRect(),area=content.getBoundingClientRect();
            if(frame.height<=area.height&&(frame.top<area.top||frame.bottom>area.bottom))
                content.scrollTop+=frame.top-area.top-(area.height-frame.height)/2;
        });
    }
    dispose(){this.disposed=true;clearTimeout(this.timer);this.disposers.splice(0).forEach(f=>f());}
}
