import {msg, appendContent} from "../i18n.js";
import {syncSingleGraph,showSingleWorkflow} from '../single/graph.js';
import {el,button,hint} from "../dom.js";
import {showWorkflow,showHairWorkflow,savedWizardState,savedSingleWizardState} from "../graph-adapter.js";
import {showGuidedWorkflow} from '../guided/graph.js';
import {showSplatWorkflow} from '../splat/graph.js';
import {syncSplatGraph} from '../splat/graph.js';
import {request} from '../services.js';

const planned=[
["repair",msg("common.refine_and_repair_an_existing_mesh"),msg("common.supply_an_existing_mesh_and_a_matching_image_for_refinement_and_new_output_v")],
["video",msg("common.start_with_a_video"),msg("common.use_a_recorded_subject_as_the_starting_point_for_a_3d_asset")],
["turntable",msg("common.pc_controlled_turntable_and_camera_capture"),msg("common.capture_a_subject_with_a_compatible_comxim_bluetooth_turntable_and_connected")],
["figure",msg("common.action_figure_mode"),msg("common.use_identity_references_and_figure_presets_to_create_a_personalized_figure_w")]
];
const artwork=(id,alt)=>{
    const url=new URL("../../assets/foundry/"+id+(id.startsWith("method-")?".webp":".png"),import.meta.url);
    // New artwork must not reuse a cached failed response from an older install.
    url.searchParams.set('v','single-image-1');
    return el("img",{src:url.href,alt,loading:"lazy",decoding:"async",width:512,height:512});
};

export function home(shell) {
    const saved = savedWizardState(shell.node);
    const methods=el('div',{class:'mesh-methods'},
        el('article',{class:'mesh-method recommended','data-method':'single'},el('div',{},el('span',{class:'badge'},msg("common.recommended_single_image_or_text")),
            el('h3',{},msg("common.single_image_or_text")),hint(msg("common.start_with_one_image_or_create_one_from_text_pixal3d_builds_the_mesh_hi3d_re")),
            hint(msg("common.best_for_a_direct_start_fewer_stages_and_models_try_a_three_quarter_view")),
            el('div',{class:'actions'},button(msg("common.open_single_image_wizard"),()=>shell.openMeshMethod('single'),{class:'primary'}),
                button(msg("common.view_workflow"),async()=>{syncSingleGraph(await request('wizard/single-template'),shell.node);showSingleWorkflow();}),
                (savedSingleWizardState(shell.node)?.runId||savedSingleWizardState(shell.node)?.draft?.references?.length)?button(msg("common.resume_single_image"),()=>shell.openWizard({method:'single-image',resume:true})):null))),
        el('article',{class:'mesh-method','data-method':'turnaround'},el('div',{},el('span',{class:'badge'},msg("common.turnaround")),
            el('h3',{},msg("common.turnaround")),hint(msg("common.generate_consistent_views_with_qwen_or_flux_build_with_pixal3d_then_refine_w")),
            hint(msg("common.best_for_humanoids_review_four_views_before_building_vehicle_prop_and_creatu")),
            el('div',{class:'actions'},button(msg("common.open_turnaround_wizard"),()=>shell.openMeshMethod('turnaround'),{class:'primary'}),
                button(msg("common.view_turnaround_workflow"),()=>showWorkflow(shell.node)),saved?button(msg("common.resume_turnaround"),()=>shell.openWizard({resume:true})):null))),
        el('article',{class:'mesh-method','data-method':'3d-guided'},el('div',{},el('span',{class:'badge'},msg("common.3d_guided_objects")),
            el('h3',{},msg("common.3d_guided")),hint(msg("common.use_a_pixal3d_proxy_and_measured_camera_views_with_moge_2_and_qwen_depth_gui")),
            hint(msg("common.best_for_controlled_object_views_choose_the_angles_before_reconstruction_mor")),
            el('div',{class:'actions'},button(msg("common.open_3d_guided_wizard"),()=>shell.openMeshMethod('guided'),{class:'primary'}),
                button(msg("common.view_3d_guided_workflow"),()=>showGuidedWorkflow()),shell.node.properties.foundryGuided?.id?button(msg("common.resume_3d_guided"),()=>shell.openGuidedWizard({resume:true})):null))));
    appendContent(methods, el('article',{class:'mesh-method','data-method':'splat'},el('div',{},el('span',{class:'badge'},msg("common.idol_splat_solid")),
        el('h3',{},msg("common.splat_solid")),hint(msg("common.create_an_idol_gaussian_splat_by_sperid_labs_with_separate_cleaned_companion")),
        hint(msg("common.best_for_detailed_appearance_plus_lightweight_geometry_orbit_previews_mesh_c")),
        el('div',{class:'actions'},button(msg("common.open_splat_solid_wizard"),()=>shell.openMeshMethod('splat'),{class:'primary'}),
            button(msg("common.view_splat_solid_workflow"),async()=>{syncSplatGraph(await request('splat/template'),shell.node);showSplatWorkflow();}),
            shell.node.properties.foundrySplat?.runId?button(msg("common.resume_splat_solid"),()=>shell.openSplatWizard({resume:true})):null))));
    for(const [method,id,alt] of [['single','single',msg("common.one_reference_becoming_a_refined_robot_mesh")],['turnaround','turnaround',msg("common.consistent_character_views_beside_a_finished_mesh")],['3d-guided','guided',msg("common.measured_cameras_around_a_cargo_rover")],['splat','splat',msg("common.detailed_splat_and_simple_companion_geometry")]]){
        const card=methods.querySelector('[data-method="'+method+'"]');card.prepend(artwork('method-'+id,alt));
        card.querySelector('div').append(el('div',{class:'formats'},...(method==='splat'?['SPZ','GLB','MP4','ZIP']:method==='3d-guided'?['GLB','FBX','STL','ZIP']:['GLB','FBX',msg('common.quads_badge'),'STL','ZIP']).map(x=>el('span',{class:'badge'},x))));
    }
    const card = el("details",{class:"mesh-category",open:true},
      el('summary',{class:'workflow-card'},
        el("div",{class:"art workflow-art"},artwork("image-to-3d",msg("common.reference_to_figure"))),
        el("div",{class:"card-body"},el("span",{class:"eyebrow"},msg("common.image_to_3d_01")),
            el("h3",{},msg("common.create_a_mesh_from_an_image")),
            el("p",{},msg("common.choose_a_guided_workflow_to_turn_a_reference_image_into_a_3d_asset_build_dir")),
            hint(msg("common.each_option_opens_its_own_wizard_with_previews_and_export_choices_start_with")),
            el("div",{class:"formats"},["SPZ","GLB","FBX","OBJ","BLEND","STL","PNG","MP4","ZIP"].map(x=>el("span",{class:"badge"},x))),
            el('span',{class:'method-disclosure'},msg("common.explore_image_to_3d_workflows")))),
        shell.pendingMeshHandoff?hint(msg("common.your_created_image_is_ready_choose_which_mesh_method_should_use_it")):null,methods);
    const imageCard=el('article',{class:'planned-workflow'},artwork("text",msg("common.images_from_description")),el('div',{},
        el('div',{class:'workflow-card-heading'},el('span',{class:'badge'},msg("common.available")),
            button(msg("common.create_images"),()=>{delete shell.imageOrigin;shell.openImages('Create Images');},{class:'primary'})),
        el('h3',{},msg("common.create_images_and_3d_assets_from_a_text_prompt")),
        hint(msg("common.create_and_edit_references_with_models_from_qwen_and_black_forest_labs_then"))));
    const hairCard=el('article',{class:'planned-workflow'},artwork("hair",msg("common.hair_cards_and_bones")),el('div',{},
        el('div',{class:'workflow-card-heading'},el('span',{class:'badge'},msg("common.hairdeck")),
            el('div',{class:'workflow-card-controls'},button(msg("common.open_hair_wizard"),()=>shell.openHairWizard(),{class:'primary'}),
                button(msg("common.view_graph"),()=>showHairWorkflow(),{title:msg("common.view_hair_workflow")}),
                shell.node.properties.foundryHair?.runId?button(msg("common.resume"),()=>shell.openHairWizard({resume:true}),{title:msg("common.resume_hair_asset")}):null)),
        el('h3',{},msg("common.create_rigged_hair_with_hairdeck")),
        hint(msg("common.powered_by_hairdeck_from_hyz317_and_its_researchers_with_fenglairh_s_comfyui"))));
    const ccoreCard=image=>el('article',{class:'planned-workflow','data-workflow':image?'ccore-image':'ccore'},
        el('img',{src:new URL(image?'../../assets/foundry/ccore-image.webp':'../../assets/foundry/ccore-prop.svg',import.meta.url).href,
            alt:image?msg("common.finished_field_radio_with_an_orange_handle_beside_its_reference_sketch"):msg("common.stylized_cargo_crate_with_orange_latches"),
            loading:'lazy',decoding:'async'}),el('div',{},
            el('div',{class:'workflow-card-heading'},el('span',{class:'badge'},image?msg("common.ccore_image_text"):msg("common.ccore_text_to_prop")),
                el('div',{class:'workflow-card-controls'},
                    button(image?msg("common.open_image_text_wizard"):msg("common.open_prop_wizard"),()=>shell.openCcoreWizard({image}),{class:'primary'}),
                    button(msg("common.view_graph"),async()=>{
                        const {showPropGraph}=await import('../ccore/graph.js');
                        showPropGraph(shell.node,image);
                    },{title:msg("common.view_ccore_workflow")}),
                    shell.node.properties[image?'foundryCcoreImage':'foundryCcore']?.id?button(msg("common.resume"),()=>shell.openCcoreWizard({image,resume:true}),{title:image?msg("common.resume_image_text_prop"):msg("common.resume_ccore_prop")}):null)),
            el('h3',{},image?msg("common.create_a_prop_from_image_text"):msg("common.create_a_prop_from_text")),
            hint(image?msg("common.give_ccore_glb_3d_coder_one_reference_and_describe_what_to_keep_or_change_re"):msg("common.describe_a_stylized_game_prop_such_as_a_crate_lantern_or_control_panel_power"))));
    const garmentCard = el('article', {class:'planned-workflow', 'data-workflow':'garment-particles'},
        el('img', {src:new URL('../../assets/foundry/garment.webp', import.meta.url).href,
            alt:msg("common.tailored_utility_jacket_with_a_sewing_pattern_and_mesh_overlay"), loading:'lazy', decoding:'async'}),
        el('div', {}, el('div', {class:'workflow-card-heading'}, el('span', {class:'badge'}, msg("common.garment_particles_experimental")),
            el('div', {class:'workflow-card-controls'},
                button(msg("common.open_garment_wizard"), () => shell.openGarmentWizard(), {class:'primary'}),
                button(msg("common.view_graph"), async () => {
                    const {showGarmentGraph} = await import('../garment/graph.js');
                    showGarmentGraph(shell.node);
                }, {title:msg("common.view_garment_particles_workflow")}),
                shell.node.properties.foundryGarment?.id
                    ? button(msg("common.resume"), () => shell.openGarmentWizard({resume:true}), {title:msg("common.resume_garment")}) : null)),
        el('h3', {}, msg("common.create_clothing_with_garment_particles")),
        hint(msg("common.powered_by_garment_particles_from_kiyohiro_nakayama_and_collaborators_design"))));
    return el("div",{},card,el("div",{class:"future-workflows"},ccoreCard(false),ccoreCard(true),hairCard,garmentCard,imageCard,...planned.map(([id,name,description])=>el("article",{class:"planned-workflow"},artwork(id,name),el("div",{},el("span",{class:"badge"},msg("common.coming_soon_2")),el("h3",{},name),hint(description))))));
}
