import {el,button,hint,icon} from "../dom.js";
import {gallery} from '../images/gallery.js';
import {creatorOrigin,ImageCreator} from '../images/controller.js';

export async function render(shell){
    let disposed=false,childDispose,sequence=0;
    const body=el("div",{});
    const tabs=el("div",{class:"image-tabs",role:"tablist","aria-label":"Images sections"});
    async function open(name){
        shell.imageSection=name;
        const current=++sequence;childDispose?.();childDispose=null;
        [...tabs.children].forEach(b=>{const selected=b.textContent===name;b.setAttribute("aria-selected",String(selected));b.tabIndex=selected?0:-1;});
        body.setAttribute("aria-label",name);
        if(name==="Create Images"){
            let creator=shell.imageCreator;
            if(creator?.disposed)creator=null;
            const origin=creatorOrigin(shell);
            if(creator&&creator.origin!==origin){if(creator.run?.active){body.replaceChildren(hint('Wait for the current image creation to finish.'));return;}creator.dispose();creator=null;}
            if(creator&&shell.openImageId&&shell.openImageId!==creator.id){
                if(creator.run?.active){body.replaceChildren(hint('An image is generating. Return to Create Images when it finishes.'));return;}
                creator.dispose();creator=null;
            }
            if(creator)delete shell.openImageId;
            try{
                if(!creator){creator=new ImageCreator(shell);shell.imageCreator=creator;await creator.init();}
                if(disposed||current!==sequence){creator.detach();return;}
                body.replaceChildren(creator.attach());childDispose=()=>creator.detach();
            }catch(error){creator?.dispose();body.replaceChildren(el('p',{role:'alert','data-connection-error':String(error.code==='FOUNDRY_OFFLINE')},error.message));}
            return;
        }
        body.replaceChildren(hint("Loading gallery…"));
        const view=await gallery(shell);
        if(disposed||current!==sequence){view.dispose?.();return;}
        body.replaceChildren(view.element||view);childDispose=view.dispose;
        requestAnimationFrame(()=>{if(!disposed&&current===sequence)shell.content.scrollTop=shell.imageGalleryScroll||0;});
    }
    for(const name of ["Create Images","Gallery"])tabs.append(button(name,()=>open(name),{role:"tab"}));
    tabs.addEventListener("keydown",e=>{
        if(!["ArrowLeft","ArrowRight","Home","End"].includes(e.key))return;
        e.preventDefault();const next=e.key==="Home"?0:e.key==="End"?1:[...tabs.children].findIndex(b=>b.getAttribute("aria-selected")==="true")===0?1:0;
        open(tabs.children[next].textContent);tabs.children[next].focus();
    });
    body.setAttribute("role","tabpanel");
    await open(shell.imageSection||"Create Images");
    return {element:el("div",{},el("div",{class:"page-head"},el("div",{},el("span",{class:"eyebrow"},"MUMBLEBOX / IMAGE WORKSPACE"),el("h2",{},"Images"),hint("Create, capture and keep your starting images in one place."))),tabs,body),
        dispose(){disposed=true;sequence++;childDispose?.();}};
}
