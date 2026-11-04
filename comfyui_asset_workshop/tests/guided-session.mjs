import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../web/foundry/shell.js',import.meta.url),'utf8');
function method(name,next,context){
    return vm.runInNewContext('({'+source.slice(source.indexOf('    async '+name+'('),source.indexOf('    async '+next+'('))+'})',context);
}
test('opening a new guided draft cannot overwrite a running asset binding',async()=>{
    const owner=method('openGuidedWizard','openHairWizard',{request:async()=>({active:true})});
    owner.node={properties:{foundryGuided:{id:'a'.repeat(32)}}};
    owner.viewDispose=()=>assert.fail('Running view must remain attached');owner.message=()=>{};
    assert.equal(await owner.openGuidedWizard(),false);
    assert.equal(owner.node.properties.foundryGuided.id,'a'.repeat(32));
});
test('a busy guided method keeps an accepted image handoff for later',async()=>{
    const owner=method('openMeshMethod','openGuidedWizard',{});
    const handoff={name:'Accepted image'};owner.pendingMeshHandoff=handoff;owner.meshOrigin={method:'guided'};
    owner.openGuidedWizard=async()=>false;
    await owner.openMeshMethod('guided');
    assert.equal(owner.pendingMeshHandoff,handoff);
});

test('finishing cleanup completion unlocks retry after a failure',async()=>{
    const controller=readFileSync(new URL('../web/foundry/guided/controller.js',import.meta.url),'utf8');
    const previous={status:'complete',completed:{texture:{}},finishing:{status:'failed',stage:'quads',active:true}};
    const current={...previous,finishing:{...previous.finishing,active:false}};
    const owner=vm.runInNewContext('({'+controller.slice(controller.indexOf('    async poll('),controller.indexOf('    async act('))+'})',{
        request:async()=>current,setTimeout:()=>0,stagePage:{}});
    let renders=0;
    Object.assign(owner,{id:'a'.repeat(32),job:previous,live:async()=>{},outputs(){},render(){renders++;}});
    await owner.poll();
    assert.equal(renders,1,'A finished cleanup must redraw the available Retry control');
    assert.equal(owner.job.finishing.active,false);
});

test('resuming a saved guided draft removes unavailable quad selections',async()=>{
    const controller=readFileSync(new URL('../web/foundry/guided/controller.js',import.meta.url),'utf8');
    const cap={exports:[{id:'detailed'},{id:'print'}],quad_retopology_enabled:false};
    const owner=vm.runInNewContext('({'+controller.slice(controller.indexOf('    async init('),controller.indexOf('    active('))+'})',{
        request:async()=>cap,setGuidedQuadAvailability(){}});
    Object.assign(owner,{node:{},draft:{selection:{variants:{detailed:{formats:['glb']},quad_light:{formats:['blend']}}},finishing:{quad_count:25000}},
        live:async()=>{},render(){},poll(){}});
    await owner.init();
    assert.deepEqual(Object.keys(owner.draft.selection.variants),['detailed']);
    assert.equal(owner.draft.finishing.quad_count,undefined);
});
