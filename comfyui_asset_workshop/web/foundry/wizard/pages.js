import {sourceMessage} from "../i18n.js";
import {msg} from "../i18n.js";
import {capturePhoto} from "../images/references.js";
import {el,button,hint,field} from "../dom.js";
import {dialog} from "../dialogs.js";
import {request} from "../services.js";
import {referenceFilename,clearWizardState} from "../graph-adapter.js";
import {mountMesh} from "./preview.js";
import {exportChoices,validateExports} from "./export-choices.js";

const imageUrl=name=>{const parts=name.split("/");return "/view?"+new URLSearchParams({filename:parts.pop(),subfolder:parts.join("/"),type:"input"});};
const title=id=>id.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
function set(w,key,value){w.draft.overrides[key]=value;w.remember();}
function selectedModel(w){return w.cap.turnaround_models.find(m=>m.id===w.draft.turnaround_model)||w.cap.turnaround_models[0];}
function select(w,key,label,choices,description){
    const control=el("select",{"aria-label":label,onchange:e=>set(w,key,typeof choices[0][0]==="number"?Number(e.target.value):e.target.value)},
        ...choices.map(([value,text])=>el("option",{value,selected:value===(w.draft.overrides[key]??w.cap.defaults[key])},text)));
    return field(label,control,description);
}
function number(w,key,label,description){
    const input=el("input",{type:"number",value:w.draft.overrides[key]??w.cap.defaults[key],step:key==="texture_guidance"||key==="print_height_mm"?"any":1,
        "aria-label":label,onchange:e=>set(w,key,Number(e.target.value))});
    return field(label,input,description);
}
async function upload(w,file){
    if(!file||!["image/png","image/jpeg","image/webp"].includes(file.type))throw Error(msg("mesh.use_a_png_jpeg_or_webp_image"));
    if(file.size>20*1024**2)throw Error(msg("mesh.use_an_image_smaller_than_20_mb"));
    const model=selectedModel(w);
    if(w.draft.references.length>=model.max_references)throw Error(msg("mesh.supports_up_to_reference_images_here_choose_another_model_or_remove_a_refere", {name: model.name, value2: model.max_references}));
    const form=new FormData();form.append("image",file);form.append("subfolder","foundry-references");form.append("overwrite","false");
    const response=await fetch("/upload/image",{method:"POST",body:form});
    const data=await response.json();
    if(!response.ok)throw Error(data.error||"The image could not be uploaded.");
    w.draft.references.push({id:crypto.randomUUID(),filename:(data.subfolder?data.subfolder+"/":"")+data.name,
        role:w.draft.references.length?"detail":"primary",description:""});
    w.remember();
}
function camera(w){capturePhoto(w.shell,file=>w.act(()=>upload(w,file)));}
export function inputPage(w){
    const name=el("input",{value:w.draft.name,maxLength:100,placeholder:msg("mesh.name_this_asset"),"aria-label":msg("mesh.asset_name"),
        oninput:e=>{w.draft.name=e.target.value;w.remember();}});
    const category=el("select",{"aria-label":msg("mesh.asset_type"),onchange:e=>{w.draft.category=e.target.value;w.remember();w.render();}},
        ...w.cap.categories.map(c=>el("option",{value:c.id,selected:c.id===w.draft.category,disabled:!c.qualified},
            c.name)));
    const model=selectedModel(w);
    const modelChoice=el("select",{"aria-label":msg("mesh.turnaround_image_model"),onchange:e=>{
        w.draft.turnaround_model=e.target.value;w.remember();w.render();
        w.host.querySelector('[data-i18n-control="mesh.turnaround_image_model"]')?.focus();
    }},...w.cap.turnaround_models.map(m=>el("option",{value:m.id,selected:m.id===model.id},m.name+(m.id==="qwen21"?" · Current default":""))));
    const modelPanel=el("section",{class:"model-choice"},
        field(msg("mesh.image_model_for_the_four_views"),modelChoice,msg("mesh.to_build_your_initial_3d_model_we_first_generate_additional_views_choose_the")),
        el("div",{class:"model-facts"},el("span",{class:"badge"},msg("mesh.1_references", {value1: model.max_references})),
            el("span",{class:"badge"},msg("mesh.steps_cfg", {steps: model.steps, cfg: model.cfg})),
            el("span",{class:"badge"},model.installed?msg("mesh.installed"):msg("mesh.downloads_on_first_use"))),
        el("p",{class:"model-license"},el("strong",{},model.license+". "),sourceMessage(model.license_summary)," ",
            el("a",{href:model.license_url,target:"_blank",rel:"noopener noreferrer"},msg("mesh.read_model_license"))),
        w.draft.references.length>model.max_references?el("p",{role:"alert",class:"error-panel"},
            msg("mesh.you_have_references_this_model_accepts_your_images_are_preserved_remove_extr", {value1: w.draft.references.length, value2: model.max_references})):null);
    const input=el("input",{type:"file",accept:"image/png,image/jpeg,image/webp",multiple:true,hidden:true,"aria-label":msg("mesh.upload_reference_images"),
        onchange:e=>w.act(async()=>{for(const file of e.target.files)await upload(w,file);})});
    const cards=w.draft.references.map((ref,index)=>{
        const role=el("select",{"aria-label":msg("mesh.reference_purpose", {value1: index+1}),disabled:index===0,
            onchange:e=>{ref.role=e.target.value;w.remember();}},
            ...[["primary",msg("mesh.overall_asset")],["back",msg("mesh.back_of_the_asset")],["face",msg("mesh.face_identity")],["component",msg("mesh.component_or_accessory")],
                ["style",msg("mesh.style_material")],["detail",msg("mesh.other_detail")]].map(([value,label])=>el("option",{value,selected:ref.role===value},label)));
        const note=el("textarea",{value:ref.description,maxLength:800,rows:2,"aria-label":msg("mesh.reference_description", {value1: index+1}),
            placeholder:index===0?msg("mesh.optional_description_of_the_whole_asset"):msg("mesh.describe_what_this_image_contributes"),
            oninput:e=>{ref.description=e.target.value;w.remember();}});
        return el("article",{class:"reference-card"},w.image(imageUrl(ref.filename),msg("mesh.reference", {value1: index+1})),
            el("div",{},el("strong",{},msg("mesh.image", {value1: index+1})),field(msg("mesh.purpose"),role),field(msg("mesh.reference_description_2"),note)),
            el("div",{class:"actions"},button(msg("mesh.remove"),()=>{
                w.draft.references.splice(index,1);if(w.draft.references[0])w.draft.references[0].role="primary";w.remember();w.render();
            }),index>1?button(msg("mesh.move_earlier"),()=>{
                [w.draft.references[index-1],w.draft.references[index]]=[ref,w.draft.references[index-1]];w.remember();w.render();
            }):null));
    });
    const current=referenceFilename();
    return el("div",{},hint(msg("mesh.supply_one_clear_image_of_the_complete_asset_your_chosen_image_model_makes_f")),
        el("div",{class:"wizard-columns"},field(msg("mesh.asset_name"),name,msg("mesh.used_in_the_saved_output_folders_and_package_name")),
            field(msg("mesh.what_kind_of_asset_are_you_making"),category,w.cap.categories.find(x=>x.id===w.draft.category)?.description)),
        el("section",{class:"image-intake"},input,
        el("div",{class:"upload-zone",ondragover:e=>{e.preventDefault();},ondrop:e=>{e.preventDefault();w.act(async()=>{for(const file of e.dataTransfer.files)await upload(w,file);});}},
            el("strong",{},msg("mesh.drop_reference_images_here")),hint(msg("mesh.one_overall_image_is_required_optional_references_can_describe_the_back_face")),
            el("div",{class:"actions"},button(msg("mesh.upload_images"),()=>input.click()),button(msg("mesh.take_a_photo_with_connected_camera"),()=>camera(w),{disabled:!navigator.mediaDevices}),
                current&&!w.draft.references.length?button(msg("mesh.use_current_graph_image"),()=>{
                    w.draft.references=[{id:crypto.randomUUID(),filename:current,role:"primary",description:""}];w.remember();w.render();
                }):null)),el("div",{class:"reference-list"},...cards)),
        hint(msg("mesh.keep_the_whole_subject_in_frame_with_a_clear_silhouette_a_plain_background_i")),
        el("div",{class:"image-invitation"},el("strong",{},msg("mesh.don_t_have_an_image")),
            button(msg("mesh.create_an_image_or_scan_an_image_with_your_webcam"),()=>{w.remember();w.shell.imageOrigin={sessionId:w.sessionId};w.shell.openImages("Create Images");}),
            el("small",{class:"muted"},msg("mesh.generate_a_front_back_reference_pair_then_return_here_with_your_images"))),
        modelPanel,
        el("details",{},el("summary",{},msg("mesh.advanced_turnaround_settings")),number(w,"turnaround_seed",msg("mesh.turnaround_seed"),msg("mesh.keep_this_fixed_to_compare_settings_regenerate_views_chooses_a_new_seed")),
            hint(msg("mesh.the_selected_model_uses_its_own_sampling_defaults_the_output_remains_a_4096")),
            el("a",{href:model.source,target:"_blank",rel:"noopener noreferrer"},msg("mesh.model_workflow_guidance"))),
        el("details",{},el("summary",{},msg("mesh.model_use_and_license_information")),hint(sourceMessage(w.cap.license_note))),
        w.nav({next:()=>w.start("turnaround"),note:msg("mesh.clicking_next_generates_the_four_views_using", {name: model.name})}));
}
export function reviewPage(w){
    const p=w.run?.previews||{};
    const ready=["front","left","back","right"].every(x=>p[x]);
    return el("div",{},hint(msg("mesh.check_that_all_four_views_show_the_same_asset_with_the_same_clothing_proport")),
        ready?el("div",{class:"view-grid"},...["front","left","back","right"].map(v=>el("figure",{},w.image(p[v],msg("mesh.view", {value1: title(v)})),el("figcaption",{},title(v))))):hint(msg("mesh.the_four_prepared_images_will_appear_here_when_generation_finishes")),
        p.sheet?el("details",{},el("summary",{},msg("mesh.turnaround_sheet_and_source")),w.image(p.sheet,msg("mesh.complete_turnaround_sheet")),
            w.draft.references[0]?w.image(imageUrl(w.draft.references[0].filename),msg("mesh.original_reference")):null):null,
        el("div",{class:"actions"},button(msg("mesh.regenerate_views"),()=>w.act(async()=>{
            w.draft.overrides.turnaround_seed=Math.floor(Math.random()*2**32);await w.start("turnaround");
        }),{disabled:!!w.run?.active}),!ready&&!w.run?.active&&w.runId?button(msg("mesh.retry"),()=>w.act(()=>w.start("turnaround"))):null),
        w.nav({next:async()=>{if(!ready)throw Error(msg("mesh.wait_for_all_four_views_before_continuing"));w.go(3);},
            note:msg("mesh.next_keeps_these_views_and_opens_the_mesh_settings_regenerate_changes_only_t")}));
}
export function optionsPage(w){
    const advanced=el("details",{},el("summary",{},msg("mesh.advanced_refinement_settings")),
        el("div",{class:"wizard-columns"},number(w,"refine_steps",msg("mesh.refinement_steps"),msg("mesh.default_25_more_steps_do_not_guarantee_a_better_result")),
            number(w,"refine_seed",msg("mesh.refinement_seed"),msg("mesh.default_42_keep_it_fixed_for_a_controlled_comparison"))),
        field(msg("mesh.cpu_offloading"),el("input",{type:"checkbox",checked:w.draft.overrides.cpu_offload??w.cap.defaults.cpu_offload,
            "aria-label":msg("mesh.cpu_offloading"),onchange:e=>set(w,"cpu_offload",e.target.checked)}),
            msg("mesh.default_on_moves_model_data_to_system_ram_when_possible_turning_it_off_can_r")));
    return el("div",{},hint(msg("mesh.pixal3d_trellis_2_will_construct_the_initial_mesh_from_your_four_views_hi3d")),
        el("div",{class:"wizard-columns"},
            select(w,"shape_resolution",msg("mesh.initial_mesh_detail"),[[1024,msg("mesh.1024_default")],[1536,msg("mesh.1536_experimental")],[2048,msg("mesh.2048_experimental")]],msg("mesh.higher_detail_requires_more_memory_and_time")),
            select(w,"refine_resolution",msg("mesh.refinement_detail"),[[512,msg("mesh.512_faster")],[1024,msg("mesh.1024_intermediate")],[1536,msg("mesh.1536_default")]],msg("mesh.choose_more_detail_when_the_subject_needs_it_higher_settings_use_more_memory"))),
        advanced,el("div",{class:"note-panel"},hint(msg("mesh.recommended_defaults_are_loaded_your_changes_take_priority"))),
        w.nav({next:()=>w.start("mesh"),note:msg("mesh.clicking_next_generates_the_initial_mesh_refines_it_once_with_hi3d_and_clean")}));
}
function mesh(w,key){
    const url=w.run?.previews?.[key];
    if(!url)return hint(msg("mesh.the_mesh_preview_will_appear_after_this_stage_finishes"));
    const container=el("div",{class:"wizard-mesh",tabindex:0,role:"application","aria-label":msg("mesh.mesh_preview", {value1: title(key)})});
    requestAnimationFrame(async()=>{
        if(!container.isConnected)return;
        try{
            const dispose=await mountMesh(container,url,w.cap.viewer_module);
            if(!container.isConnected)dispose();else w.previewDispose=dispose;
        }catch(error){container.replaceChildren(hint(sourceMessage(error.message)));}
    });
    return el("div",{},el('div',{class:'preview-tools'},hint(msg("mesh.drag_to_rotate_scroll_to_zoom")),
        button(msg("mesh.fit_view"),()=>{w.previewDispose?.viewer?.fitToViewer();w.previewDispose?.viewer?.forceRender();},{title:msg("mesh.fit_the_complete_mesh_in_the_viewer")})),container);
}
function exports(w){
    const quad=w.quadChoice();
    const change=quad.change;
    quad.change=value=>{change(value);w.remember();};
    return el("div",{},exportChoices(w.cap.exports,w.draft.selection,()=>w.remember(),quad),
        el("details",{},el("summary",{},msg("mesh.advanced_output_settings")),el("div",{class:"wizard-columns"},
            number(w,"balanced_triangles",msg("mesh.balanced_triangle_budget"),msg("mesh.a_starting_budget_not_a_guarantee_of_suitability_for_every_game")),
            number(w,"compact_triangles",msg("mesh.compact_triangle_budget"),msg("mesh.the_normal_map_carries_some_of_the_master_s_surface_detail")),
            number(w,"quad_count",msg("mesh.target_quad_count"),msg("mesh.optional_editable_retopology_automatic_quads_still_need_review_before_animat")),
            number(w,"print_height_mm",msg("mesh.print_height_in_millimetres"),msg("mesh.the_stl_records_this_scale_wall_thickness_supports_and_fabrication_need_sepa")))));
}
export function finishingPage(w){
    const ready=!!w.run?.previews?.clean;
    const picker=el("select",{"aria-label":msg("mesh.compare_geometry"),onchange:e=>{w.geometryPreview=e.target.value;w.render();}},
        ...[["clean",msg("mesh.cleaned_refined_mesh")],["refined",msg("mesh.after_hi3d")],["decoded",msg("mesh.before_hi3d")]].filter(([k])=>w.run?.previews?.[k])
            .map(([value,text])=>el("option",{value,selected:value===(w.geometryPreview||"clean")},text)));
    const mode=w.draft.overrides.texture_mode??w.cap.defaults.texture_mode??"standard";
    const textureMode=field(msg("mesh.texturing_mode"),el("select",{"aria-label":msg("mesh.texturing_mode"),onchange:e=>{set(w,"texture_mode",e.target.value);w.render();}},
        el("option",{value:"standard",selected:mode==="standard"},msg("mesh.standard_default")),
        el("option",{value:"smd",selected:mode==="smd"},msg("mesh.fast_experimental_smd_trellis_2"))),
        msg("mesh.fast_uses_a_four_step_texture_model_compare_material_detail_on_your_asset_pr"));
    const fields=el("fieldset",{disabled:!!w.run?.active},textureMode,w.single?select(w,'export_grounding',msg("mesh.floor_placement"),[['level',msg("mesh.level_and_place_on_floor_recommended")],['place',msg("mesh.place_on_floor_only")],['original',msg("mesh.keep_original_orientation")]],msg("mesh.levels_a_near_upright_resting_pose_without_bending_the_mesh_applied_after_ba")):null,select(w,"texture_size",msg("mesh.texture_size"),[[1024,"1024"],[2048,"2048"],[4096,msg("mesh.4096_default")]],
        msg("mesh.trellis_2_applies_color_and_material_maps_to_the_final_cleaned_geometry_prin")),
        el("details",{},el("summary",{},msg("mesh.advanced_texture_settings")),el("div",{class:"wizard-columns"},
            mode==="standard"?number(w,"texture_steps",msg("mesh.texture_steps"),msg("mesh.default_20")):null,
            number(w,"texture_seed",msg("mesh.texture_seed"),msg("mesh.default_42")),
            mode==="standard"?number(w,"texture_guidance",msg("mesh.texture_guidance"),msg("mesh.default_3_0")):null)),exports(w));
    const preview=el("section",{class:"review-preview"},el("h3",{},msg("mesh.inspect_your_mesh")),
        ready?el("div",{},picker,mesh(w,w.geometryPreview||"clean")):mesh(w,"decoded"),
        !w.run?.active&&["failed","cancelled","interrupted"].includes(w.run?.status)?button(msg("mesh.retry_mesh_and_refinement"),()=>w.act(()=>w.start("mesh"))):null,
        ready&&w.run.geometry_audit?el("div",{class:"note-panel"},
            el("strong",{},msg("mesh.cleaned_mesh_measurements")),
            hint(["render_vertices","faces","boundary_edges","nonmanifold_edges","watertight"].filter(k=>w.run.geometry_audit[k]!==undefined).map(k=>title(k)+": "+String(w.run.geometry_audit[k])).join(" · ")),
            hint(msg("mesh.these_checks_do_not_establish_self_intersection_wall_thickness_or_fabricatio"))):null);
    return el("div",{},el("div",{class:"review-workspace"},preview,
        ready&&!w.run?.active?el("section",{class:"review-options"},fields):hint(msg("mesh.the_initial_mesh_is_saved_before_hi3d_begins_the_refined_cleaned_version_wil"))),
        w.nav({next:async()=>{if(!ready)throw Error(msg("mesh.finish_refinement_first"));validateExports(w.draft.selection,w.quadChoice());await w.start("finish");},
            note:msg("mesh.clicking_next_creates_the_selected_textures_mesh_versions_exports_and_zip_pa")}));
}
export function resultPage(w){
    const complete=!w.run?.active&&w.run?.status==="complete"&&w.run?.package;
    if(!complete)return el("div",{},hint(w.run?.status==="failed"?msg("mesh.completed_stages_are_saved_choose_how_to_continue_above"):msg("mesh.preparing_your_selected_mesh_versions_and_exports")),
        w.run?.previews?.texture||w.run?.previews?.clean?mesh(w,w.run.previews.texture?"texture":"clean"):null,
        !w.run?.active&&!w.error?button(msg("mesh.retry_remaining_stages"),()=>w.act(()=>w.start(w.run?.operation==="rocket"?"rocket":"finish")),{class:"primary"}):null,
        el("details",{},el("summary",{},msg("mesh.stage_log")),el("ol",{},...(w.run?.events||[]).map(e=>el("li",{},e.text)))),
        w.nav({back:w.single?3:4}));
    const p=w.run.package;
    const selectedVariants=w.run.selection.variants;
    const methods=w.run.quad_report?.effective_methods||[];
    const solverLabel=id=>w.cap.quad_methods?.find(method=>method.id===id)?.label||
        (id==="topology_preserving"?"Foundry topology-preserving subdivision":id);
    const options=[["texture",msg("mesh.detailed_master"),"detailed"],["balanced",msg("mesh.balanced_game_mesh"),"game_balanced"],
        ["compact",msg("mesh.compact_game_mesh"),"game_compact"],["quads",msg("mesh.editable_quad_runtime_preview"),"quad_light"],
        ["print",msg("mesh.print_mesh_stl"),"print"],["clean",msg("mesh.original_clean_geometry_before_floor_placement"),null]]
        .filter(([key,label,variant])=>w.run.previews[key]&&(!variant||selectedVariants[variant]));
    const selected=options.some(([k])=>k===w.finalPreview)?w.finalPreview:options[0]?.[0];
    const picker=el("select",{"aria-label":msg("mesh.finished_mesh_version"),onchange:e=>{w.finalPreview=e.target.value;w.render();}},
        ...options.map(([value,text])=>el("option",{value,selected:value===selected},text)));
    return el("div",{},resultActions(w,"top"),el("div",{class:"complete-panel"},el("h3",{},msg("mesh.is_ready", {name: w.run.name})),
        hint(msg("mesh.files_mb", {value1: p.selected_variants.map(title).join(" · "), value2: p.file_count, value3: (p.bytes/1024**2).toFixed(1)}))),
        selectedVariants.quad_light&&methods.length?hint(msg("mesh.quad_methods_used", {value1: methods.map(solverLabel).join(" + ")})):null,
        picker,w.run.package.grounding?hint(msg("mesh.floor_placement_saved_generation_checkpoints_are_unchanged", {value1: w.run.package.grounding.applied==='level'?'leveled '+w.run.package.grounding.correction_degrees.toFixed(1)+'°':w.run.package.grounding.applied==='place'?'placed on floor':'original orientation'})):null,mesh(w,selected),measurements(w),el("div",{class:"actions"},
            el("a",{href:p.download,download:"",class:"download-link primary"},msg("mesh.download_zip")),
            button(msg("mesh.open_output_folder"),()=>w.act(()=>request("wizard/runs/"+w.runId+"/open-folder",{})))),
        ...(p.warnings||[]).map(text=>el("p",{class:"note-panel"},text)),
        hint(w.run.cleanup?.status==="released"?msg("mesh.loaded_models_and_reusable_execution_memory_were_released_saved_previews_mas"):msg("mesh.package_saved_memory_release_status", {value1: w.run.cleanup?.status||"finishing"})),
        resultActions(w,"bottom"));
}

function resultActions(w,position){
    return el("nav",{class:"actions result-actions","aria-label":msg("mesh.finished_asset_actions", {position: position})},
        button(msg("mesh.make_a_new_asset"),()=>w.shell.openWizard({method:w.method}),{class:"primary"}),
        button(msg("mesh.back_to_export_choices"),()=>w.go(w.single?3:4)),
        button(msg("mesh.choose_another_workflow"),()=>w.shell.open("Choose a Workflow")));
}

export function measurements(w){
    const cards=Object.entries(w.run.measurements||{}).map(([id,v])=>{
        const m=v.measurements;const stats=[];
        for(const [group,data] of Object.entries(m)){
            if(!data||typeof data!=="object"||Array.isArray(data))continue;
            for(const key of ["vertices","triangles","quads","polygons","dimensions","units","boundary_edges","nonmanifold_edges","watertight"]){
                if(data[key]===undefined||key==='quads'&&w.showQuads===false)continue;
                const value=Array.isArray(data[key])?data[key].map(x=>Number(x).toPrecision(4)).join(" × "):typeof data[key]==="number"?data[key].toLocaleString():String(data[key]);
                stats.push(el("div",{},el("dt",{},title(group)+" · "+title(key)),el("dd",{},value)));
            }
        }
        return el("section",{class:"export-option"},el("h3",{},v.directory),el("dl",{class:"asset-stats"},...stats));
    });
    return el("div",{class:"export-grid"},...cards);
}
