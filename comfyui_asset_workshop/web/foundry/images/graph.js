import {app} from '/scripts/app.js';

// This group is independent: it has no connections to the mesh pipeline.
export function showImageStage(run,owner){
    if(owner.graph!==app.graph)return;
    const graph=app.graph,stage=run.pending||run.last_stage;
    const scope=run.graph_scope==='ccore-reference'?'ccore-reference':'';
    const stateKey=scope?'foundry_creation_ccore':'foundry_creation';
    const groupPrefix=scope?'CCORE REFERENCE —':'IMAGE CREATOR —';
    const owned=node=>node?.properties?.foundryCreationOwner===owner.id&&
        (node.properties.foundryCreationScope||'')===scope;
    if(stage?.graph&&graph.extra?.[stateKey]?.prompt!==stage.prompt_id){
        for(const def of Object.values(stage.graph))if(!LiteGraph.registered_node_types[def.class_type])
            throw Error('The image graph needs '+def.class_type+'. Restart Comfy after installing the update.');
        for(const id of Object.keys(stage.graph)){
            const existing=graph.getNodeById(Number(id));
            if(existing&&!owned(existing))throw Error('Image graph ID conflicts with another workflow. Existing nodes were preserved.');
        }
        for(const node of [...graph._nodes])if(owned(node))graph.remove(node);
        const origin=graph.extra?.[stateKey]?.origin||[owner.pos[0],Math.max(...graph._nodes.map(n=>n.pos[1]+n.size[1]))+300];
        const made=new Map();
        for(const [index,[id,def]] of Object.entries(stage.graph).entries()){
            const node=LiteGraph.createNode(def.class_type);node.id=Number(id);node.title=def._meta?.title||def.class_type;
            node.properties.foundryCreationOwner=owner.id;
            if(scope)node.properties.foundryCreationScope=scope;
            graph.add(node);
            node.pos=[origin[0]+index%5*350,origin[1]+Math.floor(index/5)*350];
            for(const [name,value] of Object.entries(def.inputs))if(!Array.isArray(value)){
                const widget=node.widgets?.find(w=>w.name===name);if(widget){widget.value=value;widget.callback?.(value);}
            }
            node.size=[320,Math.max(150,Math.min(300,node.computeSize()[1]))];made.set(id,node);
        }
        for(const [id,def] of Object.entries(stage.graph))for(const [name,value] of Object.entries(def.inputs))if(Array.isArray(value)){
            const target=made.get(id),source=made.get(String(value[0]));if(!source)continue;
            let slot=target.inputs?.findIndex(input=>input.name===name)??-1;
            if(slot<0){target.addInput(name,source.outputs[value[1]].type);slot=target.inputs.length-1;}
            source.connect(value[1],target,slot);
        }
        let group=graph._groups.find(g=>g.title.startsWith(groupPrefix));
        if(!group){group=new LiteGraph.LGraphGroup(groupPrefix);graph.add(group);}
        group.title=groupPrefix+' '+run.stage;group.color='#376270';group.pos=[origin[0]-25,origin[1]-65];
        group.size=[1780,Math.ceil(made.size/5)*350+90];group.recomputeInsideNodes?.();
        graph.extra??={};graph.extra[stateKey]={origin,prompt:stage.prompt_id};
    }
    if(!run.pending)for(const [id,output] of Object.entries(run.outputs||{})){
        const node=graph.getNodeById(Number(id));if(!owned(node))continue;
        const signature=JSON.stringify(output);if(node._foundryOutput===signature)continue;
        node._foundryOutput=signature;
        app.nodeOutputs??={};app.nodeOutputs[id]=output;node.onExecuted?.(output);
    }
    app.canvas.setDirty(true,true);
}
