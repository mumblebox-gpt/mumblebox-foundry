import {bindAttribute} from "./i18n.js";
import {msg} from "./i18n.js";
/** Opt-in application presentation. The graph node and shell remain the sole owners. */
export function createAppPresentation(doc=document) {
    let current=null,container=null,anchor=null,previousStyle="",hidden=[];
    function graph() {
        if(!container)return;
        if(anchor?.parentNode)anchor.parentNode.insertBefore(current.shell.host,anchor);
        current.shell.host.style.cssText=previousStyle;
        anchor?.remove();anchor=null;
        for(const [element,inert,aria] of hidden){
            element.inert=inert;
            if(aria===null)element.removeAttribute("aria-hidden");else element.setAttribute("aria-hidden",aria);
        }
        hidden=[];container.remove();container=null;current=null;
    }
    function show(node) {
        if(current===node&&container?.isConnected)return true;
        graph();
        const host=node?.shell?.host;
        if(!host?.isConnected)return false;
        current=node;previousStyle=host.style.cssText;
        anchor=doc.createComment("Foundry graph widget position");host.before(anchor);
        container=doc.createElement("main");container.id="mumblebox-foundry-app";
        bindAttribute(container, "aria-label", msg("common.mumblebox_3d_asset_foundry"));
        container.style.cssText="position:fixed;inset:0;z-index:2147483000;background:#11150f;overflow:hidden";
        for(const element of doc.body.children){
            hidden.push([element,element.inert,element.getAttribute("aria-hidden")]);
            element.inert=true;element.setAttribute("aria-hidden","true");
        }
        host.style.cssText="width:100%;height:100%;min-height:0;overflow:hidden";
        container.append(host);doc.body.append(container);
        return true;
    }
    return {show,graph,release(node){if(current===node)graph();},get current(){return current;}};
}

export function isAppMode(currentLocation, browserWindow) {
    if (!currentLocation) return false;
    if (new URLSearchParams(currentLocation.search).get("foundry-app")==="1") return true;
    // Comfy's router removes query parameters. The dedicated same-origin host
    // remains the authority across refreshes; ordinary graph tabs stay unchanged.
    try {
        return browserWindow?.parent!==browserWindow &&
            browserWindow.parent.location.origin===currentLocation.origin &&
            browserWindow.parent.location.pathname==="/mumblebox-foundry/";
    } catch { return false; }
}
export const appMode = isAppMode(typeof location!=="undefined"?location:null,typeof window!=="undefined"?window:null);
export const presentation = typeof document!=="undefined" ? createAppPresentation() : null;

export function launchMessage(type,message=""){
    if(appMode&&window.parent!==window)window.parent.postMessage({source:"mumblebox-foundry",type,message},location.origin);
}
