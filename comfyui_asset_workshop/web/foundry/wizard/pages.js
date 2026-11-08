import {capturePhoto} from "../images/references.js";
import {el,button,hint,field} from "../dom.js";
import {dialog} from "../dialogs.js";
import {request} from "../services.js";
import {referenceFilename,clearWizardState} from "../graph-adapter.js";
import {mountMesh} from "./preview.js";
import {exportChoices,validateExports} from "./export-choices.js";

const imageUrl=name=>{const parts=name.split("/");return "/view?"+new URLSearchParams({filename:parts.pop(),subfolder:parts.join("/"),type:"input"});};
const title=id=>id.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
function set(w,key,value){w.draft.overrides[key]=value;w.remember();}
function selectedModel(w){return w.cap.turnaround_models.find(m=>m.id===w.draft.turnaround_model)||w.cap.turnaround_models[0];}
function select(w,key,label,choices,description){
    const control=el("select",{"aria-label":label,onchange:e=>set(w,key,typeof choices[0][0]==="number"?Number(e.target.value):e.target.value)},
        ...choices.map(([value,text])=>el("option",{value,selected:value===(w.draft.overrides[key]??w.cap.defaults[key])},text)));
    return field(label,control,description);
}
function number(w,key,label,description){
    const input=el("input",{type:"number",value:w.draft.overrides[key]??w.cap.defaults[key],step:key==="texture_guidance"||key==="print_height_mm"?"any":1,
        "aria-label":label,onchange:e=>set(w,key,Number(e.target.value))});
    return field(label,input,description);
}
async function upload(w,file){
    if(!file||!["image/png","image/jpeg","image/webp"].includes(file.type))throw Error("Use a PNG, JPEG or WebP image.");
    if(file.size>20*1024**2)throw Error("Use an image smaller than 20 MB.");
    const model=selectedModel(w);
    if(w.draft.references.length>=model.max_references)throw Error(model.name+" supports up to "+model.max_references+" reference images here. Choose another model or remove a reference.");
    const form=new FormData();form.append("image",file);form.append("subfolder","foundry-references");form.append("overwrite","false");
    const response=await fetch("/upload/image",{method:"POST",body:form});
    const data=await response.json();
    if(!response.ok)throw Error(data.error||"The image could not be uploaded.");
    w.draft.references.push({id:crypto.randomUUID(),filename:(data.subfolder?data.subfolder+"/":"")+data.name,
        role:w.draft.references.length?"detail":"primary",description:""});
    w.remember();
}
function camera(w){capturePhoto(w.shell,file=>w.act(()=>upload(w,file)));}
export function inputPage(w){
    const name=el("input",{value:w.draft.name,maxLength:100,placeholder:"Name this asset","aria-label":"Asset name",
        oninput:e=>{w.draft.name=e.target.value;w.remember();}});
    const category=el("select",{"aria-label":"Asset type",onchange:e=>{w.draft.category=e.target.value;w.remember();w.render();}},
        ...w.cap.categories.map(c=>el("option",{value:c.id,selected:c.id===w.draft.category,disabled:!c.qualified},
            c.name)));
    const model=selectedModel(w);
    const modelChoice=el("select",{"aria-label":"Turnaround image model",onchange:e=>{
        w.draft.turnaround_model=e.target.value;w.remember();w.render();
        w.host.querySelector('[aria-label="Turnaround image model"]')?.focus();
    }},...w.cap.turnaround_models.map(m=>el("option",{value:m.id,selected:m.id===model.id},m.name+(m.id==="qwen21"?" · Current default":""))));
    const modelPanel=el("section",{class:"model-choice"},
        field("Image model for the four views",modelChoice,"To build your initial 3D model, we first generate additional views. Choose the image model for this step. Each model's license varies."),
        el("div",{class:"model-facts"},el("span",{class:"badge"},"1–"+model.max_references+" references"),
            el("span",{class:"badge"},model.steps+" steps · CFG "+model.cfg),
            el("span",{class:"badge"},model.installed?"Installed":"Downloads on first use")),
        el("p",{class:"model-license"},el("strong",{},model.license+". "),model.license_summary," ",
            el("a",{href:model.license_url,target:"_blank",rel:"noopener noreferrer"},"Read model license")),
        w.draft.references.length>model.max_references?el("p",{role:"alert",class:"error-panel"},
            "You have "+w.draft.references.length+" references. This model accepts "+model.max_references+". Your images are preserved; remove extra cards or choose another model."):null);
    const input=el("input",{type:"file",accept:"image/png,image/jpeg,image/webp",multiple:true,hidden:true,"aria-label":"Upload reference images",
        onchange:e=>w.act(async()=>{for(const file of e.target.files)await upload(w,file);})});
    const cards=w.draft.references.map((ref,index)=>{
        const role=el("select",{"aria-label":"Reference "+(index+1)+" purpose",disabled:index===0,
            onchange:e=>{ref.role=e.target.value;w.remember();}},
            ...[["primary","Overall asset"],["back","Back of the asset"],["face","Face / identity"],["component","Component or accessory"],
                ["style","Style / material"],["detail","Other detail"]].map(([value,label])=>el("option",{value,selected:ref.role===value},label)));
        const note=el("textarea",{value:ref.description,maxLength:800,rows:2,"aria-label":"Reference "+(index+1)+" description",
            placeholder:index===0?"Optional description of the whole asset":"Describe what this image contributes",
            oninput:e=>{ref.description=e.target.value;w.remember();}});
        return el("article",{class:"reference-card"},w.image(imageUrl(ref.filename),"Reference "+(index+1)),
            el("div",{},el("strong",{},"Image "+(index+1)),field("Purpose",role),field("Reference description",note)),
            el("div",{class:"actions"},button("Remove",()=>{
                w.draft.references.splice(index,1);if(w.draft.references[0])w.draft.references[0].role="primary";w.remember();w.render();
            }),index>1?button("Move earlier",()=>{
                [w.draft.references[index-1],w.draft.references[index]]=[ref,w.draft.references[index-1]];w.remember();w.render();
            }):null));
    });
    const current=referenceFilename();
    return el("div",{},hint("Supply one clear image of the complete asset. Your chosen image model makes front, left, back and right views; Pixal3D builds the mesh, then Hi3D refines it before textures and exports."),
        el("div",{class:"wizard-columns"},field("Asset name",name,"Used in the saved output folders and package name."),
            field("What kind of asset are you making?",category,w.cap.categories.find(x=>x.id===w.draft.category)?.description)),
        el("section",{class:"image-intake"},input,
        el("div",{class:"upload-zone",ondragover:e=>{e.preventDefault();},ondrop:e=>{e.preventDefault();w.act(async()=>{for(const file of e.dataTransfer.files)await upload(w,file);});}},
            el("strong",{},"Drop reference images here"),hint("One overall image is required. Optional references can describe the back, face, accessories or materials."),
            el("div",{class:"actions"},button("Upload images",()=>input.click()),button("Take a photo with connected camera",()=>camera(w),{disabled:!navigator.mediaDevices}),
                current&&!w.draft.references.length?button("Use current graph image",()=>{
                    w.draft.references=[{id:crypto.randomUUID(),filename:current,role:"primary",description:""}];w.remember();w.render();
                }):null)),el("div",{class:"reference-list"},...cards)),
        hint("Keep the whole subject in frame with a clear silhouette. A plain background is easiest to interpret. Reference order, purposes and descriptions are sent to the selected model. Review all four generated views before continuing."),
        el("div",{class:"image-invitation"},el("strong",{},"Don't have an image?"),
            button("Create an image or scan an image with your webcam",()=>{w.remember();w.shell.imageOrigin={sessionId:w.sessionId};w.shell.openImages("Create Images");}),
            el("small",{class:"muted"},"Generate a front/back reference pair, then return here with your images.")),
        modelPanel,
        el("details",{},el("summary",{},"Advanced turnaround settings"),number(w,"turnaround_seed","Turnaround seed","Keep this fixed to compare settings. Regenerate views chooses a new seed."),
            hint("The selected model uses its own sampling defaults. The output remains a 4096 × 1024 sheet with four square panels."),
            el("a",{href:model.source,target:"_blank",rel:"noopener noreferrer"},"Model workflow guidance")),
        el("details",{},el("summary",{},"Model use and license information"),hint(w.cap.license_note)),
        w.nav({next:()=>w.start("turnaround"),note:"Clicking Next generates the four views using "+model.name+"."}));
}
export function reviewPage(w){
    const p=w.run?.previews||{};
    const ready=["front","left","back","right"].every(x=>p[x]);
    return el("div",{},hint("Check that all four views show the same asset, with the same clothing, proportions and attachments. These are the images that will go into Pixal3D."),
        ready?el("div",{class:"view-grid"},...["front","left","back","right"].map(v=>el("figure",{},w.image(p[v],title(v)+" view"),el("figcaption",{},title(v))))):hint("The four prepared images will appear here when generation finishes."),
        p.sheet?el("details",{},el("summary",{},"Turnaround sheet and source"),w.image(p.sheet,"Complete turnaround sheet"),
            w.draft.references[0]?w.image(imageUrl(w.draft.references[0].filename),"Original reference"):null):null,
        el("div",{class:"actions"},button("Regenerate views",()=>w.act(async()=>{
            w.draft.overrides.turnaround_seed=Math.floor(Math.random()*2**32);await w.start("turnaround");
        }),{disabled:!!w.run?.active}),!ready&&!w.run?.active&&w.runId?button("Retry",()=>w.act(()=>w.start("turnaround"))):null),
        w.nav({next:async()=>{if(!ready)throw Error("Wait for all four views before continuing.");w.go(3);},
            note:"Next keeps these views and opens the mesh settings. Regenerate changes only the turnaround seed."}));
}
export function optionsPage(w){
    const advanced=el("details",{},el("summary",{},"Advanced refinement settings"),
        el("div",{class:"wizard-columns"},number(w,"refine_steps","Refinement steps","Default: 25. More steps do not guarantee a better result."),
            number(w,"refine_seed","Refinement seed","Default: 42. Keep it fixed for a controlled comparison.")),
        field("CPU offloading",el("input",{type:"checkbox",checked:w.draft.overrides.cpu_offload??w.cap.defaults.cpu_offload,
            "aria-label":"CPU offloading",onchange:e=>set(w,"cpu_offload",e.target.checked)}),
            "Default: on. Moves model data to system RAM when possible. Turning it off can require substantially more GPU memory."));
    return el("div",{},hint("Pixal3D / TRELLIS.2 will construct the initial mesh from your four views. Hi3D then refines it using the matching front image, followed by measured geometry cleanup."),
        el("div",{class:"wizard-columns"},
            select(w,"shape_resolution","Initial mesh detail",[[1024,"1024 · Default"],[1536,"1536 · Experimental"],[2048,"2048 · Experimental"]],"Higher detail requires more memory and time."),
            select(w,"refine_resolution","Refinement detail",[[512,"512 · Faster"],[1024,"1024 · Intermediate"],[1536,"1536 · Default"]],"Choose more detail when the subject needs it; higher settings use more memory and time.")),
        advanced,el("div",{class:"note-panel"},hint("Recommended defaults are loaded. Your changes take priority.")),
        w.nav({next:()=>w.start("mesh"),note:"Clicking Next generates the initial mesh, refines it once with Hi3D, and cleans the geometry."}));
}
function mesh(w,key){
    const url=w.run?.previews?.[key];
    if(!url)return hint("The mesh preview will appear after this stage finishes.");
    const container=el("div",{class:"wizard-mesh",tabindex:0,role:"application","aria-label":title(key)+" mesh preview"});
    requestAnimationFrame(async()=>{
        if(!container.isConnected)return;
        try{
            const dispose=await mountMesh(container,url,w.cap.viewer_module);
            if(!container.isConnected)dispose();else w.previewDispose=dispose;
        }catch(error){container.replaceChildren(hint(error.message));}
    });
    return el("div",{},el('div',{class:'preview-tools'},hint('Drag to rotate · Scroll to zoom'),
        button('Fit view',()=>{w.previewDispose?.viewer?.fitToViewer();w.previewDispose?.viewer?.forceRender();},{title:'Fit the complete mesh in the viewer'})),container);
}
function exports(w){
    return el("div",{},exportChoices(w.cap.exports,w.draft.selection,()=>w.remember()),
        el("details",{},el("summary",{},"Advanced output settings"),el("div",{class:"wizard-columns"},
            number(w,"balanced_triangles","Balanced triangle budget","A starting budget, not a guarantee of suitability for every game."),
            number(w,"compact_triangles","Compact triangle budget","The normal map carries some of the master's surface detail."),
            number(w,"quad_count","Target quad count","Optional editable retopology. Automatic quads still need review before animation."),
            number(w,"print_height_mm","Print height in millimetres","The STL records this scale. Wall thickness, supports and fabrication need separate review."))));
}
export function finishingPage(w){
    const ready=!!w.run?.previews?.clean;
    const picker=el("select",{"aria-label":"Compare geometry",onchange:e=>{w.geometryPreview=e.target.value;w.render();}},
        ...[["clean","Cleaned refined mesh"],["refined","After Hi3D"],["decoded","Before Hi3D"]].filter(([k])=>w.run?.previews?.[k])
            .map(([value,text])=>el("option",{value,selected:value===(w.geometryPreview||"clean")},text)));
    const fields=el("fieldset",{disabled:!!w.run?.active},w.single?select(w,'export_grounding','Floor placement',[['level','Level and place on floor · Recommended'],['place','Place on floor only'],['original','Keep original orientation']],'Levels a near-upright resting pose without bending the mesh. Applied after baking to previews and exports; saved generation checkpoints stay unchanged.'):null,select(w,"texture_size","Texture size",[[1024,"1024"],[2048,"2048"],[4096,"4096 · Default"]],
        "TRELLIS.2 applies color and material maps to the final cleaned geometry. Print-only exports skip this stage."),
        el("details",{},el("summary",{},"Advanced texture settings"),el("div",{class:"wizard-columns"},
            number(w,"texture_steps","Texture steps","Default: 20."),number(w,"texture_seed","Texture seed","Default: 42."),
            number(w,"texture_guidance","Texture guidance","Default: 3.0."))),exports(w));
    const preview=el("section",{class:"review-preview"},el("h3",{},"Inspect your mesh"),
        ready?el("div",{},picker,mesh(w,w.geometryPreview||"clean")):mesh(w,"decoded"),
        !w.run?.active&&["failed","cancelled","interrupted"].includes(w.run?.status)?button("Retry mesh and refinement",()=>w.act(()=>w.start("mesh"))):null,
        ready&&w.run.geometry_audit?el("div",{class:"note-panel"},
            el("strong",{},"Cleaned mesh measurements"),
            hint(["render_vertices","faces","boundary_edges","nonmanifold_edges","watertight"].filter(k=>w.run.geometry_audit[k]!==undefined).map(k=>title(k)+": "+String(w.run.geometry_audit[k])).join(" · ")),
            hint("These checks do not establish self-intersection, wall-thickness or fabrication suitability.")):null);
    return el("div",{},el("div",{class:"review-workspace"},preview,
        ready&&!w.run?.active?el("section",{class:"review-options"},fields):hint("The initial mesh is saved before Hi3D begins. The refined, cleaned version will be shown here before texturing.")),
        w.nav({next:async()=>{if(!ready)throw Error("Finish refinement first.");validateExports(w.draft.selection);await w.start("finish");},
            note:"Clicking Next creates the selected textures, mesh versions, exports and ZIP package."}));
}
export function resultPage(w){
    const complete=!w.run?.active&&w.run?.status==="complete"&&w.run?.package;
    if(!complete)return el("div",{},hint(w.run?.status==="failed"?"Completed stages are saved. Choose how to continue above.":"Preparing your selected mesh versions and exports."),
        w.run?.previews?.texture||w.run?.previews?.clean?mesh(w,w.run.previews.texture?"texture":"clean"):null,
        !w.run?.active&&!w.error?button("Retry remaining stages",()=>w.act(()=>w.start(w.run?.operation==="rocket"?"rocket":"finish")),{class:"primary"}):null,
        el("details",{},el("summary",{},"Stage log"),el("ol",{},...(w.run?.events||[]).map(e=>el("li",{},e.text)))),
        w.nav({back:w.single?3:4}));
    const p=w.run.package;
    const selectedVariants=w.run.selection.variants;
    const options=[["texture","Detailed master","detailed"],["balanced","Balanced game mesh","game_balanced"],
        ["compact","Compact game mesh","game_compact"],["quads","Editable quad runtime preview","quad_light"],
        ["print","Print mesh (STL)","print"],["clean","Original clean geometry (before floor placement)",null]]
        .filter(([key,label,variant])=>w.run.previews[key]&&(!variant||selectedVariants[variant]));
    const selected=options.some(([k])=>k===w.finalPreview)?w.finalPreview:options[0]?.[0];
    const picker=el("select",{"aria-label":"Finished mesh version",onchange:e=>{w.finalPreview=e.target.value;w.render();}},
        ...options.map(([value,text])=>el("option",{value,selected:value===selected},text)));
    return el("div",{},resultActions(w,"top"),el("div",{class:"complete-panel"},el("h3",{},w.run.name+" is ready"),
        hint(p.selected_variants.map(title).join(" · ")+" · "+p.file_count+" files · "+(p.bytes/1024**2).toFixed(1)+" MB")),
        picker,w.run.package.grounding?hint('Floor placement: '+(w.run.package.grounding.applied==='level'?'leveled '+w.run.package.grounding.correction_degrees.toFixed(1)+'°':w.run.package.grounding.applied==='place'?'placed on floor':'original orientation')+'. Saved generation checkpoints are unchanged.'):null,mesh(w,selected),measurements(w),el("div",{class:"actions"},
            el("a",{href:p.download,download:"",class:"download-link primary"},"Download ZIP"),
            button("Open Output Folder",()=>w.act(()=>request("wizard/runs/"+w.runId+"/open-folder",{})))),
        ...(p.warnings||[]).map(text=>el("p",{class:"note-panel"},text)),
        hint(w.run.cleanup?.status==="released"?"Loaded models and reusable execution memory were released. Saved previews, masters and exports are retained.":"Package saved. Memory release status: "+(w.run.cleanup?.status||"finishing")),
        resultActions(w,"bottom"));
}

function resultActions(w,position){
    return el("nav",{class:"actions result-actions","aria-label":"Finished asset actions "+position},
        button("Make a new asset",()=>w.shell.openWizard({method:w.method}),{class:"primary"}),
        button("Back to export choices",()=>w.go(w.single?3:4)),
        button("Choose another workflow",()=>w.shell.open("Choose a Workflow")));
}

export function measurements(w){
    const cards=Object.entries(w.run.measurements||{}).map(([id,v])=>{
        const m=v.measurements;const stats=[];
        for(const [group,data] of Object.entries(m)){
            if(!data||typeof data!=="object"||Array.isArray(data))continue;
            for(const key of ["vertices","triangles","quads","polygons","dimensions","units","boundary_edges","nonmanifold_edges","watertight"]){
                if(data[key]===undefined||key==='quads'&&w.showQuads===false)continue;
                const value=Array.isArray(data[key])?data[key].map(x=>Number(x).toPrecision(4)).join(" × "):typeof data[key]==="number"?data[key].toLocaleString():String(data[key]);
                stats.push(el("div",{},el("dt",{},title(group)+" · "+title(key)),el("dd",{},value)));
            }
        }
        return el("section",{class:"export-option"},el("h3",{},v.directory),el("dl",{class:"asset-stats"},...stats));
    });
    return el("div",{class:"export-grid"},...cards);
}
