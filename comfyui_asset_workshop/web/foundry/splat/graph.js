import {sourceText} from "../i18n.js";
import {msg} from "../i18n.js";
import {app} from '/scripts/app.js';
import {appMode,presentation} from '../app-mode.js';

export function syncSplatGraph(recipe,owner){
    if(owner.graph!==app.graph)throw Error(msg("splat.open_the_foundry_graph_before_continuing"));
    const graph=app.graph;graph.beforeChange();
    try{
    graph.extra??={};
    const origin=graph.extra.splatOrigin??=[Math.max(0,...graph._nodes.filter(n=>!n.properties?.splatOwner).map(n=>n.pos[0]+n.size[0]))+700,100];
    const made=new Map();
    const noteId=400100;
    let note=graph.getNodeById(noteId);
    if(note&&note.properties?.splatOwner!==owner.id)throw Error(msg("splat.another_workflow_owns_the_splat_solid_notes"));
    if(!note){note=LiteGraph.createNode('MarkdownNote');if(note){note.id=noteId;graph.add(note);}}
    if(note){
        note.title=sourceText(msg("splat.splat_solid_original_research_and_workflow"));note.properties.splatOwner=owner.id;note.properties.splatStage='generation';note.mode=2;
        const text='## Splat & Solid\n\n**Idol by Sperid Labs**, native ComfyUI integration by Comfy-Org and contributors. Optional image-guided refinement: **Hi3D**. Native mesh cleanup/rendering: **ComfyUI**; independent exported-file checks: **PyMeshLab and trimesh**. DINOv3, FLUX.2 autoencoder and BiRefNet retain their original credits and terms.\n\nOne image → splat + original mesh → optional refinement → closed master + lightweight companion. Appearance lives in the splat; the companion is separate geometry in its frame. Thin features may be lost. Closed geometry does not certify engine collision or physical printing.\n\nThis branch is independent of Turnaround, 3D-Guided and HairDeck. The wizard queues only its selected stage; nodes stay disabled for the global Run button. Saved loaders resume completed stages. Original files are preserved.\n\nhttps://huggingface.co/speridlabs/idol\nhttps://github.com/Comfy-Org/ComfyUI\nhttps://github.com/hi3d-official/Hi3Dv1.0';
        if(note.widgets?.[0])note.widgets[0].value=text;
    }
    if(Object.values(recipe).some(item=>item.class_type==='VAEDecodeTripoSplat')){
        for(const n of [...graph._nodes]){
            if(n.id!==noteId&&n.properties?.splatOwner===owner.id&&n.properties.splatStage==='generation'&&!Object.hasOwn(recipe,n.id)){
                graph.remove(n);
            }
        }
    }
    for(const [id,item] of Object.entries(recipe)){
        let n=graph.getNodeById(+id);
        if(n&&n.properties?.splatOwner!==owner.id)throw Error(msg("splat.another_workflow_owns_node", {id: id}));
        if(!n){n=LiteGraph.createNode(item.class_type);if(!n)throw Error(msg("splat.required_native_node_is_missing", {value1: item.class_type}));n.id=+id;graph.add(n);}
        n.properties.splatOwner=owner.id;n.properties.splatStage=item._meta?.splat_stage||'processing';n.mode=2;n.title=sourceText(item._meta?.title||'Splat & Solid · '+item.class_type);
        for(const [name,value] of Object.entries(item.inputs))if(!Array.isArray(value)){
            const w=n.widgets?.find(w=>w.name===name);if(w){w.value=value;w.callback?.(value);}
        }
        const seedMode=n.widgets?.find(w=>w.name==='control_after_generate');if(seedMode)seedMode.value='fixed';
        made.set(id,n);
    }
    for(const [id,item] of Object.entries(recipe))for(const [name,value] of Object.entries(item.inputs)){
        if(!Array.isArray(value)||value.length!==2)continue;
        const n=made.get(id),source=made.get(String(value[0]));if(!source)throw Error(msg("splat.missing_splat_branch_connection"));
        let slot=n.inputs.findIndex(i=>i.name===name);
        if(slot<0){n.addInput(name,source.outputs[value[1]]?.type||'*');slot=n.inputs.length-1;}
        source.connect(value[1],n,slot);
    }
    for(const group of [...graph._groups])if(group.title.startsWith('Splat & Solid / '))graph.remove(group);
    let y=origin[1];
    for(const stage of ['generation','refinement','cleanup']){
        const nodes=graph._nodes.filter(n=>n.properties?.splatOwner===owner.id&&n.properties.splatStage===stage);
        if(!nodes.length)continue;
        nodes.forEach((n,i)=>{n.pos=[origin[0]+i%4*480,y+65+Math.floor(i/4)*460];n.size=[440,400];n.onResize?.(n.size);});
        const group=new LiteGraph.LGraphGroup('Splat & Solid / '+stage);group.pos=[origin[0]-25,y];group.size=[1950,Math.ceil(nodes.length/4)*460+80];group.color='#496d65';graph.add(group);y+=group.size[1]+100;
    }
    graph.extra.splat_method={method:'splat-solid/v1',owner:owner.id};graph.change?.();graph.setDirtyCanvas(true,true);
    }finally{graph.afterChange();}
}
export function syncSplatOutputs(outputs,owner){
    if(owner.graph!==app.graph)return;
    for(const [id,value] of Object.entries(outputs||{})){
        const n=app.graph.getNodeById(+id);if(n?.properties?.splatOwner!==owner.id)continue;
        if(JSON.stringify(app.nodeOutputs[id])===JSON.stringify(value))continue;
        const copy=JSON.parse(JSON.stringify(value));app.nodeOutputs[id]=copy;n.onExecuted?.(copy);
    }
}
export function showSplatWorkflow(){
    if(appMode)presentation.graph();
    const n=app.graph._nodes.find(n=>n.properties?.splatOwner);
    if(n)app.canvas.animateToBounds([n.pos[0]-50,n.pos[1]-70,1950,1150],{duration:180,zoom:.8});
}
