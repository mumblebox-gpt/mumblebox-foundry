import {msg} from "../i18n.js";
import {el,button,hint,field,link} from '../dom.js';
import {capturePhoto,inputURL} from '../images/references.js';
import {fileURL} from './controller.js';
import {comparison} from './comparison.js';
export const titles=[msg("splat.starting_image"),msg("splat.generation_options"),msg("splat.splat_and_original_mesh"),msg("splat.refine_and_clean"),msg("splat.review_your_outputs"),msg("splat.finished_asset")];
export const blurbs=['One complete subject','Quality and selected files','Inspect Idol’s reconstruction','Optional refinement and repair','Compare detail and geometry','Downloads and saved History'];
export function page(w){return [input,options,generation,cleanup,review,result][w.page-1](w);}
function input(w){
    const file=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,onchange:e=>w.act(()=>w.upload(e.target.files[0]))});
    const drop=el('div',{class:'reference-drop',tabIndex:0,ondragover:e=>{e.preventDefault();e.stopPropagation();},ondrop:e=>{e.preventDefault();e.stopPropagation();w.act(()=>w.upload(e.dataTransfer.files[0]));}},
        hint(msg("splat.drop_one_image_here_or_choose_an_input_below")),file,w.draft.image?el('img',{src:inputURL(w.draft.image),alt:msg("splat.starting_asset_reference"),style:'max-height:320px;max-width:100%'}):null,
        el('div',{class:'actions'},button(msg("splat.upload_image"),()=>file.click()),button(msg("splat.take_a_photo"),()=>capturePhoto(w.shell,f=>w.act(()=>w.upload(f)))),button(msg("splat.choose_from_gallery"),()=>w.gallery())));
    return el('div',{},w.text('name','Asset name'),hint(msg("splat.use_one_clear_image_with_the_entire_subject_visible_a_three_quarter_view_can")),drop,
        hint(msg("splat.idol_by_sperid_labs_creates_a_detailed_gaussian_splat_and_an_extracted_mesh")),
        el('div',{class:'actions'},...w.cap.models.map(m=>link(m.name+' · '+m.creator,m.url))),w.nav({next:()=>w.go(2)}));
}
function options(w){
    const mode=w.draft.generation_mode||'standard';
    const modes=el('fieldset',{},el('legend',{},msg("splat.idol_generation_mode")),
        ...[['standard',msg("splat.standard_default"),msg("splat.use_the_established_recipe_with_adjustable_steps_and_guidance")],
            ['turbo',msg("splat.turbo_experimental"),msg("splat.use_the_two_idol_turbo_adapters_and_five_sampling_steps_fine_detail_may_be_s")]].map(([value,label,description])=>
            el('label',{class:'check-row'},el('input',{type:'radio',name:'idol-generation-mode',value,checked:mode===value,
                onchange:()=>{w.draft.generation_mode=value;w.remember();w.render();}}),el('span',{},label,hint(description)))));
    const names={splat:'Gaussian splat (SPZ)',raw:'Original extracted mesh (GLB)',master:'Cleaned master (GLB)',companion:'Lightweight companion (GLB)',presentation:'Crease-normal presentation copies (GLB)',orbit:'Splat orbit video (MP4)',previews:'Untextured preview images (PNG)',zip:'Downloadable ZIP package'};
    const selection=el('fieldset',{},el('legend',{},msg("splat.files_to_keep_in_the_package")),...Object.entries(names).map(([key,label])=>el('label',{class:'check-row'},el('input',{type:'checkbox',checked:w.draft.outputs[key],onchange:e=>{w.draft.outputs[key]=e.target.checked;w.remember();}}),el('span',{},label))));
    const advanced=el('details',{},el('summary',{},msg("splat.advanced_generation_settings")),w.number('seed','Idol seed',0,2**53-16),mode==='standard'?w.number('steps','Sampling steps',1,100):null,mode==='standard'?w.number('cfg','Guidance',.1,20,.1):null,w.number('image_size','Reference preparation size',256,2048,64),w.number('gaussians','Gaussian count',32768,1048576,32768),w.number('decoder_seed','Decoder seed',0,2**53-16),w.number('mesh_resolution','Splat mesh extraction resolution',128,1024,64),w.number('orbit_size','Orbit image size',256,2048,64),w.number('orbit_frames','Orbit frames',16,180),w.number('orbit_fps','Orbit frames per second',1,60));
    return el('div',{},hint(msg("splat.the_defaults_reproduce_our_tested_lander_workflow_higher_settings_increase_m")),
        modes,w.check('refine','Use Hi3D geometry refinement','Can improve the extracted mesh before cleanup. Adds processing time. The original splat and extracted mesh are preserved.'),
        selection,advanced,hint(msg("splat.selected_model_files_are_checked_and_downloaded_before_processing_the_splat")),w.nav({next:()=>w.start('generation'),nextText:mode==='turbo'?'Generate with Idol Turbo':'Generate with Idol'}));
}
function generation(w){return el('div',{},hint(msg("splat.review_the_splat_and_its_original_mesh_the_splat_preserves_appearance_the_me")),w.artifact('orbit',msg("splat.splat_orbit")),w.artifact('splat',msg("splat.gaussian_splat"),{preview:true}),w.artifact('raw',msg("splat.original_mesh"),{preview:true}),w.nav({next:()=>w.go(4),nextText:msg("splat.review_cleanup_settings")}));}
function cleanup(w){
    const resolution=el('select',{value:String(w.draft.refine_resolution),onchange:e=>{w.draft.refine_resolution=Number(e.target.value);w.remember();}},...[512,1024,1536].map(v=>el('option',{value:String(v),selected:v===w.draft.refine_resolution},String(v))));
    const mode=el('select',{onchange:e=>{w.draft.repair_mode=e.target.value;w.remember();}},el('option',{value:'rebuild',selected:w.draft.repair_mode==='rebuild'},msg("splat.solid_rebuild_tested_default")),el('option',{value:'auto',selected:w.draft.repair_mode==='auto'},msg("splat.connectivity_based_automatic_repair")));
    return el('div',{},hint(msg("splat.hi3d_can_recover_more_useful_structure_comfyui_then_closes_the_surface_gentl")),
        w.check('refine','Use Hi3D refinement'),w.number('companion_triangles','Companion triangle target',1000,500000,1000),
        hint(msg("splat.the_final_solid_rebuild_can_change_the_exact_triangle_count_fine_rails_anten")),
        el('details',{},el('summary',{},msg("splat.advanced_refinement_and_cleanup")),field(msg("splat.hi3d_resolution"),resolution),w.number('refine_steps','Hi3D steps',1,100),w.number('refine_seed','Hi3D seed',0,2**53-16),w.check('cpu_offload','Allow CPU offload'),
            w.number('master_resolution','Master remesh resolution',64,1024,32),w.number('master_smoothing','Gentle smoothing iterations',0,10),w.number('master_band','Master closing band',.5,4,.1),w.number('drop_small_components','Small-component filter',0,.1,.0001),w.number('repair_resolution','Companion repair resolution',32,256,8),field(msg("splat.companion_repair"),mode),hint(msg("splat.automatic_repair_checks_connectivity_an_independent_exported_mesh_audit_also")),w.number('crease_angle','Presentation crease angle',1,180)),
        w.nav({next:()=>w.start('cleanup'),nextText:msg("splat.refine_and_clean")}),button(msg("splat.review_saved_meshes"),()=>w.go(5),{disabled:!w.run?.artifacts?.master}));
}
function review(w){return el('div',{},hint(msg("splat.compare_the_preserved_splat_clean_master_and_lightweight_companion_closed_ge")),
    comparison(w),
    w.run?.quality?el('details',{},el('summary',{},msg("splat.recorded_geometry_checks")),el('pre',{},JSON.stringify(w.run.quality,null,2))):null,
    w.nav({next:()=>w.start('export'),nextText:msg("splat.save_selected_package")}));}
function result(w){
    const actions=el('div',{class:'actions'},button(msg("splat.review_meshes"),()=>w.go(5)),button(msg("splat.new_splat_asset"),()=>w.shell.openSplatWizard()),button(msg("splat.choose_a_workflow"),()=>w.shell.open('Choose a Workflow')));
    return el('div',{},w.run?.package?hint(msg("splat.your_selected_files_are_saved_with_a_readable_catalog_model_credits_and_a_hi")):hint(msg("splat.the_selected_stages_are_processing_completed_results_remain_saved_as_the_wor")),
    w.run?.artifacts?.companion?comparison(w):w.artifact('orbit',msg("splat.splat_orbit")),
        w.run?.package?.zip_selected?link(msg("splat.download_asset_zip"),fileURL(w.runId,w.run.package.path,true)):null,
        el('div',{class:'actions'},...Object.keys(w.run?.artifacts||{}).map(role=>link(msg("splat.download_2", {value1: role.replaceAll('_',' ')}),fileURL(w.runId,w.run.artifacts[role].relative,true)))),actions,w.nav({back:5}));
}
