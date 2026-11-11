import {sourceMessage} from "../i18n.js";
import {msg, appendContent, replaceContent} from "../i18n.js";
import {el,button,hint,icon,link} from "../dom.js";
import {request,fileUrl} from "../services.js";
import {dialog} from "../dialogs.js";

const formatSize=n=>n>=1024**3?(n/1024**3).toFixed(2)+" GB":(n/1024**2).toFixed(1)+" MB";
const label = value => sourceMessage(value.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase()));
const number = value => Number.isInteger(value) ? value.toLocaleString() : Number(value).toLocaleString(undefined,{maximumFractionDigits:4});
const measure = value => Array.isArray(value) ? value.map(number).join(" × ") : typeof value === "boolean" ? (value ? msg("package.yes") : msg("package.no")) : typeof value === "number" ? number(value) : String(value);
function measurements(data) {
    return Object.entries(data).map(([section, values]) => {
        if (Array.isArray(values)) return el("section",{},el("h4",{},label(section)),
            el("ul",{},...values.map(v=>el("li",{},el("span",{class:"filename"},v.path),msg("common.px", {value1: measure(v.dimensions), interpretation: v.interpretation})))));
        if (!values || typeof values !== "object") return el("dl",{},el("dt",{},label(section)),el("dd",{},measure(values)));
        return el("section",{},el("h4",{},label(section)),el("dl",{},...Object.entries(values).flatMap(([k,v])=>[el("dt",{},label(k)),el("dd",{},measure(v))])));
    });
}
async function details(shell,item) {
    const data=await request("library/"+item.id);
    const body=el("div",{},el("dl",{},el("dt",{},msg("common.workflow")),el("dd",{},data.workflow),
        el("dt",{},msg("common.created")),el("dd",{},new Date(data.created).toLocaleString()),el("dt",{},msg("common.package")),el("dd",{},msg("common.cataloged_files", {value1: data.file_count, value2: formatSize(data.bytes)}))),
        ...data.variants.map(v=>el("section",{class:"settings-section"},el("h3",{},label(v.id)),hint(sourceMessage(v.description||v.intended_use||"")),
            ...measurements(v.measurements||{}),
            ...(v.validations||[]).map(check=>hint(check.name+" — "+check.status+". "+check.note)),
            ...(v.limitations||[]).map(hint))),
        el("h3",{},msg("common.files_2")),el("div",{class:"file-list"},...data.catalog.files.map(f=>el("div",{},f.path+" · "+formatSize(f.bytes||0)))),
        ...data.warnings.map(text=>hint(text)));
    dialog(shell,data.name,body,[{label:msg("common.close"),run:close=>close()}]);
}
function confirmRemoval(shell,kind,ids) {
    const destructive=el("input",{type:"checkbox"});
    const first=el("div",{},el("p",{},ids?msg("common.remove_this_entry_from", {value1: kind==="mesh"?"History":"Image Gallery"}):msg("common.purge_all_entries_currently_in", {value1: kind==="mesh"?"History":"Image Gallery"})),
        hint(msg("common.saved_files_are_kept_unless_you_explicitly_choose_to_delete_them")),
        el("label",{class:"check-row"},destructive,el("span",{},msg("common.also_delete_saved_files"))));
    dialog(shell,ids?msg("common.remove_entry"):msg("common.purge_history"),first,[
        {label:msg("common.cancel"),run:close=>close()},
        {label:msg("common.review_removal"),primary:true,run:async close=>{
            const review=await request("library/removal-preview",{kind,ids,delete_files:destructive.checked});
            close();
            const explanation=el("div",{},el("p",{},msg(review.count === 1 ? "common.entry_will_be_removed" : "common.entries_will_be_removed", {count: review.count})),
                el("ul",{},...review.names.map(n=>el("li",{},n))),
                review.delete_files?el("div",{},el("strong",{},msg("common.these_saved_files_will_also_be_permanently_deleted")),
                    el("div",{class:"file-list"},...review.files.map(p=>el("div",{},p)))):
                    hint(msg("common.saved_images_meshes_and_zip_files_will_remain_on_disk")));
            dialog(shell,review.delete_files?msg("common.confirm_file_deletion"):msg("common.confirm_entry_removal"),explanation,[
                {label:msg("common.cancel"),run:c=>c()},
                {label:review.delete_files?msg("common.delete_files_and_entries"):msg("common.remove_entries"),primary:true,run:async c=>{
                    const result=await request("library/remove",{token:review.token});
                    if(!result.ok)throw Error(result.error+" "+(result.failures||[]).join(", "));
                    c();shell.message(msg(result.removed_entries === 1 ? "common.entry_removed" : "common.entries_removed", {count: result.removed_entries, files: msg(review.delete_files ? "common.selected_files_deleted" : "common.saved_files_kept")}));
                    if(kind==="mesh")await shell.open("History");
                    else await shell.openImages("Gallery");
                }}]);
        }}]);
}
export async function render(shell,kind) {
    let disposed=false,cursor="",items=[];
    const title=kind==="mesh"?msg("common.history_title"):msg("common.image_gallery_title");
    const intro=kind==="mesh"?msg("common.mesh_history_intro"):msg("common.image_history_intro");
    const root=el("div",{});
    const list=el("div",{class:"library-list"});
    const purge=button(msg("common.purge_history_2"),()=>confirmRemoval(shell,kind,null),{class:"danger",disabled:true});
    const more=button(msg("common.load_more"),()=>load(true),{hidden:true});
    const refresh=button(msg("common.refresh"),()=>load(false));
    appendContent(root, el("div",{class:"page-head"},el("div",{},el("span",{class:"eyebrow"},kind==="mesh"?msg("common.asset_library"):msg("common.image_library")),el("h2",{},title),hint(intro)),
        el("div",{class:"actions"},refresh,purge)), list, more);
    async function load(append) {
        refresh.disabled=true;more.disabled=true;
        try{
            if(!append) {
                const sync=await request("library/sync",{});
                if(sync.failed)shell.message(msg("common.history_notification_s_need_attention_existing_files_are_unchanged", {failed: sync.failed}),true);
            }
            const page=await request("library?"+new URLSearchParams({kind,cursor:append?cursor:"",limit:24}));
            if(disposed)return;
            items=append?[...items,...page.items]:page.items;cursor=page.next_cursor;
            purge.disabled=!items.length;more.hidden=!cursor;
            replaceContent(list, ...items.map(item=>{
                const thumb=el("div",{class:"thumbnail"},item.preview_id?el("img",{src:fileUrl(item.id,item.preview_id),alt:item.name}):icon(kind==="mesh"?"cube":"image",42));
                return el("article",{class:"library-card"},thumb,el("div",{},el("h3",{},item.name),
                    hint(new Date(item.created).toLocaleString()+" · "+item.workflow),
                    el("div",{class:"formats"},...item.formats.filter(Boolean).map(f=>el("span",{class:"badge"},f.toUpperCase()))),
                    hint(msg("common.files_3", {value1: item.file_count, value2: formatSize(item.bytes), value3: item.variants.map(v=>v.id.replaceAll("_"," ")).join(", ")})),
                    el("div",{class:"actions"},button(msg("common.view_details"),()=>details(shell,item).catch(e=>shell.message(sourceMessage(e.message),true))),
                        button(msg("common.open_output_folder"),async()=>{try{const result=await request("library/"+item.id+"/open-folder",{});shell.message(result.location);}catch(e){shell.message(sourceMessage(e.message),true);}}),
                        el("a",{href:fileUrl(item.id,"archive"),download:"",class:"download-link"},msg("common.download_zip")),
                        button(msg("common.delete"),()=>confirmRemoval(shell,kind,[item.id]),{class:"danger"}))));
            }));
            if(!items.length)appendContent(list, el("div",{class:"empty"},icon(kind==="mesh"?"history":"image",42),
                el("h3",{},kind==="mesh"?msg("common.no_mesh_packages_in_history_yet"):msg("common.no_image_creations_yet")),
                hint(kind==="mesh"?msg("common.completed_exports_will_appear_here"):msg("common.this_gallery_will_collect_final_images_when_the_image_creation_workflow_is_a"))));
        }catch(e){if(!disposed){shell.message(sourceMessage(e.message),true);if(!items.length)list.replaceChildren(el("p",{},sourceMessage(e.message)));}}
        finally{refresh.disabled=false;more.disabled=false;}
    }
    await load(false);
    return {element:root,dispose:()=>{disposed=true;}};
}
