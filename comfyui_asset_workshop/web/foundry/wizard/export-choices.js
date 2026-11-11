import {msg, replaceContent} from "../i18n.js";
import {el,button,field,hint} from "../dom.js";

const title=id=>id.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
export function validateExports(selection, quad) {
    const variants=Object.values(selection.variants||{});
    if(!variants.length)throw Error(msg("mesh.choose_at_least_one_output_version"));
    if(variants.some(v=>!v.formats?.length))throw Error(msg("mesh.choose_at_least_one_file_format_for_each_selected_version"));
    if(selection.variants?.quad_light&&quad){
        const method=quad.methods.find(item=>item.id===quad.value);
        if(!method?.available)throw Error(method?.reason||"Choose an available quad solver.");
    }
}

function advancedQuadControls(quad, open) {
    const groups=[["shared",msg("mesh.guide_and_baking")],[quad.value,"Selected solver"]];
    const sections=groups.map(([group,label])=>{
        const controls=Object.entries(quad.controls[group]||{});
        if(!controls.length)return null;
        return el("fieldset",{},el("legend",{},label),...controls.map(([id,spec])=>{
            const previous=()=>quad.getOption(group,id,spec.default);
            const name=quad.name+"-"+group+"-"+id;
            const labelId=name+"-help";
            const save=e=>{
                const input=e.currentTarget;
                if(input.type==="number"&&(!input.value||!input.checkValidity())){
                    input.reportValidity();
                    input.value=previous();
                    return;
                }
                const value=input.type==="checkbox"?input.checked:input.type==="number"?input.valueAsNumber:input.value;
                quad.setOption(group,id,value);
            };
            const attrs={"aria-label":spec.label,"aria-describedby":labelId,onchange:save};
            const description=el("small",{id:labelId,class:"muted"},spec.description);
            if(typeof spec.default==="boolean"){
                return el("div",{class:"quad-advanced-control"},
                    el("label",{class:"format-check"},el("input",{...attrs,type:"checkbox",checked:previous()}),spec.label),description);
            }
            const input=spec.choices
                ? el("select",attrs,...Object.entries(spec.choices).map(([value,text])=>el("option",{value,selected:value===previous()},text)))
                : el("input",{...attrs,type:"number",value:previous(),min:spec.min,max:spec.max,step:spec.step,required:true});
            return el("div",{class:"quad-advanced-control"},field(spec.label,input),description);
        }));
    });
    return sections.some(Boolean)
        ? el("details",{class:"quad-advanced",open},el("summary",{},msg("mesh.advanced_quad_settings")),...sections)
        : null;
}

// One selector for guided finishing and Rocket confirmation. Changes stay with the
// supplied draft; a modal can pass a copy so Cancel never changes the wizard.
export function exportChoices(capabilities,selection,onChange=()=>{},quad=null) {
    const root=el("section",{class:"export-choices"});
    function changed(){onChange(selection);render();}
    function render(){
        const advancedOpen=root.querySelector(".quad-advanced")?.open||false;
        const selected=selection.variants;
        const versions=Object.keys(selected).length, formats=Object.values(selected).reduce((sum,v)=>sum+v.formats.length,0);
        const cards=capabilities.map(variant=>{
            const enabled=!!selected[variant.id];
            const toggle=el("input",{type:"checkbox",checked:enabled,"aria-label":msg("mesh.include", {value1: title(variant.id)}),onchange:e=>{
                if(e.target.checked)selected[variant.id]={formats:[variant.formats[0]]};else delete selected[variant.id];changed();
            }});
            return el("section",{class:"export-option"},el("label",{class:"export-title"},toggle,title(variant.id)),hint(variant.description),
                variant.id==="quad_light"&&enabled&&quad?el("fieldset",{class:"quad-solver-choices"},
                    el("legend",{},msg("mesh.quad_solver")),
                    ...quad.methods.map(method=>el("div",{},
                        el("label",{class:"format-check"},
                            el("input",{type:"radio",name:quad.name,checked:quad.value===method.id,
                                disabled:!method.available,"aria-label":method.label+" · "+method.device,onchange:()=>{
                                    quad.value=method.id;quad.change(method.id);render();
                                }}),method.label+" · "+method.device+(method.recommended?" · Default":"")),
                        hint(method.available?method.description:method.reason))),
                    advancedQuadControls(quad,advancedOpen)):null,
                el("div",{class:"format-options"},...variant.formats.map(format=>el("label",{class:"format-check"},
                    el("input",{type:"checkbox",checked:selected[variant.id]?.formats.includes(format)||false,disabled:!enabled,
                        "aria-label":title(variant.id)+" "+format.toUpperCase(),onchange:e=>{
                            const formats=selected[variant.id].formats;
                            selected[variant.id].formats=e.target.checked?[...new Set([...formats,format])]:formats.filter(f=>f!==format);changed();
                        }}),format.replaceAll("_"," ").toUpperCase()))));
        });
        const focused=root.getRootNode().activeElement?.getAttribute?.("aria-label");
        replaceContent(root, el("h3",{},msg("mesh.output_versions_formats")), hint(msg("mesh.only_selected_versions_are_generated_the_zip_includes_measurements_a_readme")), el("div",{class:"export-summary",role:"status"},msg("mesh.output_selection_summary", {versions: msg(versions === 1 ? "mesh.version_count" : "mesh.version_count_plural", {count: versions}), formats: msg(formats === 1 ? "mesh.format_count" : "mesh.format_count_plural", {count: formats})})), el("div",{class:"actions"},button(msg("mesh.select_all"),()=>{selection.variants=Object.fromEntries(capabilities.map(v=>[v.id,{formats:[...v.formats]}]));changed();}),
                button(msg("mesh.clear"),()=>{selection.variants={};changed();})), el("div",{class:"export-grid"},...cards));
        if(focused)[...root.querySelectorAll("[aria-label]")].find(n=>n.getAttribute("aria-label")===focused)?.focus({preventScroll:true});
    }
    render();return root;
}
