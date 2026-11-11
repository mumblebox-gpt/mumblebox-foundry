import {sourceText} from "../i18n.js";
import {msg} from "../i18n.js";
import {app} from '/scripts/app.js';

const copy=value=>JSON.parse(JSON.stringify(value));
export function mergeHairBranch(workflow,template){
    const graph=copy(workflow),expected=new Map(template.nodes.map(n=>[+n.id,n]));
    let changed=false;
    const existingGroup=graph.groups.find(g=>g.title.startsWith('HAIR / 01'));
    const sourceGroup=template.groups.find(g=>g.title.startsWith('HAIR / 01'));
    const bottom=Math.max(0,...graph.groups.map(g=>g.bounding[1]+g.bounding[3]));
    const dy=(existingGroup?existingGroup.bounding[1]:bottom+240)-sourceGroup.bounding[1];
    for(const [id,source] of expected){
        const node=graph.nodes.find(n=>+n.id===id);
        if(node){
            if(node.type===source.type)continue;
            if(id!==70002||node.type!=='HairDeckGenerate')throw Error(msg("hair.a_reserved_hairdeck_node_id_is_occupied_by_another_node_the_graph_was_preser"));
            const values=node.widgets_values_named||{};
            node.type=source.type;node.title=sourceText(source.title);node.properties={...node.properties,'Node name for S&R':source.type};
            node.inputs=node.inputs.filter(i=>['model','external_image','transparent_mask'].includes(i.name));
            node.widgets_values=['',0,50,2,true,true].map((fallback,index)=>values[['image','seed','steps','cfg','generate_bones','colors'][index]]??fallback);
            node.widgets_values_named=Object.fromEntries(['image','seed','steps','cfg','generate_bones','colors'].map((key,i)=>[key,node.widgets_values[i]]));
            changed=true;
        }else{
            const added=copy(source);added.pos=[source.pos[0],source.pos[1]+dy];
            for(const input of added.inputs||[])input.link=null;
            for(const output of added.outputs||[])output.links=[];
            graph.nodes.push(added);changed=true;
        }
    }
    if(!changed)return {changed:false,graph:workflow};
    let nextLink=Math.max(graph.last_link_id||0,...graph.links.map(row=>+row[0]));
    for(const source of template.links){
        const [,from,fromSlot,to,toSlot,type]=source;
        if(graph.links.some(row=>+row[1]===+from&&row[2]===fromSlot&&+row[3]===+to&&row[4]===toSlot))continue;
        const target=graph.nodes.find(n=>+n.id===+to).inputs[toSlot];
        if(target.link!=null)throw Error(msg("hair.a_hairdeck_input_has_a_custom_connection_the_graph_was_preserved"));
        const id=++nextLink;graph.links.push([id,from,fromSlot,to,toSlot,type]);target.link=id;
        graph.nodes.find(n=>+n.id===+from).outputs[fromSlot].links??=[];
        graph.nodes.find(n=>+n.id===+from).outputs[fromSlot].links.push(id);
    }
    let nextGroup=Math.max(0,...graph.groups.map(g=>+g.id||0));
    for(const group of template.groups){
        if(graph.groups.some(g=>g.title===group.title))continue;
        const added=copy(group);added.id=++nextGroup;added.bounding[1]+=dy;graph.groups.push(added);
    }
    graph.last_node_id=Math.max(graph.last_node_id||0,...expected.keys());graph.last_link_id=nextLink;
    return {changed:true,graph};
}

export async function ensureHairBranch(template){
    const original=copy(app.graph.serialize());
    // Capture current named values before changing the old node's widget layout.
    for(const source of original.nodes){
        if(+source.id!==70002)continue;
        source.widgets_values_named=Object.fromEntries((app.graph.getNodeById(70002)?.widgets||[]).map(w=>[w.name,w.value]));
    }
    const merged=mergeHairBranch(original,template);
    if(!merged.changed)return false;
    const outputs=copy(app.nodeOutputs||{}),workflow=app.extensionManager.workflow.activeWorkflow;
    // Only the independent branch changes. Keep output state for every other
    // workflow and use the existing active workflow, never a replacement tab.
    await app.loadGraphData(merged.graph,true,true,workflow);app.nodeOutputs=outputs;
    workflow.changeTracker.prepareForSave();await workflow.save();
    return true;
}
