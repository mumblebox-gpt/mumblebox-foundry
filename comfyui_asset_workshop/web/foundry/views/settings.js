import {sourceMessage} from "../i18n.js";
import {languages, currentLanguage} from "../i18n.js";
import {msg, setText, appendContent} from "../i18n.js";
import {cacheControls} from '../cache-controls.js';
import {el,button,hint,field} from "../dom.js";
import {request} from "../services.js";
import {dialog} from "../dialogs.js";
import {resourceLists} from "./resources.js";
import {civitaiInstructions} from "../connection-help.js";

function connection(shell,service,label) {
    const token=el("input",{type:"password",autocomplete:"off",spellcheck:false,placeholder:msg("common.paste_a_new_access_token"),"aria-label":msg("common.access_token", {label: label})});
    const status=el("p",{class:"muted",role:"status"},msg("common.checking_connection"));
    const error=el("p",{class:"muted","aria-live":"polite"});
    const section=el("section",{class:"settings-section","data-service":service},el("h3",{},label),
        status,field(msg("common.access_token_2"),token,msg("common.saved_securely_on_this_computer_your_saved_token_is_never_displayed")),error);
    const path=service==="hugging-face"?"/asset-workshop/hugging-face":"/asset-workshop/v2/civitai/connection";
    const controls=[];
    const update=data=>{
        const connection=data.connection||data;
        setText(status, connection.connected?msg("common.connected_2", {value1: connection.account?" · "+connection.account:""}):msg("common.not_connected"));
        setText(error, connection.error||"");
        setText(controls[0], connection.connected?msg("common.replace_token"):msg("common.connect"));
        controls[1].disabled=!connection.connected;
        controls[2].disabled=!connection.connected;
    };
    for(const [action,labelText] of [["connect",msg("common.connect")],["test",msg("common.test_connection")],["disconnect",msg("common.disconnect")]]) {
        const control=button(labelText,async()=>{
            controls.forEach(b=>b.disabled=true);setText(error, "");
            try {
                const data=await request(path,action==="connect"?{action,token:token.value}:{action});
                if(action==="connect")token.value="";
                update(data);shell.message(msg("common.connection_updated", {label: label}));
            } catch(e){setText(error, sourceMessage(e.message));}
            finally{controls[0].disabled=false;await refresh();}
        });
        controls.push(control);
    }
    async function refresh() {
        try {
            const data=await request(service==="hugging-face"?"/asset-workshop/status":"/asset-workshop/v2/civitai/status");
            update(service==="hugging-face"?data.hugging_face:data);
        } catch(e){setText(status, msg("common.connection_status_unavailable"));setText(error, sourceMessage(e.message));controls.forEach(b=>b.disabled=false);}
    }
    section.append(el("div",{class:"actions"},...controls));
    if(service==="civitai")appendContent(section, el("details",{class:"connection-help-inline"},
        el("summary",{},msg("common.where_do_i_get_my_civitai_api_key")),civitaiInstructions()));
    refresh();
    return {element:section,clear:()=>{token.value="";}};
}
export function render(shell,{service}={}) {
    const motion=el("select",{"aria-label":msg("common.busy_animations"),onchange:async e=>{
        try{shell.data.preferences=await request("preferences",{busy_motion:e.target.value},{method:"PATCH"});
            shell.root.dataset.motion=shell.data.preferences.busy_motion;
        }catch(error){shell.message(sourceMessage(error.message),true);}
    }},...[["system",msg("common.follow_system_motion_preference")],["full",msg("common.spin_spin_spin_rest")],["paused",msg("common.pause_animation")]].map(([value,label])=>
        el("option",{value,selected:value===(shell.data.preferences.busy_motion||"system")},label)));
    const appearance=el("section",{class:"settings-section"},el("h3",{},msg("common.appearance_and_language")),
        el("div",{class:"actions"},button(msg("common.light_theme"),()=>shell.setTheme("light")),button(msg("common.dark_theme"),()=>shell.setTheme("dark"))),
        field(msg("common.busy_animations"),motion,msg("common.applies_to_progress_indicators_pause_keeps_them_still_system_follows_your_mo")),
        field(msg("common.language"),
            el("select", {onchange:event=>shell.setLanguage(event.target.value), "aria-label":msg("common.language")},
                ...languages.map(language=>el("option", {value:language.id, selected:language.id===currentLanguage()}, language.label))),
            msg("common.language_switch_help")));
    const profile=el("select",{"aria-label":msg("common.memory_profile"),onchange:async e=>{
        try{shell.data.preferences=await request("preferences",{profile:e.target.value},{method:"PATCH"});}
        catch(error){shell.message(sourceMessage(error.message),true);}
    }},el("option",{value:"default",selected:true},msg("common.default_current_tested_workflow_settings")),
       el("option",{value:"low",disabled:true},msg("common.low_memory_coming_soon")),
       el("option",{value:"high",disabled:true},msg("common.high_memory_coming_soon")));
    const profiles=el("section",{class:"settings-section"},el("h3",{},msg("common.memory_profile")),
        field(msg("common.hardware_profile"),profile,msg("common.wizard_choices_override_the_default_profile")),
        hint(msg("common.reference_hardware_16_gb_vram_and_64_gb_ram_lower_memory_profiles_are_still")));

    const hf=connection(shell,"hugging-face",msg("common.hugging_face")),civitai=connection(shell,"civitai",msg("common.civitai"));
    const resources=resourceLists(shell);
    const updates=shell.updates.settings();
    const cache=cacheControls(shell);
    const content=el("div",{},cache.element,appearance,profiles,updates.element,hf.element,civitai.element,
        resources.element);
    const modal=dialog(shell,msg("common.settings"),content);
    modal.surface.addEventListener("foundry-close",()=>{hf.clear();civitai.clear();resources.dispose();updates.dispose();cache.dispose();});
    const target=service==="civitai"?civitai.element:service==="hugging-face"?hf.element:null;
    if(target)requestAnimationFrame(()=>{
        if(!modal.surface.isConnected)return;
        const scroller=modal.surface.querySelector(".dialog-content");
        const bounds=scroller.getBoundingClientRect();
        // Comfy scales the node; scrollTop uses unscaled CSS pixels.
        const scale=bounds.height/scroller.offsetHeight||1;
        scroller.scrollTop+=(target.getBoundingClientRect().top-bounds.top)/scale-12;
        target.querySelector("input").focus({preventScroll:true});
    });
    return modal;
}
