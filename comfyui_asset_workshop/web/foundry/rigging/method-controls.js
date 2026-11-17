import {button,el,field,hint} from "../dom.js";
import {setText} from "../i18n.js";
import {rigText as t} from "./entry.js";

export class RigPresets {
    constructor(label, schema, selected="standard", values={}) {
        this.schema=schema;
        this.inputs=Object.fromEntries(Object.entries(schema.fields).map(([key,limits])=>
            [key,el("input",{type:"number",min:limits.min,max:limits.max,step:limits.step,
                value:limits.default,"aria-label":t("field_"+key)})]));
        this.select=el("select",{"aria-label":t(label),onchange:()=>this.selectPreset(this.select.value)},
            ...[...Object.keys(schema.presets),"custom"].map(key=>el("option",{value:key},t("preset_"+key))));
        this.summary=el("p",{class:"rig-preset-summary"});
        this.custom=el("div",{class:"rig-custom-fields"},...Object.entries(this.inputs).map(([key,input])=>
            field(t("field_"+key),input,t("help_"+key))),
            button(t("reset_preset"),()=>this.selectPreset(this.previous||"standard")));
        this.element=el("fieldset",{class:"rig-presets","aria-label":t(label)},field(t(label),this.select),this.summary,this.custom);
        this.selectPreset(selected,values);
    }

    selectPreset(key, values={}) {
        this.select.value=key;
        this.custom.hidden=key!=="custom";
        const preset=this.schema.presets[key];
        if(preset)this.previous=key;
        for(const [name,input] of Object.entries(this.inputs)){
            if(preset||name in values)input.value=values[name]??preset[name];
        }
        const primary=Object.keys(this.inputs)[0];
        setText(this.summary,preset?t("summary_"+primary,{value:preset[primary]}):t("preset_custom_hint"));
    }

    payload() {
        const preset=this.select.value;
        const custom=preset==="custom"?Object.fromEntries(Object.entries(this.inputs).map(([key,input])=>{
            if(!input.value||!input.validity.valid)throw Error(String(t("invalid_custom")));
            return [key,input.valueAsNumber];
        })):{};
        return {preset,custom};
    }
}

export function setupHint(status) {
    if(!status.supported_platform)return hint(t("ai_unavailable"));
    if(status.setup_ready)return hint(t("ai_ready"));
    return hint(t("ai_setup",{gb:(status.known_download_bytes/1e9).toFixed(2)}));
}
