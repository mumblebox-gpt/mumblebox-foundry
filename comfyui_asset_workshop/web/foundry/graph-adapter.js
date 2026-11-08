import {app} from "/scripts/app.js";
import {appMode,presentation,launchMessage} from "./app-mode.js";
import {hasWork,retainSession} from "./wizard/session.js";
import {syncTurnaroundBranch} from "./turnaround-graph.js";
export const NODE_TYPE = "MumbleboxFoundry/Interface";
let returnControl;
function referenceNode() {
    const id = app.graph.extra?.mumblebox_foundry?.reference_node_id;
    return id === undefined ? null : app.graph.getNodeById(id);
}
export function referenceImage() {
    const node = referenceNode();
    const value = node?.widgets?.find(w => w.name === "image")?.value;
    if (!value || typeof value !== "string") return null;
    const clean = value.replace(/ \[(input|output|temp)\]$/, "");
    const parts = clean.split("/");
    return "/view?" + new URLSearchParams({filename:parts.pop(),subfolder:parts.join("/"),type:"input"});
}
function frame(bounds) {
    const rect = app.canvas.canvas.getBoundingClientRect();
    app.canvas.animateToBounds(bounds, {duration:180,zoom:0.97,
        viewport:[85,195,Math.max(480,rect.width-525),Math.max(350,rect.height-255)]});
    app.canvas.setDirty(true,true);
}
export function showInterface(node) { if(appMode&&presentation.show(node)){launchMessage("ready");return;} frame([node.pos[0],node.pos[1]-30,node.size[0],node.size[1]+40]); }
export function showWorkflow(node) {
    if(appMode)presentation.graph();
    const input = referenceNode();
    if (input) frame([input.pos[0]-60,input.pos[1]-80,1900,1150]);
    else {
        const other = app.graph._nodes.find(n => n.id !== node.id);
        if (other) frame([other.pos[0],other.pos[1],1600,1100]);
    }
}
export function showHairWorkflow() {
    if(appMode)presentation.graph();
    const node=app.graph.getNodeById(70000);
    if(node)frame([node.pos[0]-60,node.pos[1]-90,2500,1200]);
}
export function installReturnControl(node) {
    returnControl?.remove();
    const control = document.createElement("button");
    control.textContent = "Return to Foundry";
    control.type = "button";
    control.style.cssText = "position:fixed;left:84px;bottom:20px;z-index:130;background:#1f2d26;color:#fff;border:1px solid #9aaf9b;border-radius:8px;padding:12px 18px;font:14px 'Segoe UI',sans-serif;cursor:pointer";
    control.onclick = () => showInterface(node);
    document.body.append(control);
    returnControl = control;
    return () => { control.remove(); if (returnControl === control) returnControl = null; };
}


export function referenceFilename(){
    const value=referenceNode()?.widgets?.find(w=>w.name==="image")?.value;
    return typeof value==="string"&&!/\[(output|temp)\]$/.test(value)?value.replace(/ \[input\]$/,""):null;
}
export function syncWizardGraph(run,interfaceNode,branch){
    const set=(id,name,value)=>{
        const node=app.graph.getNodeById(id);
        const widget=node?.widgets?.find(w=>w.name===name);
        if(widget&&value!==undefined){widget.value=value;widget.callback?.(value);}
    };
    if(interfaceNode.graph!==app.graph)throw Error("Open the Foundry workflow before starting this stage.");
    if(branch)syncTurnaroundBranch(branch,interfaceNode);
    const s=run.settings;
    set(900,"image",run.references[0].filename);
    set(1574,"prompt",run.reference_prompt);set(1574,"text",run.reference_prompt);
    set(1558,"seed",s.turnaround_seed);set(94,"target_resolution",s.shape_resolution);
    for(const [field,key] of [["resolution","refine_resolution"],["steps","refine_steps"],["seed","refine_seed"],["cpu_offload","cpu_offload"],["attention","attention"]])set(2003,field,s[key]);
    for(const [field,key] of [["seed","texture_seed"],["steps","texture_steps"],["texture_size","texture_size"],["guidance","texture_guidance"]])set(2023,field,s[key]);
    set(2030,"target_triangles",s.balanced_triangles);set(2040,"target_triangles",s.compact_triangles);
    set(3001,"target_quads",s.quad_count);set(2050,"height_mm",s.print_height_mm);
    for(const id of [2030,2040,3001])set(id,"texture_size",s.texture_size);
    for(const id of [2031,2041])set(id,"resolution",s.texture_size);
    set(3010,"asset_name",run.name);set(3010,"selection_json",JSON.stringify(run.selection));
    app.graph.extra??={};app.graph.extra.foundry_run={id:run.id,name:run.name,version:run.version};
    app.graph.setDirtyCanvas(true,true);app.graph.change?.();
}
export function syncWizardOutputs(outputs,interfaceNode){
    if(!outputs||interfaceNode?.graph!==app.graph)return;
    for(const [id,output] of Object.entries(outputs)){
        const node=app.graph.getNodeById(Number(id));
        if(!node)continue;
        const value=structuredClone(output);
        app.nodeOutputs[id]=value;
        node.onExecuted?.(value);
    }
    app.graph.setDirtyCanvas(true,true);
}

export function wizardStateKey(){
    return "mumblebox-foundry/wizard/"+(app.extensionManager.workflow.activeWorkflow?.path||"unsaved");
}
export function clearWizardState(node){
    rememberPreviousSession(node);
    node.properties.foundryWizard=null;
    localStorage.removeItem(wizardStateKey());
    app.graph.change?.();
}
export function savedSingleWizardState(node){
    let saved=node.properties.foundrySingle;
    try{saved=JSON.parse(localStorage.getItem(wizardStateKey()+':single'))||saved;}catch{}
    return saved||null;
}
export function savedWizardState(node){
    let saved=node.properties.foundryWizard;
    try{saved=JSON.parse(localStorage.getItem(wizardStateKey()))||saved;}catch{}
    if(hasWork(saved))return saved;
    let recent=node.properties.foundryRecentSessions||[];
    try{recent=JSON.parse(localStorage.getItem(wizardStateKey()+"/recent"))||recent;}catch{}
    return recent.find(hasWork)||null;
}
export function rememberPreviousSession(node){
    const saved=savedWizardState(node);
    let recent=node.properties.foundryRecentSessions||[];
    try{recent=JSON.parse(localStorage.getItem(wizardStateKey()+"/recent"))||recent;}catch{}
    recent=retainSession(recent,saved);
    node.properties.foundryRecentSessions=recent;
    localStorage.setItem(wizardStateKey()+"/recent",JSON.stringify(recent));
}
