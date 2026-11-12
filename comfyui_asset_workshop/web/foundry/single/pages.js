import {sourceMessage} from "../i18n.js";
import {msg} from "../i18n.js";
import {el,button,hint,field} from '../dom.js';
import {capturePhoto,chooseSavedReference,uploadReference,inputURL} from '../images/references.js';
import {optionsPage} from '../wizard/pages.js';
async function replace(w,file){if(!file)return;w.draft.references=[{...await uploadReference(file),role:'primary'}];delete w.draft.image_creation;w.remember();}
export function singleInputPage(w){
    const file=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,'aria-label':msg("mesh.upload_single_reference"),onchange:e=>w.act(()=>replace(w,e.target.files[0]))});
    const ref=w.draft.references[0];
    return el('div',{},hint(msg("mesh.one_image_is_all_you_need_a_three_quarter_view_shows_more_of_the_shape_keep")),
        field(msg("mesh.asset_name"),el('input',{value:w.draft.name,maxLength:100,placeholder:msg("mesh.name_this_asset"),'aria-label':msg("mesh.asset_name"),oninput:e=>{w.draft.name=e.target.value;w.remember();}})),file,
        el('div',{class:'upload-zone',ondragover:e=>{e.preventDefault();e.currentTarget.classList.add('dragging');},ondragleave:e=>e.currentTarget.classList.remove('dragging'),ondrop:e=>{
            e.preventDefault();e.currentTarget.classList.remove('dragging');if(e.dataTransfer.files.length!==1){w.error='Drop exactly one image.';w.render();return;}w.act(()=>replace(w,e.dataTransfer.files[0]));}},
            el('strong',{},ref?msg("mesh.your_starting_image"):msg("mesh.drop_an_image_here")),
            ref?w.image(inputURL(ref.filename),msg("mesh.starting_reference")):hint(msg("mesh.png_jpeg_or_webp_up_to_20_mb")),
            el('div',{class:'actions'},button(ref?msg("mesh.replace_image"):msg("mesh.upload_image"),()=>file.click()),
                button(msg("mesh.take_a_photo"),()=>capturePhoto(w.shell,f=>w.act(()=>replace(w,f))),{disabled:!navigator.mediaDevices}),
                button(msg("mesh.choose_from_gallery"),()=>chooseSavedReference(w.shell,handoff=>w.act(async()=>{
                    w.draft.references=handoff.references;w.draft.image_creation=handoff.image_creation;w.remember();
                }))),
                button(msg("mesh.create_image"),()=>{w.remember();w.shell.imageOrigin={method:'single-image',sessionId:w.sessionId};w.shell.openImages('Create Images');},{class:'primary'}))),
        hint(msg("mesh.no_image_create_one_from_a_description_then_choose_use_in_3d_to_return_here")),
        el('details',{},el('summary',{},msg("mesh.how_this_method_works")),hint(msg("mesh.pixal3d_by_tencent_arc_builds_geometry_from_one_view_using_the_official_comf"))),
        w.nav({next:async()=>{if(!w.draft.references.length)throw Error(msg("mesh.choose_or_create_an_image_first"));w.go(2);}}));
}
export function singleOptionsPage(w){
    const page=optionsPage(w);
    setText(page.firstChild, msg("mesh.pixal3d_builds_from_your_one_reference_hi3d_refines_the_initial_mesh_using_t"));
    page.insertBefore(field(msg("mesh.geometry_seed"),el('input',{type:'number',value:w.draft.overrides.shape_seed??42,min:0,max:9007199254740976,'aria-label':msg("mesh.geometry_seed"),onchange:e=>{w.draft.overrides.shape_seed=Number(e.target.value);w.remember();}}),msg("mesh.keep_the_seed_fixed_to_compare_settings")),page.lastChild);
    return page;
}
