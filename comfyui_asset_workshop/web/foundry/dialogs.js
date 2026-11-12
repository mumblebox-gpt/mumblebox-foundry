import {sourceMessage} from "./i18n.js";
import {msg} from "./i18n.js";
import {el, button} from "./dom.js";

export function dialog(shell, title, content, actions = []) {
    shell.activeDialog?.close();
    const previous = shell.shadow.activeElement;
    const surface = el("section", {class:"dialog", role:"dialog", "aria-modal":"true", "aria-label":title, tabindex:-1},
        el("div", {class:"dialog-title"}, el("h2", {}, title), button(msg("common.close"), () => close(), {"aria-label":msg("common.close_2", {title: title})})),
        el("div", {class:"dialog-content"}, content));
    const footer = el("div", {class:"dialog-actions"});
    const overlay = el("div", {class:"dialog-overlay"}, surface);
    // The Comfy canvas can scale/pan this node beyond the browser viewport.
    // Keep modal controls inside the visible part of the existing node.
    function fitViewport() {
        const bounds=shell.root.getBoundingClientRect();
        const scale=bounds.width/shell.root.offsetWidth || 1;
        const left=Math.max(bounds.left,12), top=Math.max(bounds.top,12);
        const right=Math.min(bounds.right,window.innerWidth-12);
        const bottom=Math.min(bounds.bottom,window.innerHeight-12);
        if(right<=left || bottom<=top)return;
        Object.assign(overlay.style,{inset:"auto",left:(left-bounds.left)/scale+"px",
            top:(top-bounds.top)/scale+"px",width:(right-left)/scale+"px",
            height:(bottom-top)/scale+"px",padding:"12px"});
    }
    let fitTimer;
    function close() {
        clearInterval(fitTimer);
        window.removeEventListener("resize",fitViewport);
        surface.dispatchEvent(new Event("foundry-close"));
        overlay.remove();
        shell.activeDialog = null;
        previous?.focus({preventScroll:true});
    }
    for (const action of actions) footer.append(button(action.label, async event => {
        const control = event.currentTarget;
        control.disabled = true;
        try { await action.run(close); }
        catch (error) { shell.message(sourceMessage(error.message), true); }
        finally { control.disabled = false; }
    }, {class:action.primary ? "primary" : ""}));
    if (actions.length) surface.append(footer);
    overlay.addEventListener("keydown", event => {
        if (event.key === "Escape") { event.preventDefault(); close(); }
        if (event.key !== "Tab") return;
        const controls = [...surface.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,a[href],[tabindex="0"]')]
            .filter(control => control.getClientRects().length);
        if (!controls.length) return;
        const index = controls.indexOf(shell.shadow.activeElement);
        if (event.shiftKey && index <= 0) { event.preventDefault(); controls.at(-1).focus(); }
        else if (!event.shiftKey && index === controls.length-1) { event.preventDefault(); controls[0].focus(); }
    });
    shell.root.append(overlay);
    fitViewport();
    fitTimer=setInterval(fitViewport,250);
    window.addEventListener("resize",fitViewport);
    shell.activeDialog = {close};
    surface.focus({preventScroll:true});
    return {close, surface};
}
