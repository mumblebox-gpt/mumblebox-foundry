import {cacheControls} from '../cache-controls.js';
import {el,button,hint,field} from "../dom.js";
import {request} from "../services.js";
import {dialog} from "../dialogs.js";
import {resourceLists} from "./resources.js";
import {civitaiInstructions} from "../connection-help.js";

function connection(shell,service,label) {
    const token=el("input",{type:"password",autocomplete:"off",spellcheck:false,placeholder:"Paste a new access token","aria-label":label+" access token"});
    const status=el("p",{class:"muted",role:"status"},"Checking connection…");
    const error=el("p",{class:"muted","aria-live":"polite"});
    const section=el("section",{class:"settings-section","data-service":service},el("h3",{},label),
        status,field("Access token",token,"Saved securely on this computer. Your saved token is never displayed."),error);
    const path=service==="hugging-face"?"/asset-workshop/hugging-face":"/asset-workshop/v2/civitai/connection";
    const controls=[];
    const update=data=>{
        const connection=data.connection||data;
        status.textContent=connection.connected?"Connected"+(connection.account?" · "+connection.account:""):"Not connected";
        error.textContent=connection.error||"";
        controls[0].textContent=connection.connected?"Replace token":"Connect";
        controls[1].disabled=!connection.connected;
        controls[2].disabled=!connection.connected;
    };
    for(const [action,labelText] of [["connect","Connect"],["test","Test connection"],["disconnect","Disconnect"]]) {
        const control=button(labelText,async()=>{
            controls.forEach(b=>b.disabled=true);error.textContent="";
            try {
                const data=await request(path,action==="connect"?{action,token:token.value}:{action});
                if(action==="connect")token.value="";
                update(data);shell.message(label+" connection updated.");
            } catch(e){error.textContent=e.message;}
            finally{controls[0].disabled=false;await refresh();}
        });
        controls.push(control);
    }
    async function refresh() {
        try {
            const data=await request(service==="hugging-face"?"/asset-workshop/status":"/asset-workshop/v2/civitai/status");
            update(service==="hugging-face"?data.hugging_face:data);
        } catch(e){status.textContent="Connection status unavailable";error.textContent=e.message;controls.forEach(b=>b.disabled=false);}
    }
    section.append(el("div",{class:"actions"},...controls));
    if(service==="civitai")section.append(el("details",{class:"connection-help-inline"},
        el("summary",{},"Where do I get my Civitai API key?"),civitaiInstructions()));
    refresh();
    return {element:section,clear:()=>{token.value="";}};
}
export function render(shell,{service}={}) {
    const motion=el("select",{"aria-label":"Busy animations",onchange:async e=>{
        try{shell.data.preferences=await request("preferences",{busy_motion:e.target.value},{method:"PATCH"});
            shell.root.dataset.motion=shell.data.preferences.busy_motion;
        }catch(error){shell.message(error.message,true);}
    }},...[["system","Follow system motion preference"],["full","Spin, spin, spin, rest"],["paused","Pause animation"]].map(([value,label])=>
        el("option",{value,selected:value===(shell.data.preferences.busy_motion||"system")},label)));
    const appearance=el("section",{class:"settings-section"},el("h3",{},"Appearance and language"),
        el("div",{class:"actions"},button("Light theme",()=>shell.setTheme("light")),button("Dark theme",()=>shell.setTheme("dark"))),
        field("Busy animations",motion,"Applies to progress indicators. Pause keeps them still; System follows your motion preference."),
        hint("Language: English. More translations are planned."));
    const profile=el("select",{"aria-label":"Memory profile",onchange:async e=>{
        try{shell.data.preferences=await request("preferences",{profile:e.target.value},{method:"PATCH"});}
        catch(error){shell.message(error.message,true);}
    }},el("option",{value:"default",selected:true},"Default · current tested workflow settings"),
       el("option",{value:"low",disabled:true},"Low memory · Coming soon"),
       el("option",{value:"high",disabled:true},"High memory · Coming soon"));
    const profiles=el("section",{class:"settings-section"},el("h3",{},"Memory profile"),
        field("Hardware profile",profile,"Wizard choices override the default profile."),
        hint("Reference hardware: 16 GB VRAM and 64 GB RAM. Lower-memory profiles are still being evaluated."));

    const hf=connection(shell,"hugging-face","Hugging Face"),civitai=connection(shell,"civitai","Civitai");
    const resources=resourceLists(shell);
    const updates=shell.updates.settings();
    const cache=cacheControls(shell);
    const content=el("div",{},cache.element,appearance,profiles,updates.element,hf.element,civitai.element,
        resources.element);
    const modal=dialog(shell,"Settings",content);
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
