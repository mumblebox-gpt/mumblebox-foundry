import {el} from "./dom.js";

export function workingStar(size=32) {
    return el("img",{class:"working-star",width:size,height:size,
        src:new URL("../assets/foundry-chaos-star.svg",import.meta.url).href,alt:""});
}

class FoundryElapsed extends HTMLElement {
    connectedCallback() {
        const render = () => {
            const seconds = Math.max(0, Math.floor((Date.now() - this.startedAt) / 1000));
            this.textContent = 'Elapsed time · ' + Math.floor(seconds / 60) + 'm ' + (seconds % 60) + 's';
        };
        render();
        this.tick = setInterval(render, 1000);
    }

    disconnectedCallback() {
        clearInterval(this.tick);
    }
}

if (!customElements.get('foundry-elapsed')) customElements.define('foundry-elapsed', FoundryElapsed);

export function elapsedTime(startedAt) {
    if (!Number.isFinite(startedAt) || startedAt <= 0) return null;
    const element = el('foundry-elapsed', {class: 'muted', role: 'timer'});
    element.startedAt = startedAt;
    return element;
}

export function activity() {
    const label=el("strong"),detail=el("span",{class:"muted"}),progress=el("progress",{max:1,hidden:true});
    const element=el("div",{class:"activity-feedback",role:"status","aria-live":"polite"},workingStar(),el("div",{},label,detail,progress));
    return {element,update(state) {
        element.dataset.busy=String(state.busy);element.dataset.error=String(!!state.error);
        label.textContent=state.label;detail.textContent=state.detail||"";detail.hidden=!state.detail;
        progress.hidden=!state.busy||state.fraction==null;
        if(state.fraction!=null) {progress.value=state.fraction;progress.setAttribute("aria-label",state.label);}
    }};
}
