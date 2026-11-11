import {sourceText} from "../i18n.js";
import {msg} from "../i18n.js";
import {app} from '/scripts/app.js';

// Separate ID spaces and ownership tags protect Turnaround and HairDeck.
export function syncGuidedBranch(recipe,owner,{offset=100000,replace=true}={}){
    if(owner.graph!==app.graph)throw Error(msg("guided.open_the_foundry_graph_before_continuing"));
    const entries=Object.entries(recipe).filter(([,n])=>!['control','repair_control'].includes(n._meta?.fvb_stage));
    for(const [,n] of entries)if(!LiteGraph.registered_node_types[n.class_type])throw Error(msg("guided.required_node_is_not_installed", {value1: n.class_type}));
    const graph=app.graph;graph.extra??={};
    const origin=graph.extra.guided_origin||[Math.max(0,...graph._nodes.filter(n=>!n.properties?.guidedOwner).map(n=>n.pos[0]+n.size[0]))+1000,100];
    graph.extra.guided_origin=origin;
    const previous=graph._nodes.filter(n=>n.properties?.guidedOwner===owner.id&&n.properties?.guidedOffset===offset);
    if(replace)for(const n of previous)graph.remove(n);
    const made=new Map();
    for(const [index,[id,definition]] of entries.entries()){
        const nativeId=Number(id)+offset;
        let n=graph.getNodeById(nativeId);
        if(n&&n.properties?.guidedOwner!==owner.id)throw Error(msg("guided.another_workflow_owns_node", {nativeId: nativeId}));
        if(n&&n.type!==definition.class_type){graph.remove(n);n=null;}
        if(!n){n=LiteGraph.createNode(definition.class_type);n.id=nativeId;graph.add(n);}
        n.properties.guidedOwner=owner.id;n.properties.guidedOffset=offset;
        n.properties.guidedStage=definition._meta?.fvb_stage||(offset===200000?'exports':'processing');
        n.title=sourceText(msg("guided.3d_guided_2", {value1: definition._meta?.title||definition.class_type}));
        n.mode=2;
        for(const [name,value] of Object.entries(definition.inputs||{}))if(!Array.isArray(value)){
            const widget=n.widgets?.find(w=>w.name===name);
            if(widget){widget.value=value;widget.callback?.(value);}
        }
        const fixed=n.widgets?.find(w=>w.name==='control_after_generate');if(fixed)fixed.value='fixed';
        made.set(id,n);
    }
    for(const [id,definition] of entries)for(const [name,value] of Object.entries(definition.inputs||{})){
        if(!Array.isArray(value)||value.length!==2)continue;
        const source=made.get(String(value[0]));if(!source)throw Error(msg("guided.missing_guided_connection", {value1: value[0]}));
        const n=made.get(id);let slot=n.inputs.findIndex(i=>i.name===name);
        if(slot<0){n.addInput(name,source.outputs[value[1]]?.type||'*');slot=n.inputs.length-1;}
        source.connect(value[1],n,slot);
    }
    for(const g of [...graph._groups])if(g.title.startsWith('3D-Guided / '+offset+' / '))graph.remove(g);
    let y=origin[1]+(offset===200000?24000:0);
    const stages=[...new Set(graph._nodes.filter(n=>n.properties?.guidedOwner===owner.id&&n.properties.guidedOffset===offset).map(n=>n.properties.guidedStage))];
    for(const stage of stages){
        const nodes=graph._nodes.filter(n=>n.properties?.guidedOwner===owner.id&&n.properties.guidedOffset===offset&&n.properties.guidedStage===stage);
        nodes.forEach((n,i)=>{n.pos=[origin[0]+i%4*470,y+60+Math.floor(i/4)*460];n.size=[430,400];n.onResize?.(n.size);});
        const group=new LiteGraph.LGraphGroup('3D-Guided / '+offset+' / '+stage);
        group.color=offset===200000?'#5d4e70':'#365f59';group.pos=[origin[0]-25,y];group.size=[1910,Math.ceil(nodes.length/4)*460+70];graph.add(group);
        y+=group.size[1]+100;
    }
    graph.extra.guided_method={method:'3d-guided/v1',owner:owner.id,offset:100000,finishing_offset:200000};
    graph.change?.();graph.setDirtyCanvas(true,true);
}

export function syncGuidedOutputs(outputs,owner,offset=100000){
    if(owner.graph!==app.graph)return;
    for(const [id,value] of Object.entries(outputs||{})){
        const n=app.graph.getNodeById(Number(id)+offset);
        if(n?.properties?.guidedOwner!==owner.id)continue;
        const data=JSON.parse(JSON.stringify(value));app.nodeOutputs[String(n.id)]=data;n.onExecuted?.(data);
    }
    app.graph.setDirtyCanvas(true,true);
}

export function setGuidedQuadAvailability(owner,enabled){
    for(const node of owner.graph._nodes){
        if(node.properties?.guidedOwner!==owner.id||node.type!=='Hi3DQuadFinish')continue;
        node.mode=2;
        const widget=node.widgets?.find(w=>w.name==='enabled');
        if(widget)widget.value=enabled;
        node.properties.guidedQuadDisabled=!enabled;
        node.title=sourceText(enabled?msg("guided.3d_guided_quad_retopology"):msg("guided.3d_guided_quad_retopology_disabled_retained"));
    }
    owner.graph.change?.();owner.graph.setDirtyCanvas(true,true);
}

export function showGuidedWorkflow(){
    const n=app.graph._nodes.find(n=>n.properties?.guidedOffset===100000);
    if(n)app.canvas.animateToBounds([n.pos[0]-50,n.pos[1]-70,1900,1100],{duration:180,zoom:.8});
}
