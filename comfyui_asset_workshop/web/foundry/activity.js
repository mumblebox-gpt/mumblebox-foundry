import {bindAttribute} from "./i18n.js";
import {msg, setText} from "./i18n.js";
import {el} from "./dom.js";

export function workingStar(size=32) {
    return el("img",{class:"working-star",width:size,height:size,
        src:new URL("../assets/foundry-chaos-star.svg",import.meta.url).href,alt:""});
}

class FoundryElapsed extends HTMLElement {
    connectedCallback() {
        const render = () => {
            const seconds = Math.max(0, Math.floor((Date.now() - this.startedAt) / 1000));
            setText(this, msg("common.elapsed_time_m_s", {value1: Math.floor(seconds / 60), value2: seconds % 60}));
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
        setText(label, state.label);setText(detail, state.detail||"");detail.hidden=!state.detail;
        progress.hidden=!state.busy||state.fraction==null;
        if(state.fraction!=null) {progress.value=state.fraction;bindAttribute(progress, "aria-label", state.label);}
    }};
}
