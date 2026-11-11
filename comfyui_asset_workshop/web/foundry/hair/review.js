import {sourceMessage} from "../i18n.js";
import {msg} from "../i18n.js";
import {el,button,hint} from '../dom.js';
import {dialog} from '../dialogs.js';
import {mountMesh} from '../wizard/preview.js';

export const hairFileURL=(id,path,download=false)=>'/mumblebox-foundry/v1/hair/runs/'+id+'/file?'+new URLSearchParams({path,...(download?{download:'1'}:{})});

const labels={preview:["result",msg("hair.hairdeck_multi_view_sheet")],preprocess:["input",msg("hair.hairdeck_processing_sheet")],model_input:["input",msg("hair.model_input_crop")],hair_mask:["input",msg("hair.detected_hair")],face_mask:["input",msg("hair.detected_face")],base_color:["material",msg("hair.base_color_and_opacity")],normal:["material",msg("hair.strand_normal_map")],roughness:["material",msg("hair.roughness")],alpha:["material",msg("hair.opacity")],uv_layout:["material",msg("hair.uv_layout_for_painting")],metallic_roughness:["material",msg("hair.gltf_metallic_and_roughness")],unity_metallic_smoothness:["material",msg("hair.unity_metallic_and_smoothness")]};
export function displayFiles(item){
    if(item?.displays)return item.displays;
    // Older saved runs stay reviewable without rewriting their assets.
    return (item?.files||[]).flatMap(f=>{
        const role=Object.keys(labels).find(k=>f.filename===k+'.png'||f.filename.startsWith(k+'_0')&&f.filename.endsWith('.png'));
        return role?[{role,group:labels[role][0],label:labels[role][1],path:f.subfolder+'/'+f.filename}]:[];
    });
}

export function preprocessingWarnings(item){
    const data=item?.preprocess_notes||{};
    const messages={matte_uncertain:'HairDeck is unsure about this image’s segmentation. Check the processing sheet.',
        box_from_low_scores:'Hair or face detection had low confidence. Check the crop before continuing.',
        matte_disagree:'The foreground masks disagree. Review the processing sheet carefully.',
        box_fallback:'HairDeck used a fallback crop. Check that the complete hairstyle is visible.',
        no_person_mask:'No foreground person mask was detected.',no_hair:'HairDeck did not detect hair; the face was used to frame the reference.',
        no_hair_no_face:'Neither hair nor face was detected; HairDeck used the whole image.'};
    const explained=[data.status,...(data.notes||[])].filter(n=>messages[n]).map(n=>messages[n]);
    return [...new Set(explained.length?explained:data.warnings||[])];
}

export function imageSheet(wizard,item,group){
    const images=displayFiles(item).filter(f=>f.group===group);
    if(!images.length)return null;
    return el('div',{class:'hair-diagnostics','data-hair-sheet':group},...images.map(f=>el('figure',{},
        button(el('img',{src:hairFileURL(wizard.runId,f.path),alt:f.label,loading:'lazy'}),()=>{
            dialog(wizard.shell,f.label,el('img',{class:'hair-full-image',src:hairFileURL(wizard.runId,f.path),alt:f.label}));
        },{class:'hair-image-button','aria-label':msg("hair.enlarge", {label: f.label})}),
        el('figcaption',{},f.label,el('a',{href:hairFileURL(wizard.runId,f.path,true),class:'hair-save-image'},msg("hair.download_png"))))));
}

export function hairViewer(wizard,item,{compact=false}={}){
    if(!item)return hint(msg("hair.the_saved_hairdeck_preview_will_appear_here"));
    const host=el('div',{class:'wizard-mesh hair-viewer'+(compact?' hair-viewer-compact':''),'aria-label':msg("hair.hairdeck_variation_seed", {value1: item.measurements?.seed})});
    const state=(wizard.reviewState??={})[item.checkpoint]??={head:true,chains:false};
    const download=el('a',{class:'hair-view-download',title:msg("hair.static_review_glb_visible_chain_tubes_are_diagnostic_geometry_not_a_bone_rig")},msg("hair.download_view_glb"));
    let disposed=false,cleanup,revision=0;
    const show=async()=>{
        const current=++revision;cleanup?.();host.replaceChildren();
        const key=(state.head?'head':'hair')+(state.chains?'_chains':'');
        const path=item.views?.[key]||(state.chains&&item.bone_model?item.bone_model:item.model);
        download.href=hairFileURL(wizard.runId,path,true);download.download=path.split('/').at(-1);
        try{
            const dispose=await mountMesh(host,hairFileURL(wizard.runId,path),wizard.cap.viewer_module);
            if(disposed||current!==revision)dispose();else{
                cleanup=dispose;host.dataset.loaded=path;host.hairViewer=dispose.viewer;
                // HairDeck's reference previews use a clear studio background.
                // Keep the native renderer, without a distracting modelling grid.
                dispose.viewer?.toggleGrid?.(false);dispose.viewer?.setBackgroundColor?.('#edf0e8');
            }
        }catch(error){if(!disposed&&current===revision)host.replaceChildren(el('p',{role:'alert'},sourceMessage(error.message)));}
    };
    wizard.disposers.push(()=>{disposed=true;revision++;cleanup?.();});
    setTimeout(()=>{if(!disposed)show();},0);
    const toolbar=el('div',{class:'hair-viewer-tools'},
        item.views?el('label',{},el('input',{type:'checkbox',checked:state.head,onchange:e=>{state.head=e.target.checked;wizard.remember();show();}}),msg("hair.reference_head")):null,
        item.views?.head_chains||item.bone_model?el('label',{},el('input',{type:'checkbox',checked:state.chains,onchange:e=>{state.chains=e.target.checked;wizard.remember();show();}}),msg("hair.predicted_chains")):null,
        button(msg("hair.reset_view"),()=>{cleanup?.viewer?.fitToViewer();cleanup?.viewer?.forceRender();}),download);
    return el('section',{class:'hair-model-review'},toolbar,host,compact?null:hint(msg("hair.drag_to_orbit_scroll_to_zoom_orange_chains_show_the_prediction_the_exported")));
}

export function variationCards(wizard){
    return el('div',{class:'hair-variations','aria-label':msg("hair.compare_hairdeck_variations")},...(wizard.run?.variants||[]).map((item,index)=>
        el('article',{class:'hair-variation'+((wizard.selected||0)===index?' selected':''),'data-variation':index},
            el('header',{},el('h3',{},msg("hair.variation", {value1: index+1})),el('span',{},msg("hair.seed", {seed: item.measurements.seed}))),
            hairViewer(wizard,item,{compact:true}),
            hint(msg("hair.cards_predicted_chains", {value1: item.measurements.hair_cards, value2: item.measurements.generated_chains})),
            button((wizard.selected||0)===index?msg("hair.selected_for_editing_and_export"):msg("hair.use_this_variation"),()=>{
                wizard.selected=index;wizard.remember();wizard.render();
            },{'aria-pressed':String((wizard.selected||0)===index),class:(wizard.selected||0)===index?'primary':''}))));
}
