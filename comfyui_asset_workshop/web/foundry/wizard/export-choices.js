import {el,button,hint} from "../dom.js";

const title=id=>id.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
export function validateExports(selection) {
    const variants=Object.values(selection.variants||{});
    if(!variants.length)throw Error("Choose at least one output version.");
    if(variants.some(v=>!v.formats?.length))throw Error("Choose at least one file format for each selected version.");
}

// One selector for guided finishing and Rocket confirmation. Changes stay with the
// supplied draft; a modal can pass a copy so Cancel never changes the wizard.
export function exportChoices(capabilities,selection,onChange=()=>{}) {
    const root=el("section",{class:"export-choices"});
    function changed(){onChange(selection);render();}
    function render(){
        const selected=selection.variants;
        const versions=Object.keys(selected).length, formats=Object.values(selected).reduce((sum,v)=>sum+v.formats.length,0);
        const cards=capabilities.map(variant=>{
            const enabled=!!selected[variant.id];
            const toggle=el("input",{type:"checkbox",checked:enabled,"aria-label":"Include "+title(variant.id),onchange:e=>{
                if(e.target.checked)selected[variant.id]={formats:[variant.formats[0]]};else delete selected[variant.id];changed();
            }});
            return el("section",{class:"export-option"},el("label",{class:"export-title"},toggle,title(variant.id)),hint(variant.description),
                variant.id==="quad_light"?hint("QuadriFlow uses the CPU. High CPU use and spikes are normal. Retopology can take several minutes."):null,
                el("div",{class:"format-options"},...variant.formats.map(format=>el("label",{class:"format-check"},
                    el("input",{type:"checkbox",checked:selected[variant.id]?.formats.includes(format)||false,disabled:!enabled,
                        "aria-label":title(variant.id)+" "+format.toUpperCase(),onchange:e=>{
                            const formats=selected[variant.id].formats;
                            selected[variant.id].formats=e.target.checked?[...new Set([...formats,format])]:formats.filter(f=>f!==format);changed();
                        }}),format.replaceAll("_"," ").toUpperCase()))));
        });
        const focused=root.getRootNode().activeElement?.getAttribute?.("aria-label");
        root.replaceChildren(el("h3",{},"Output versions & formats"),
            hint("Only selected versions are generated. The ZIP includes measurements, a README and model credits."),
            el("div",{class:"export-summary",role:"status"},`${versions} version${versions===1?"":"s"} · ${formats} format selection${formats===1?"":"s"}`),
            el("div",{class:"actions"},button("Select all",()=>{selection.variants=Object.fromEntries(capabilities.map(v=>[v.id,{formats:[...v.formats]}]));changed();}),
                button("Clear",()=>{selection.variants={};changed();})),el("div",{class:"export-grid"},...cards));
        if(focused)[...root.querySelectorAll("[aria-label]")].find(n=>n.getAttribute("aria-label")===focused)?.focus({preventScroll:true});
    }
    render();return root;
}
