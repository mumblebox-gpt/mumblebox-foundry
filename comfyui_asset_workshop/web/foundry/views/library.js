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
    const body=el("div",{},el("dl",{},el("dt",{},msg("common.workflow")),el("dd",{},sourceMessage(data.workflow)),
        el("dt",{},msg("common.created")),el("dd",{},new Date(data.created).toLocaleString()),el("dt",{},msg("common.package")),el("dd",{},msg("common.cataloged_files", {value1: data.file_count, value2: formatSize(data.bytes)}))),
        ...data.variants.map(v=>el("section",{class:"settings-section"},el("h3",{},label(v.id)),hint(sourceMessage(v.description||v.intended_use||"")),
            ...measurements(v.measurements||{}),
            ...(v.validations||[]).map(check=>hint(check.name+" — "+check.status+". "+check.note)),
            ...(v.limitations||[]).map(hint))),
        el("h3",{},msg("common.files_2")),el("div",{class:"file-list"},...data.catalog.files.map(f=>el("div",{},f.path+" · "+formatSize(f.bytes||0)))),
        ...data.warnings.map(text=>hint(text)));
    dialog(shell,data.name,body,[{label:msg("common.close"),run:close=>close()}]);
}
async function reviewRemoval(shell,kind,ids,deleteFiles,onDone,close){
    const review=await request("library/removal-preview",{kind,ids,delete_files:deleteFiles});
    close?.();
    const video=kind==="video";
    const explanation=el("div",{},
        video?hint(msg("common.delete_video_explanation")):
            el("p",{},msg(review.count === 1 ? "common.entry_will_be_removed" : "common.entries_will_be_removed", {count: review.count})),
        el("ul",{},...review.names.map(name=>el("li",{},name))),
        review.delete_files?el("div",{},el("strong",{},msg("common.these_saved_files_will_also_be_permanently_deleted")),
            el("div",{class:"file-list"},...review.files.map(path=>el("div",{},path)))):
            hint(msg("common.saved_images_meshes_and_zip_files_will_remain_on_disk")));
    dialog(shell,video?msg("common.delete_video"):msg(review.delete_files?"common.confirm_file_deletion":"common.confirm_entry_removal"),explanation,[
        {label:msg("common.cancel"),run:cancel=>cancel()},
        {label:video?msg("common.delete_video"):msg(review.delete_files?"common.delete_files_and_entries":"common.remove_entries"),
            primary:true,run:async done=>{
                const result=await request("library/remove",{token:review.token});
                if(!result.ok)throw Error(result.error+" "+(result.failures||[]).join(", "));
                done();shell.message(video?msg("common.video_deleted"):msg(result.removed_entries===1?"common.entry_removed":"common.entries_removed",
                    {count:result.removed_entries,files:msg(review.delete_files?"common.selected_files_deleted":"common.saved_files_kept")}));
                await onDone();
            }}]);
}
function confirmRemoval(shell,kind,ids,onDone) {
    if(kind==="video"){
        return reviewRemoval(shell,kind,ids,true,onDone).catch(error=>shell.message(sourceMessage(error.message),true));
    }
    const destructive=el("input",{type:"checkbox"});
    const location=msg(kind==="mesh"?"common.history":"common.image_gallery_title");
    const first=el("div",{},el("p",{},msg(ids?"common.remove_this_entry_from":"common.purge_all_entries_currently_in",{value1:location})),
        hint(msg("common.saved_files_are_kept_unless_you_explicitly_choose_to_delete_them")),
        el("label",{class:"check-row"},destructive,el("span",{},msg("common.also_delete_saved_files"))));
    dialog(shell,ids?msg("common.remove_entry"):msg("common.purge_history"),first,[
        {label:msg("common.cancel"),run:close=>close()},
        {label:msg("common.review_removal"),primary:true,
            run:close=>reviewRemoval(shell,kind,ids,destructive.checked,onDone,close)}]);
}

function videoCard(shell,item,refresh){
    const url=fileUrl(item.id,"video");
    const media=el("div",{class:"history-video-player"});
    const play=button(msg("common.play_video"),()=>{
        const video=el("video",{src:url+"?play=1",controls:true,playsInline:true,"aria-label":item.name,tabIndex:0});
        media.replaceChildren(video);
        play.hidden=true;
        video.focus({preventScroll:true});
        video.play().catch(()=>{});
    });
    return el("article",{class:"library-card library-video-card"},el("div",{class:"thumbnail"},icon("video",42)),
        el("div",{},el("h3",{},item.name),
            el("p",{class:"muted"},new Date(item.created).toLocaleString()+" · ",sourceMessage(item.workflow)),
            el("div",{class:"filename"},item.filename+" · "+formatSize(item.bytes)),
            el("div",{class:"actions"},play,
                el("a",{href:url,download:"",class:"download-link"},msg("common.download_video")),
                button(msg("common.delete_video"),()=>confirmRemoval(shell,"video",[item.id],refresh),{class:"danger"})),
            media));
}

export async function render(shell,initialKind) {
    let disposed=false,sequence=0,cursor="",items=[];
    let kind=initialKind;
    const history=initialKind==="mesh";
    const root=el("div",{});
    const list=el("div",{class:"library-list"});
    const purge=button(msg("common.purge_history_2"),()=>confirmRemoval(shell,kind,null,()=>load(false)),{class:"danger",disabled:true});
    const more=button(msg("common.load_more"),()=>load(true),{hidden:true});
    const refresh=button(msg("common.refresh"),()=>load(false));
    const intro=el("p",{class:"muted"});
    const tabs={};
    if(history){
        for(const [key,label] of [["mesh","common.history_assets"],["video","common.history_videos"]]){
            tabs[key]=button(msg(label),()=>{
                if(kind===key)return;
                kind=key;cursor="";items=[];list.replaceChildren();load(false);
            });
        }
    }
    appendContent(root,el("div",{class:"page-head"},el("div",{},
        el("span",{class:"eyebrow"},msg(history?"common.asset_library":"common.image_library")),
        el("h2",{},msg(history?"common.history_title":"common.image_gallery_title")),intro),
        el("div",{class:"actions"},...Object.values(tabs),refresh,purge)),list,more);
    async function load(append) {
        const requestId=++sequence;
        const current=()=>!disposed&&requestId===sequence;
        const video=kind==="video";
        const mesh=kind==="mesh";
        for(const [key,tab] of Object.entries(tabs)){
            tab.setAttribute("aria-pressed",String(kind===key));tab.classList.toggle("primary",kind===key);
        }
        replaceContent(intro,msg(video?"common.video_history_intro":mesh?"common.mesh_history_intro":"common.image_history_intro"));
        purge.hidden=video;refresh.disabled=true;more.disabled=true;
        try{
            if(!append) {
                const sync=await request("library/sync",video?{kind:"video"}:{});
                if(!current())return;
                if(sync.failed)shell.message(msg("common.history_notification_s_need_attention_existing_files_are_unchanged",{failed:sync.failed}),true);
            }
            const page=await request("library?"+new URLSearchParams({kind,cursor:append?cursor:"",limit:24}));
            if(!current())return;
            items=append?[...items,...page.items]:page.items;cursor=page.next_cursor;
            purge.disabled=!items.length;more.hidden=!cursor;
            replaceContent(list,...items.map(item=>{
                if(video)return videoCard(shell,item,()=>load(false));
                const thumb=el("div",{class:"thumbnail"},item.preview_id?el("img",{src:fileUrl(item.id,item.preview_id),alt:item.name}):icon(mesh?"cube":"image",42));
                return el("article",{class:"library-card"},thumb,el("div",{},el("h3",{},item.name),
                    el("p",{class:"muted"},new Date(item.created).toLocaleString()+" · ",sourceMessage(item.workflow)),
                    el("div",{class:"formats"},...item.formats.filter(Boolean).map(f=>el("span",{class:"badge"},f.toUpperCase()))),
                    hint(msg("common.files_3",{value1:item.file_count,value2:formatSize(item.bytes),value3:item.variants.map(v=>v.id.replaceAll("_"," ")).join(", ")})),
                    el("div",{class:"actions"},button(msg("common.view_details"),()=>details(shell,item).catch(e=>shell.message(sourceMessage(e.message),true))),
                        button(msg("common.open_output_folder"),async()=>{try{const result=await request("library/"+item.id+"/open-folder",{});shell.message(result.location);}catch(e){shell.message(sourceMessage(e.message),true);}}),
                        el("a",{href:fileUrl(item.id,"archive"),download:"",class:"download-link"},msg("common.download_zip")),
                        button(msg("common.delete"),()=>confirmRemoval(shell,kind,[item.id],()=>load(false)),{class:"danger"}))));
            }));
            if(!items.length)appendContent(list,el("div",{class:"empty"},icon(video?"video":mesh?"history":"image",42),
                el("h3",{},msg(video?"common.no_videos_in_history":mesh?"common.no_mesh_packages_in_history_yet":"common.no_image_creations_yet")),
                video?null:hint(msg(mesh?"common.completed_exports_will_appear_here":"common.this_gallery_will_collect_final_images_when_the_image_creation_workflow_is_a"))));
        }catch(error){
            if(current()){shell.message(sourceMessage(error.message),true);if(!items.length)replaceContent(list,el("p",{},sourceMessage(error.message)));}
        }finally{if(current()){refresh.disabled=false;more.disabled=false;}}
    }
    await load(false);
    return {element:root,dispose:()=>{disposed=true;}};
}
