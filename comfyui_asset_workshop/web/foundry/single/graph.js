import {sourceText} from "../i18n.js";
import {msg} from "../i18n.js";
import {app} from '/scripts/app.js';
const OFFSET=500000;
// Independent ownership: no edits to the Turnaround, Guided, Splat or Hair branches.
export function syncSingleGraph(recipe,owner,run=null){
    if(owner.graph!==app.graph)throw Error(msg("mesh.open_the_foundry_graph_before_continuing"));
    const graph=app.graph;graph.extra??={};
    const origin=graph.extra.single_origin??=[Math.max(0,...graph._nodes.map(n=>n.pos[0]+n.size[0]))+900,100];
    const made=new Map(),fresh=[];
    for(const [id,definition] of Object.entries(recipe)){
        const nativeId=Number(id)+OFFSET;let n=graph.getNodeById(nativeId);
        if(n&&n.properties?.singleOwner!==owner.id)throw Error(msg("mesh.another_method_owns_node", {nativeId: nativeId}));
        if(!n){n=LiteGraph.createNode(definition.class_type);if(!n)throw Error(msg("mesh.required_node_missing", {value1: definition.class_type}));n.id=nativeId;graph.add(n);fresh.push(n);}
        n.properties.singleOwner=owner.id;n.properties.singleStage=definition._meta?.single_stage||'processing';n.mode=2;
        n.title=sourceText(msg("mesh.single_image", {value1: definition._meta?.title||definition.class_type}));
        for(const [name,value] of Object.entries(definition.inputs||{}))if(!Array.isArray(value)){
            const widget=n.widgets?.find(w=>w.name===name);if(widget){widget.value=value;widget.callback?.(value);}
        }
        const fixed=n.widgets?.find(w=>w.name==='control_after_generate');if(fixed)fixed.value='fixed';made.set(id,n);
    }
    for(const [id,d] of Object.entries(recipe))for(const [name,v] of Object.entries(d.inputs||{}))if(Array.isArray(v)&&v.length===2){
        const n=made.get(id),source=made.get(String(v[0]));if(!source)throw Error(msg("mesh.missing_single_image_connection", {value1: v[0]}));
        let slot=n.inputs.findIndex(i=>i.name===name);if(slot<0){n.addInput(name,source.outputs[v[1]]?.type||'*');slot=n.inputs.length-1;}
        if(!n.inputs[slot].link)source.connect(v[1],n,slot);
    }
    for(let i=fresh.length-1;i>=0;i--){
        const n=fresh[i],group=graph._groups.find(g=>g.title==='Single Image or Text / '+n.properties.singleStage);
        if(!group)continue;
        const peers=graph._nodes.filter(p=>p!==n&&p.properties?.singleOwner===owner.id&&p.properties?.singleStage===n.properties.singleStage);
        n.pos=[Math.max(group.pos[0]+25,...peers.map(p=>p.pos[0]+p.size[0]+40)),group.pos[1]+70];n.size=[430,400];n.onResize?.(n.size);
        group.size[0]=Math.max(group.size[0],n.pos[0]+n.size[0]-group.pos[0]+25);fresh.splice(i,1);
    }
    if(fresh.length){let y=origin[1];for(const stage of [...new Set(fresh.map(n=>n.properties.singleStage))]){
        const nodes=fresh.filter(n=>n.properties.singleStage===stage);
        nodes.forEach((n,i)=>{n.pos=[origin[0]+i%4*470,y+70+Math.floor(i/4)*460];n.size=[430,400];n.onResize?.(n.size);});
        const group=new LiteGraph.LGraphGroup('Single Image or Text / '+stage);group.color='#486b75';group.pos=[origin[0]-25,y];group.size=[1910,Math.ceil(nodes.length/4)*460+80];graph.add(group);y+=group.size[1]+90;
    }}
    if(run){
        const bind=(id,name,value)=>{const w=made.get(id)?.widgets?.find(w=>w.name===name);if(w){w.value=value;w.callback?.(value);}};
        bind('122','image',run.references[0].filename);const settings=run.settings;
        const fields=[['94','shape_resolution','target_resolution'],['2003','refine_steps','steps'],['2003','refine_resolution','resolution'],
            ['2003','refine_seed','seed'],['2003','cpu_offload','cpu_offload'],['2003','attention','attention'],
            ['2023','texture_seed','seed'],['2023','texture_steps','steps'],['2023','texture_size','texture_size'],['2023','texture_guidance','guidance'],['2023','texture_mode','texture_mode'],
            ['2030','balanced_triangles','target_triangles'],['2040','compact_triangles','target_triangles'],['3001','quad_count','target_quads'],['2050','print_height_mm','height_mm']];
        for(const [id,key,name] of fields)bind(id,name,settings[key]);
        for(const [id,offset] of [['3',14],['18',0],['23',0]])bind(id,'seed',(settings.shape_seed??42)+offset);
        for(const [name,value] of Object.entries(run.quad_inputs||{method:settings.quad_method||'quadriflow'}))bind('3001',name,value);
        bind('3011','mode',settings.export_grounding||'level');bind('3010','asset_name',run.name);bind('3010','selection_json',JSON.stringify(run.selection));
    }
    graph.change?.();graph.setDirtyCanvas(true,true);
}
export function syncSingleOutputs(outputs,owner){
    for(const [id,value] of Object.entries(outputs||{})){
        const n=app.graph.getNodeById(Number(id)+OFFSET);if(n?.properties?.singleOwner!==owner.id)continue;
        const data=structuredClone(value);app.nodeOutputs[String(n.id)]=data;n.onExecuted?.(data);
    }app.graph.setDirtyCanvas(true,true);
}
export function showSingleWorkflow(){const n=app.graph._nodes.find(n=>n.properties?.singleOwner);if(n)app.canvas.animateToBounds([n.pos[0]-50,n.pos[1]-70,1900,1100],{duration:180,zoom:.8});}
