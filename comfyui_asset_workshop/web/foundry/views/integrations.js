import {sourceMessage} from "../i18n.js";
import {msg, setText, appendContent, replaceContent} from "../i18n.js";
import {el,button,hint,field,link} from "../dom.js";
import {request} from "../services.js";
import {dialog} from "../dialogs.js";
import {modelUsageRows} from "../../model-usage.js";
import {activity} from "../activity.js";
import {activityState} from "../activity-state.js";
import {showCivitaiHelp} from "../connection-help.js";
const BASE="/asset-workshop/v2/civitai";
const NSFW_KEY="mumblebox-civitai-nsfw";
const profiles={"sdxl_base":"SDXL 1.0","klein4":"FLUX.2 Klein 4B","klein4_base":"FLUX.2 Klein 4B base",
    "klein_base":"FLUX.2 Klein 9B base","klein_distilled":"FLUX.2 Klein 9B","qwen21":"Qwen Image 2.1","qwen2511":"Qwen Image Edit 2511"};
const size=n=>n>=1024**3?(n/1024**3).toFixed(2)+" GB":(n/1024**2).toFixed(1)+" MB";
const select=(label,options)=>el("select",{"aria-label":label},Object.entries(options).map(([value,text])=>el("option",{value},text)));

export async function render(shell) {
    let disposed=false,sequence=0,controller,timer,cursor="",items=[];
    const profile=select(msg("common.image_model_family"),profiles);
    const kind=select(msg("common.resource_type"),{LORA:"LoRAs",Checkpoint:"Checkpoints"});
    const query=el("input",{type:"search",placeholder:msg("common.name_or_keyword"),"aria-label":msg("common.search_civitai")});
    const sort=select(msg("common.sort_by"),{"Highest Rated":"Highest rated","Most Downloaded":"Most downloaded",Newest:"Newest"});
    let includeNsfw=false;
    try{includeNsfw=localStorage.getItem(NSFW_KEY)==="true";}catch{}
    const nsfw=el("input",{type:"checkbox",checked:includeNsfw,"aria-label":msg("common.include_nsfw_resources")});
    const results=el("div",{class:"model-list"});
    const feedback=el("p",{class:"muted",role:"status"},msg("common.choose_a_model_family_and_search_for_compatible_resources"));
    const status=el("div",{class:"note-panel"});
    const downloadActivity=activity();
    const installed=el("div",{class:"library-list"});
    const searchButton=button(msg("common.search"),()=>search(false),{class:"primary"});
    const more=button(msg("common.load_more"),()=>search(true),{hidden:true});
    const agent=shell.agentSetup.integration();
    const root=el("div",{class:"civitai-browser"},agent.element,
        el("div",{class:"page-head civitai-heading"},el("h2",{},msg("common.civitai_model_browser")),
            button(msg("common.connection_settings"),()=>shell.settings({service:"civitai"}))),
        el("div",{class:"civitai-intro"},
            el("p",{class:"muted"},link(msg("common.civitai"),"https://civitai.com"),msg("common.is_an_independent_third_party_platform_models_and_loras_belong_to_their_crea")),
            hint(msg("common.for_initial_image_creation_only_turnarounds_use_foundry_s_built_in_supported"))),
        el("div",{class:"filters"},field(msg("common.model_family"),profile),field(msg("common.resource"),kind),field(msg("common.search"),query),field(msg("common.sort"),sort),searchButton),
        el("div",{class:"civitai-options"},el("label",{class:"choice"},nsfw,msg("common.include_nsfw_resources")),
            el("div",{class:"civitai-auth-help"},hint(msg("common.some_downloads_require_a_civitai_api_key")),
                button(msg("common.how_to_connect_civitai"),()=>showCivitaiHelp(shell),{class:"text-link","aria-haspopup":"dialog"}))),
        feedback,results,more,status,el("h3",{style:"margin:26px 0 14px"},msg("common.installed_resources")),installed,
        hint(msg("common.downloads_are_placed_in_the_correct_comfyui_model_or_lora_folder_the_upcomin")));
    query.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();search(false);}});
    for(const control of [profile,kind,sort,nsfw])control.addEventListener("change",()=>{
        if(control===nsfw){try{localStorage.setItem(NSFW_KEY,String(nsfw.checked));}catch{}}
        search(false);
    });

    async function search(append) {
        controller?.abort();controller=new AbortController();
        const current=++sequence;
        if(!append){cursor="";items=[];results.replaceChildren();more.hidden=true;}
        searchButton.disabled=true;more.disabled=true;setText(feedback, msg("common.searching_civitai"));
        const params=new URLSearchParams({profile:profile.value,kind:kind.value,query:query.value,sort:sort.value,period:"AllTime",nsfw:String(nsfw.checked)});
        if(append&&cursor)params.set("cursor",cursor);
        try {
            const data=await request(BASE+"/search?"+params,undefined,{signal:controller.signal});
            if(disposed||current!==sequence)return;
            items=[...new Map((append?[...items,...data.items]:data.items).map(item=>[item.id,item])).values()];cursor=data.next_cursor;
            setText(feedback, items.length?msg("common.resources_shown_review_each_version_and_its_license_before_downloading", {value1: items.length}):msg("common.no_matching_resources_try_another_name_or_model_family"));
            replaceContent(results, ...items.map(model=>el("article",{class:"model-card resource-card"},preview(model),el("div",{class:"resource-card-body"},el("h3",{},model.name),
                hint((model.creator||"Creator not listed")+" · "+model.type),
                hint(model.description.slice(0,180)+(model.description.length>180?"…":"")),
                el("div",{class:"actions"},button(msg("common.download"),()=>detail(model),{class:"primary"}),button(msg("common.details"),()=>detail(model)),link(msg("common.view_on_civitai"),model.source_url))))));
            more.hidden=!cursor;
        } catch(e){if(e.name!=="AbortError"&&!disposed&&current===sequence)setText(feedback, sourceMessage(e.message));}
        finally{if(current===sequence){searchButton.disabled=false;more.disabled=false;}}
    }
    function preview(model){
        const version=model.versions.find(v=>v.compatible)||model.versions[0],image=version?.images?.[0];
        return button(image?el("img",{src:image.url,alt:msg("common.preview_of", {name: model.name}),loading:"lazy",decoding:"async",referrerPolicy:"no-referrer",
            onerror:e=>{e.target.replaceWith(el("span",{},msg("common.preview_unavailable")));}}):el("span",{},msg("common.no_preview_available")),
            ()=>detail(model),{class:"resource-preview","aria-label":msg("common.open", {name: model.name})});
    }
    async function detail(model) {
        try {
            const selectedProfile=profile.value,selectedKind=kind.value,current=sequence;
            const full=await request(BASE+"/model/"+model.id+"?"+new URLSearchParams({profile:selectedProfile,nsfw:String(nsfw.checked)}));
            if(disposed||current!==sequence)return;
            const versions=select(msg("common.resource_version"),Object.fromEntries(full.versions.map(v=>[v.id,v.name+" · "+v.base_model+(v.compatible?"":" · incompatible")])));
            const preferred=full.versions.find(v=>v.compatible&&v.files.some(f=>f.eligible));
            if(preferred)versions.value=String(preferred.id);
            const files=el("div",{});
            const redraw=()=>{
                const version=full.versions.find(v=>String(v.id)===versions.value);
                replaceContent(files, el("div",{class:"resource-previews"},...(version?.images||[]).map(image=>
                    el("a",{href:image.url,target:"_blank",rel:"noopener noreferrer"},el("img",{src:image.url,alt:msg("common.creator_preview_for", {name: version.name}),
                        loading:"lazy",decoding:"async",referrerPolicy:"no-referrer"})))), hint(version?.notes||"No version notes supplied."), ...(version?.triggers?.length?[hint(msg("common.trigger_words", {value1: version.triggers.join(", ")}))]:[]), ...((version?.files)||[]).map(file=>el("div",{class:"settings-section"},
                        el("p",{class:"filename"},file.name),hint(size(file.size_bytes)+" · "+file.format),
                        hint(file.eligible?msg("common.compatible_file_with_a_published_checksum"):file.reason||"Not eligible for installation."),
                        button(msg("common.download"),async event=>{
                            const control=event.currentTarget;control.disabled=true;
                            try {
                                await request(BASE+"/download",{model_id:full.id,version_id:version.id,file_id:file.id,profile:selectedProfile,kind:selectedKind});
                                shell.message(msg("common.downloading_the_selected_resource_progress_appears_below_and_in_the_header"));
                                await refreshStatus();
                            } catch(e){shell.message(sourceMessage(e.message),true);}
                            finally{control.disabled=!file.eligible;}
                        },{disabled:!file.eligible,class:"primary"}))));
            };
            versions.addEventListener("change",redraw);redraw();
            dialog(shell,msg("common.download_2", {name: full.name}),el("div",{},hint(msg("common.choose_a_version_and_file_the_app_installs_it_in_the_correct_folder_for_init")),link(msg("common.license_and_resource_page"),full.source_url),
                field(msg("common.version"),versions),files,el("h3",{},msg("common.author_permissions")),
                el("dl",{},...modelUsageRows(full.permissions,true).flatMap(([key,value])=>[el("dt",{},key),el("dd",{},value)]))));
        } catch(e){shell.message(sourceMessage(e.message),true);}
    }
    async function refreshStatus() {
        try{
            const [data,local]=await Promise.all([request(BASE+"/status"),request(BASE+"/installed")]);
            if(disposed)return;
            const d=data.download;
            downloadActivity.update({...activityState({download:d}),
                label:d.status==="running"?msg("common.downloading", {value1: d.name||"resource"}):d.status==="complete"?msg("common.download_complete"):d.status==="idle"?msg("common.no_download_active"):msg("common.download_3", {status: d.status}),
                detail:d.error||[d.total?size(d.bytes||0)+" / "+size(d.total):"",d.phase||""].filter(Boolean).join(" · ")});
            replaceContent(status, el("div",{class:"connection-line"},el("strong",{},msg("common.civitai")),
                el("span",{class:"badge"},data.connection.connected?msg("common.connected"):msg("common.not_connected")),
                !data.connection.connected?hint(msg("common.public_browsing_is_available_some_downloads_require_a_connection")):null), downloadActivity.element);
            const controls=el("div",{class:"actions"});
            if(d.status==="running")appendContent(controls, button(msg("common.pause_download"),()=>control("pause")));
            if(["paused","failed"].includes(d.status))appendContent(controls, button(msg("common.resume_retry"),()=>control("retry")));
            if(["running","paused","failed"].includes(d.status))appendContent(controls, button(msg("common.cancel_download"),()=>control("cancel")));
            status.append(controls);
            replaceContent(installed, ...local.items.map(item=>el("article",{class:"model-card"},el("strong",{},item.model_name||item.name||item.file_id),
                hint(msg("common.initial_image_creation", {value1: item.base_model||item.profile||"", value2: item.kind||""})),
                el("div",{class:"filename"},item.relative_path||item.name||""),el("span",{class:"badge"},msg("common.installed")))));
            if(!local.items.length)appendContent(installed, hint(msg("common.no_resources_have_been_installed_through_this_browser_yet")));
        }catch(e){if(!disposed)status.replaceChildren(hint(sourceMessage(e.message)));}
        finally{clearTimeout(timer);if(!disposed)timer=setTimeout(refreshStatus,3000);}
    }
    async function control(action) {
        try{await request(BASE+"/download/control",{action});await refreshStatus();}
        catch(e){shell.message(sourceMessage(e.message),true);}
    }
    await refreshStatus();
    search(false);
    return {element:root,dispose:()=>{disposed=true;agent.dispose();controller?.abort();clearTimeout(timer);sequence++;}};
}
