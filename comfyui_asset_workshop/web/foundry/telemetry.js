import {msg, setText, bindAttribute} from "./i18n.js";
import {el,bytes} from "./dom.js";
import {utilization} from "./activity-state.js";

export function resourceMeter(label,{percent=false}={}) {
    const value=el("span",{class:"meter-value"}),dots=Array.from({length:12},()=>el("i"));
    const bar=el("span",{class:"meter-dots","aria-hidden":"true"},dots);
    const element=el("div",{class:"resource-meter"},el("div",{class:"meter-caption"},el("strong",{},label),value),bar);
    return {element,update(used,total) {
        const fraction=utilization(used,total);
        setText(value, fraction==null?msg("common.unavailable"):percent?Math.round(fraction*100)+"%":bytes(used)+" / "+bytes(total));
        element.dataset.level=fraction==null?"unknown":fraction>=.9?"high":fraction>=.75?"elevated":"normal";
        bindAttribute(element, "title", fraction==null?msg("common.reading_unavailable", {label: label}):msg("common.used", {label: label, value2: Math.round(fraction*100)}));
        dots.forEach((dot,i)=>dot.dataset.lit=String(fraction!=null && i<Math.ceil(fraction*dots.length)));
    }};
}
