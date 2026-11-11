import {sourceMessage} from "../i18n.js";
import {msg} from "../i18n.js";
import {el,button,hint,field} from '../dom.js';
import {uploadReference,capturePhoto,inputURL} from '../images/references.js';
import {referenceFilename} from '../graph-adapter.js';
import {mountMesh} from '../wizard/preview.js';
import {exportChoices,validateExports} from '../wizard/export-choices.js';
import {request} from '../services.js';
import {measurements} from '../wizard/pages.js';

const views=['front','right','back','left'];
const title=s=>s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
const set=(w,k,v)=>{w.draft.controls[k]=v;w.remember();};
function number(w,k,label,note,limits={}){
    return field(label,el('input',{type:'number',value:w.draft.controls[k]??w.cap.defaults[k],step:limits.step||1,...limits,
        'aria-label':label,oninput:e=>set(w,k,e.target.valueAsNumber)}),note);
}
function select(w,k,label,choices,note){
    return field(label,el('select',{'aria-label':label,onchange:e=>set(w,k,typeof choices[0][0]==='number'?Number(e.target.value):e.target.value)},
        ...choices.map(([value,text])=>el('option',{value,selected:value===(w.draft.controls[k]??w.cap.defaults[k])},text))),note);
}
function picture(w,key,label){const url=w.artifact(key);return url?el('figure',{},w.image(url,label),el('figcaption',{},label),el('a',{href:url,download:label+'.png'},msg("guided.save_image"))):null;}
function mesh(w,key,label,urlOverride=null){
    const url=urlOverride||w.previewArtifact(key);if(!url)return null;
    const host=el('div',{class:'wizard-mesh','aria-label':label});let disposed=false;
    const old=w.previewDispose;w.previewDispose=()=>{disposed=true;old?.();host._dispose?.();};
    setTimeout(async()=>{try{const dispose=await mountMesh(host,url,w.cap.viewer,key==='print'?'preview.stl':'preview.glb');if(disposed)dispose();else host._dispose=dispose;}catch(e){if(!disposed)host.replaceChildren(hint(sourceMessage(e.message)));}},0);
    return el('section',{},el('h3',{},label),host,el('a',{href:url,download:w.draft.name+'-'+key.replaceAll(':','-')+'.glb'},msg("guided.save_this_mesh")));
}

export function startingPage(w){
    async function take(file){if(w.id)throw Error(msg("guided.start_a_new_object_to_change_its_original_reference_this_saved_run_is_preser"));const ref=await uploadReference(file);w.draft.original=ref.filename;w.remember();w.render();}
    const file=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,'aria-label':msg("guided.upload_starting_object_image"),onchange:e=>w.act(()=>take(e.target.files[0]))});
    const current=referenceFilename();
    const original=hint(w.draft.original?msg("guided.selected_reference", {value1: w.draft.original.split('/').pop()}):msg("guided.choose_one_complete_object_as_your_starting_reference"));
    const extra=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,'aria-label':msg("guided.upload_appearance_reference"),onchange:e=>w.act(async()=>{
        const ref=await uploadReference(e.target.files[0]);const refs=w.draft.controls.extra_references??=[];
        if(refs.length>=6)throw Error(msg("guided.use_at_most_six_additional_references"));refs.push({filename:ref.filename,description:msg("guided.appearance_and_material_details")});
    })});
    const category=el('select',{'aria-label':msg("guided.object_type")},el('option',{value:'props'},msg("guided.objects")),
        el('option',{disabled:true},msg("guided.people_future_preset")),el('option',{disabled:true},msg("guided.vehicles_future_presets")));
    return el('div',{},hint(msg("guided.3d_guided_combines_pixal3d_geometry_moge_2_camera_estimation_blender_renderi")),
        el('div',{class:'wizard-columns'},field(msg("guided.asset_name"),el('input',{value:w.draft.name,'aria-label':msg("guided.asset_name"),maxLength:100,disabled:!!w.id,oninput:e=>{w.draft.name=e.target.value;w.remember();}})),
            field(msg("guided.what_are_you_making"),category,msg("guided.objects_only_in_this_version_best_suited_to_solid_standalone_props_readable"))),
        file,el('div',{class:'upload-zone',ondragover:e=>e.preventDefault(),ondrop:e=>{e.preventDefault();w.act(()=>take(e.dataTransfer.files[0]));}},el('strong',{},msg("guided.drop_one_starting_image_here")),
            el('div',{class:'actions'},button(msg("guided.upload_image"),()=>file.click(),{disabled:!!w.id}),button(msg("guided.take_a_photo"),()=>capturePhoto(w.shell,file=>w.act(()=>take(file))),{disabled:!!w.id||!navigator.mediaDevices}),
                current?button(msg("guided.use_existing_reference"),()=>{w.draft.original=current;w.remember();w.render();},{disabled:!!w.id}):null)),
        original,w.draft.original?w.image(inputURL(w.draft.original),msg("guided.starting_object_reference")):null,
        w.id?button(msg("guided.start_a_new_object"),()=>w.shell.openGuidedWizard(),{disabled:w.active()}):null,
        field(msg("guided.describe_the_object"),el('textarea',{rows:3,value:w.draft.controls.asset_description||'','aria-label':msg("guided.describe_the_object"),maxLength:800,oninput:e=>set(w,'asset_description',e.target.value)}),msg("guided.describe_its_main_shape_material_colors_and_attached_parts")),
        field(msg("guided.special_instructions"),el('textarea',{rows:3,value:w.draft.controls.special_instructions||'','aria-label':msg("guided.special_instructions"),maxLength:800,oninput:e=>set(w,'special_instructions',e.target.value)}),msg("guided.optional_preserve_an_emblem_explain_the_back_or_name_details_that_must_remai")),
        el('div',{class:'image-invitation'},el('strong',{},msg("guided.don_t_have_an_image")),button(msg("guided.create_an_image"),()=>{w.remember();w.shell.imageOrigin={method:'guided'};w.shell.openImages('Create Images');})),
        el('details',{},el('summary',{},msg("guided.additional_appearance_references")),hint(msg("guided.these_guide_materials_and_details_blender_provides_the_target_viewpoints")),extra,
            button(msg("guided.add_appearance_reference"),()=>extra.click()),...(w.draft.controls.extra_references||[]).map((r,i)=>el('section',{class:'reference-card'},w.image(inputURL(r.filename),msg("guided.appearance_reference", {value1: i+1})),
                field(msg("guided.reference_purpose"),el('textarea',{value:r.description,'aria-label':msg("guided.appearance_reference_purpose", {value1: i+1}),oninput:e=>{r.description=e.target.value;w.remember();}})),
                button(msg("guided.remove_reference"),()=>{w.draft.controls.extra_references.splice(i,1);w.remember();w.render();})))),
        el('details',{},el('summary',{},msg("guided.main_view_and_geometry_controls")),
            number(w,'elevation_deg',msg("guided.view_elevation_degrees"),'Default 10°. Zero gives straight-on views; a small elevation also shows upper surfaces.',{min:0,max:30}),
            select(w,'proxy_processing',msg("guided.working_proxy_handling"),[['upright_solid_box',msg("guided.upright_solid_prop_chest_default")],['as_generated',msg("guided.preserve_generated_pose_advanced")]],'The solid-prop preset estimates box orientation and repairs its actual working mesh. It can change thin or open shapes.'),
            select(w,'refine_resolution',msg("guided.refinement_detail"),[[512,'512'],[1024,'1024'],[1536,msg("guided.1536_default")]],'Higher detail takes more time and memory.'),
            select(w,'texture_size',msg("guided.texture_resolution"),[[1024,'1024'],[2048,'2048'],[4096,msg("guided.4096_default")]],'Final textures are applied after refinement and cleanup.')),
        el('details',{},el('summary',{},msg("guided.advanced_generation_controls")),
            number(w,'turnaround_seed',msg("guided.concept_seed"),'Fixed default preserves repeatability.'),number(w,'proxy_seed',msg("guided.rough_mesh_seed"),'Default 42.'),
            number(w,'enhancement_seed',msg("guided.enhancement_seed"),'Default 42. Change to regenerate appearance.'),
            number(w,'enhancement_steps',msg("guided.enhancement_steps"),'Default 40.',{min:20,max:100}),number(w,'control_strength',msg("guided.depth_guidance_strength"),'Default 1.0.',{min:0,max:2,step:.1}),
            number(w,'refine_steps',msg("guided.refinement_steps"),'Default 25 per internal resolution pass.',{min:1,max:100}),
            number(w,'reconstruction_seed',msg("guided.reconstruction_seed"),'Default 42. Keep fixed when comparing selected views.'),
            number(w,'refine_seed',msg("guided.refinement_seed"),'Default 42.'),number(w,'texture_seed',msg("guided.texture_seed"),'Default 42.'),
            number(w,'texture_steps',msg("guided.texture_steps"),'Default 20.',{min:1,max:100}),
            number(w,'texture_guidance',msg("guided.texture_guidance"),'Default 3.0.',{min:0,max:20,step:.1}),
            field(msg("guided.cpu_offloading"),el('input',{type:'checkbox',checked:w.draft.controls.cpu_offload??true,'aria-label':msg("guided.cpu_offloading"),onchange:e=>set(w,'cpu_offload',e.target.checked)}),msg("guided.default_on_uses_system_ram_to_reduce_gpu_memory_requirements"))),
        el('details',{},el('summary',{},msg("guided.models_licenses_and_retained_files")),hint(sourceMessage(w.cap.license_note)),...w.cap.resources.map(r=>el('p',{},el('strong',{},r.name+' · '),r.license||'See source',' ',el('a',{href:r.license_url||r.source,target:'_blank',rel:'noopener noreferrer'},msg("guided.read_terms")))),
            hint(msg("guided.originals_intermediate_meshes_camera_records_and_settings_are_retained_local"))),
        w.nav({next:()=>w.advance(),label:msg("guided.generate_concept_turnaround"),note:msg("guided.only_the_original_image_makes_the_rough_mesh_the_concept_turnaround_is_kept")}));
}

export function guidePage(w){
    const done=w.job?.completed||{};
    const label=!done.concept?'Generate concept turnaround':!done.proxy?'Build rough mesh':!done.render?'Render measured Blender views':'Assemble enhancement sheet';
    return el('div',{},hint(msg("guided.review_the_appearance_concept_then_the_actual_working_proxy_and_its_measured")),
        picture(w,'concept:sheet',msg("guided.concept_appearance_turnaround")),w.artifact('concept:sheet')?button(msg("guided.edit_an_area_of_the_concept_sheet"),()=>w.act(()=>w.editConcept()),{disabled:w.active()}):null,
        done.concept?button(msg("guided.regenerate_concept_views"),()=>w.act(async()=>{w.draft.controls.turnaround_seed=Math.floor(Math.random()*2**32);await w.advance();}),{disabled:w.active()}):null,
        mesh(w,'proxy:glb',msg("guided.actual_working_rough_mesh")),
        el('div',{class:'view-grid'},...views.map(v=>picture(w,'render:'+v,title(v)+' measured guide'))),
        w.artifact('cameras')?el('a',{href:w.artifact('cameras'),download:'measured-cameras.json'},msg("guided.save_measured_camera_information")):null,
        hint(msg("guided.concept_art_supplies_appearance_blender_supplies_the_numerical_cameras_and_s")),
        w.nav({next:()=>w.advance(),label,note:msg("guided.each_completed_generation_is_saved_before_the_next_stage")}));
}

export function enhancementPage(w){
    const done=w.job?.completed||{};const selected=w.draft.controls.selected_view_ids??=[...w.cap.defaults.selected_view_ids];
    const label=!done.sheet?'Assemble enhancement sheet':!done.enhance_sheet?'Enhance the sheet':!done.split?'Split and review four views':!done.prepare?'Prepare selected camera frames':'Build reconstructed mesh';
    return el('div',{},hint(msg("guided.all_four_panels_show_the_same_object_black_separators_keep_their_frames_dist")),
        picture(w,'guide:sheet',msg("guided.measured_blender_sheet")),picture(w,'enhanced:sheet',msg("guided.enhanced_four_view_sheet")),
        done.enhance_sheet?button(msg("guided.regenerate_enhanced_sheet"),()=>w.act(async()=>{w.draft.controls.enhancement_seed=Math.floor(Math.random()*2**32);await w.advance();}),{disabled:w.active()}):null,
        el('div',{class:'view-grid'},...views.map(v=>el('section',{class:'guided-view-choice'},picture(w,'enhanced:'+v,title(v)+' enhanced view'),
            field(msg("guided.use_view", {value1: title(v)}),el('input',{type:'checkbox','aria-label':msg("guided.use_view_2", {v: v}),checked:selected.includes(v),disabled:w.active(),onchange:e=>{
                const next=e.target.checked?[...selected,v]:selected.filter(x=>x!==v);w.draft.controls.selected_view_ids=next;
                if(!next.includes(w.draft.controls.reference_view_id||'front'))w.draft.controls.reference_view_id=next[0]||'front';w.remember();w.render();
            }}))))),
        !selected.length?el('p',{role:'alert',class:'error-panel'},msg("guided.choose_at_least_one_view")):hint(msg("guided.of_four_views_selected_only_these_images_and_their_matching_cameras_go_to_re", {value1: selected.length})),
        select(w,'reference_view_id',msg("guided.refinement_and_texture_reference"),views.filter(v=>selected.includes(v)).map(v=>[v,title(v)]),'Choose the clearest selected view for final refinement and texture.'),
        w.artifact('enhanced:cameras')?el('a',{href:w.artifact('enhanced:cameras'),download:'enhanced-view-cameras.json'},msg("guided.save_enhanced_view_camera_information")):null,
        w.nav({next:async()=>{if(!selected.length)throw Error(msg("guided.choose_at_least_one_view"));await w.advance();},label}));
}

export function meshPage(w){
    const done=w.job?.completed||{};
    const options=[['textured',msg("guided.textured_master")],['refined:glb',msg("guided.after_cleanup")],['refine:raw:glb',msg("guided.after_hi3d_before_cleanup")],['reconstruction:glb',msg("guided.before_hi3d")]].filter(([key])=>w.artifact(key));
    const preview=options.some(([key])=>key===w.geometryPreview)?w.geometryPreview:options[0]?.[0];
    const picker=el('select',{'aria-label':msg("guided.compare_geometry_checkpoints"),onchange:e=>{w.geometryPreview=e.target.value;w.render();}},...options.map(([value,label])=>el('option',{value,selected:value===preview},label)));
    const label=!done.reconstruct?'Build reconstructed mesh':!done.refine?'Refine and clean geometry':!done.texture?'Apply final textures':'Choose output versions';
    return el('div',{},hint(msg("guided.reconstruction_uses_selected_images_and_measured_cameras_hi3d_refines_the_re")),
        options.length?picker:null,mesh(w,preview,options.find(([key])=>key===preview)?.[1]||'Reconstructed mesh'),
        w.nav({next:()=>done.texture?w.go(5):w.advance(),label,note:msg("guided.all_previous_mesh_checkpoints_remain_saved")}));
}

export function exportPage(w){
    function finishingNumber(key,label,note){return field(label,el('input',{type:'number',value:w.draft.finishing[key]??w.cap.finishing_defaults[key],'aria-label':label,min:1000,max:1000000,
        oninput:e=>{w.draft.finishing[key]=e.target.valueAsNumber;w.remember();}}),note);}
    return el('div',{},hint(msg("guided.choose_the_versions_and_file_formats_to_save_detailed_and_reduced_triangle_m")),
        exportChoices(w.cap.exports,w.draft.selection,()=>w.remember()),
        el('details',{},el('summary',{},msg("guided.output_geometry_settings")),finishingNumber('balanced_triangles',msg("guided.balanced_triangle_target"),'Default 250,000.'),
            finishingNumber('compact_triangles',msg("guided.compact_triangle_target"),'Default 100,000.'),w.cap.quad_retopology_enabled?finishingNumber('quad_count',msg("guided.editable_quad_target"),'Default 25,000. QuadriFlow builds editable topology; runtime derivatives are triangulated.'):null,
            field(msg("guided.print_height_millimeters"),el('input',{type:'number',value:w.draft.finishing.print_height_mm??100,'aria-label':msg("guided.print_height_millimeters"),min:1,max:10000,oninput:e=>{w.draft.finishing.print_height_mm=e.target.valueAsNumber;w.remember();}}),msg("guided.physical_printing_requires_separate_validation"))),
        w.nav({next:async()=>{validateExports(w.draft.selection);await w.finish();},label:msg("guided.prepare_selected_outputs_and_package")}));
}

export function resultPage(w){
    const f=w.job?.finishing;const packageURL='guided/runs/'+w.id+'/package';
    const options=[['texture',msg("guided.detailed_master"),'detailed'],['balanced',msg("guided.balanced_game_mesh"),'game_balanced'],['compact',msg("guided.compact_game_mesh"),'game_compact'],['quads',msg("guided.editable_quad_runtime_preview"),'quad_light'],['print',msg("guided.print_mesh_stl"),'print'],['clean',msg("guided.clean_geometry"),null]]
        .filter(([key,label,variant])=>f?.previews?.[key]&&(!variant||f.selection.variants[variant])&&(key!=='quads'||w.cap.quad_retopology_enabled));
    const selected=options.some(([key])=>key===w.finalPreview)?w.finalPreview:options[0]?.[0];
    const picker=el('select',{'aria-label':msg("guided.finished_mesh_version"),onchange:e=>{w.finalPreview=e.target.value;w.render();}},...options.map(([value,label])=>el('option',{value,selected:value===selected},label)));
    const actions=()=>el('nav',{class:'actions result-actions','aria-label':msg("guided.finished_asset_actions")},button(msg("guided.make_a_new_asset"),()=>w.shell.openGuidedWizard(),{class:'primary'}),button(msg("guided.back_to_export_choices"),()=>w.go(5)),button(msg("guided.choose_another_workflow"),()=>w.shell.open('Choose a Workflow')));
    return el('div',{},f?.package?actions():null,options.length?picker:null,
        mesh(w,selected||'textured',options.find(([key])=>key===selected)?.[1]||'Final textured master',f?.previews?.[selected]),
        f?.package?el('section',{},el('h3',{},msg("guided.your_selected_asset_package_is_ready")),
            el('a',{class:'download-link',href:'/mumblebox-foundry/v1/'+packageURL,download:w.draft.name+'.zip'},msg("guided.download_asset_zip")),
            button(msg("guided.open_output_folder"),()=>w.act(()=>request('guided/runs/'+w.id+'/open-package-folder',{}))),
            hint(msg("guided.includes_the_selected_meshes_matching_material_maps_measurements_production"))):
            el('div',{},hint(f?.active?msg("guided.preparing_the_selected_exports_and_package_this_can_take_several_minutes"):msg("guided.select_your_output_versions_on_the_previous_page")),
                f&&!f.active&&!f.package?button(msg("guided.retry_remaining_stages"),()=>w.act(()=>w.finish()),{class:'primary'}):null),
        el('details',{},el('summary',{},msg("guided.save_originals_cameras_and_production_files")),
            hint(msg("guided.private_download_contains_original_images_prompts_intermediate_meshes_numeri")),
            el('a',{class:'download-link',href:'/mumblebox-foundry/v1/guided/runs/'+w.id+'/production',download:'private-production.zip'},msg("guided.download_private_production_archive")),
            button(msg("guided.open_retained_production_folder"),()=>w.act(()=>request('guided/runs/'+w.id+'/open-folder',{}))),
            el('a',{href:w.artifact('enhanced:cameras'),download:'camera-information.json'},msg("guided.save_camera_information"))),
        f?.measurements?measurements({run:f,showQuads:w.cap.quad_retopology_enabled}):null,
        ...(f?.package?.warnings||[]).map(text=>el('p',{class:'note-panel'},text)),
        f?.package?hint(f.cleanup?.status==='released'?msg("guided.models_were_released_saved_masters_previews_and_exports_are_retained"):msg("guided.package_saved_memory_release_status", {value1: f.cleanup?.status||'finishing'})):null,
        f?.package?actions():w.nav({back:5,note:msg("guided.your_session_and_all_completed_checkpoints_are_retained")}));
}
