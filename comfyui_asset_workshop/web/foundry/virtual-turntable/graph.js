import {app} from '/scripts/app.js';
import {appMode,presentation} from '../app-mode.js';

const layouts={
    turntable:{offset:780000,title:'Virtual Turntable',property:'virtualTurntable',origin:[24000,3000]},
    orbit:{offset:790000,title:'Orbit to Mesh',property:'orbitToMesh',origin:[26800,3000]},
};
const belongs=(node,owner,layout)=>node?.properties?.virtualTurntableOwner===owner.id&&
    (node.properties.orbitLayout||'turntable')===layout;

export function syncTurntableGraph(recipe,owner,key='turntable') {
    const config=layouts[key];
    const prefix=config.title+' / ';
    const graph=app.graph;
    if(owner.graph!==graph)throw Error('Open the Foundry graph to view this workflow.');
    const layout=graph.extra[config.property]||={origin:config.origin};
    const stage=Object.values(recipe)[0]?._meta?.turntable_stage||'setup';
    graph.beforeChange();
    try {
        const made=new Map();
        for(const [id,item] of Object.entries(recipe)){
            let node=graph.getNodeById(Number(id));
            if(node&&!belongs(node,owner,key))throw Error('A different workflow owns node '+id);
            if(node&&node.type!==item.class_type){graph.remove(node);node=null;}
            if(!node){
                node=LiteGraph.createNode(item.class_type);
                if(!node)throw Error('Required ComfyUI node is missing: '+item.class_type);
                node.id=Number(id);graph.add(node);
            }
            node.properties.virtualTurntableOwner=owner.id;
            node.properties.orbitLayout=key;
            node.title=item._meta?.title||item.class_type;
            node.mode=2;
            for(const [name,value] of Object.entries(item.inputs)){
                if(Array.isArray(value))continue;
                const widget=node.widgets?.find(w=>w.name===name);
                if(widget&&widget.value!==value){widget.value=value;widget.callback?.(value);}
                const slot=node.inputs?.findIndex(input=>input.name===name);
                if(slot>=0&&node.inputs[slot].link!=null)node.disconnectInput(slot);
            }
            made.set(id,node);
        }
        for(const [id,item] of Object.entries(recipe)){
            const target=made.get(id);
            for(const [name,value] of Object.entries(item.inputs)){
                if(!Array.isArray(value)||!made.has(String(value[0])))continue;
                const source=made.get(String(value[0]));
                let slot=target.inputs?.findIndex(input=>input.name===name)??-1;
                if(slot<0){target.addInput(name,source.outputs[value[1]]?.type||'*');slot=target.inputs.length-1;}
                source.connect(value[1],target,slot);
            }
        }
        const groups={
            'Reference and four views':[], 'H3 orbit':[], 'Frame masks and reconstruction':[], 'Refinement and export':[],
        };
        for(const node of graph._nodes.filter(n=>belongs(n,owner,key))){
            const id=node.id-config.offset;
            const section=id<22||id===56?'Reference and four views':id<=44?'H3 orbit':(id<=55||key==='orbit'&&(id<=64||id===340||id===381||id===382||id>=1000&&id<2000))?'Frame masks and reconstruction':'Refinement and export';
            groups[section].push(node);
        }
        for(const group of [...graph._groups])if(group.title.startsWith(prefix))graph.remove(group);
        let [x,y]=layout.origin;
        for(const [name,nodes] of Object.entries(groups)){
            if(!nodes.length)continue;
            nodes.forEach((node,index)=>{
                node.pos=[x+index%4*490,y+60+Math.floor(index/4)*500];
                node.size=[440,Math.min(460,Math.max(250,node.size?.[1]||0))];
            });
            const group=new LiteGraph.LGraphGroup(prefix+name);
            group.pos=[x-25,y];group.size=[1980,Math.ceil(nodes.length/4)*500+72];
            group.color={'Reference and four views':'#496d65','H3 orbit':'#55667b','Frame masks and reconstruction':'#746044','Refinement and export':'#5c5978'}[name];graph.add(group);
            y+=group.size[1]+100;
        }
        layout.stage=stage;
        graph.change?.();
        graph.setDirtyCanvas(true,true);
    }finally{graph.afterChange();}
}

export function syncTurntableOutputs(outputs,owner,key='turntable') {
    if(owner.graph!==app.graph)return;
    for(const [id,value] of Object.entries(outputs||{})){
        const node=app.graph.getNodeById(Number(id));
        if(!belongs(node,owner,key))continue;
        if(JSON.stringify(app.nodeOutputs[id])===JSON.stringify(value))continue;
        const copied=structuredClone(value);app.nodeOutputs[id]=copied;node.onExecuted?.(copied);
    }
}

export function showTurntableGraph(owner,key='turntable') {
    if(appMode)presentation.graph();
    const group=owner.graph._groups.find(item=>item.title===layouts[key].title+' / Reference and four views');
    if(group)app.canvas.animateToBounds([...group.pos,1980,1100],{duration:180,zoom:.8});
}
