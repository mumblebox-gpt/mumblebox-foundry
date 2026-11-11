import {sourceText} from "./i18n.js";
import {msg} from "./i18n.js";
import {app} from "/scripts/app.js";

// Native graph display has a single selected image branch. Backend compilation
// remains authoritative; the same branch is returned by the run's graph route.
const ORIGINAL_IDS=[1551,1553,1554,1556,1557,1558,1569,1574];
export function syncTurnaroundBranch(branch,owner){
    const graph=app.graph;
    const entries=Object.entries(branch).filter(([id])=>id!=="900");
    // Check availability before changing the existing live graph.
    for(const [,definition] of entries)if(!LiteGraph.registered_node_types[definition.class_type])
        throw Error(msg("common.required_native_node_is_unavailable", {value1: definition.class_type}));
    const previous=graph.extra?.foundry_turnaround?.node_ids||ORIGINAL_IDS;
    const oldIds=new Set(previous.map(String));
    for(const node of graph._nodes)if(node.properties?.foundryReferenceOwner===owner.id)oldIds.add(String(node.id));
    const outgoing=[];
    for(const id of oldIds){
        const node=graph.getNodeById(id);
        for(const output of node?.outputs||[])for(const linkId of output.links||[]){
            const link=graph.links[linkId];
            if(link&&!oldIds.has(String(link.target_id)))outgoing.push({...link});
        }
    }
    const existing=graph.getNodeById(1551);
    const origin=graph.extra?.foundry_turnaround?.origin||Array.from(existing?.pos||[440,130]);
    for(const id of oldIds){const node=graph.getNodeById(id);if(node)graph.remove(node);}
    const made=new Map();
    for(const [index,[id,definition]] of entries.entries()){
        const node=LiteGraph.createNode(definition.class_type);
        if(!node)throw Error(msg("common.required_native_node_is_unavailable", {value1: definition.class_type}));
        node.id=Number(id);node.title=sourceText(definition._meta?.title||definition.class_type);
        node.properties.foundryTurnaroundOwner=owner.id;
        graph.add(node);
        node.pos=[origin[0]+(index%4)*400,origin[1]+Math.floor(index/4)*410];
        node.size=[370,Math.max(180,node.computeSize()[1])];
        // Set scalar widgets first; dynamic combo widgets may add their inputs.
        for(const [name,value] of Object.entries(definition.inputs))if(!Array.isArray(value)){
            const widget=node.widgets?.find(w=>w.name===name);
            if(widget){widget.value=value;widget.callback?.(value);}
        }
        if(["TextEncodeQwenImage21","TextEncodeQwenImageEditPlus","CLIPTextEncode"].includes(definition.class_type))node.size=[370,350];
        made.set(id,node);
    }
    const primary=graph.getNodeById(900);
    const imageWidget=primary?.widgets?.find(w=>w.name==="image");
    if(imageWidget)imageWidget.value=branch["900"].inputs.image;
    made.set("900",primary);
    for(const [id,definition] of entries){
        const node=made.get(id);
        for(const [name,value] of Object.entries(definition.inputs)){
            if(!Array.isArray(value))continue;
            const source=made.get(String(value[0]));
            if(!source)throw Error(msg("common.missing_turnaround_source", {value1: value[0]}));
            let slot=node.inputs.findIndex(input=>input.name===name);
            if(slot<0){node.addInput(name,source.outputs[value[1]].type);slot=node.inputs.length-1;}
            source.connect(value[1],node,slot);
        }
    }
    for(const link of outgoing){
        const source=made.get(String(link.origin_id)),target=graph.getNodeById(link.target_id);
        if(source&&target)source.connect(link.origin_slot,target,link.target_slot);
    }
    let group=graph._groups.find(g=>g.title==="02 - SELECTED TURNAROUND MODEL"||g.title==="02 - QWEN TURNAROUND");
    if(!group){group=new LiteGraph.LGraphGroup("02 - SELECTED TURNAROUND MODEL");group.color="#345a61";graph.add(group);}
    group.title=sourceText(msg("common.02_selected_turnaround_model"));
    // Keep the existing sheet preview in the same stage as its model branch.
    group.pos=[origin[0]-30,origin[1]-80];group.size=[2974,Math.ceil(entries.length/4)*410+110];
    group.recomputeInsideNodes?.();
    graph.extra??={};graph.extra.foundry_turnaround={node_ids:entries.map(([id])=>id),origin};
}
