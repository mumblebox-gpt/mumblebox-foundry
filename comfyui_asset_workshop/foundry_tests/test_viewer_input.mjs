import test from "node:test";
import assert from "node:assert/strict";
import {installOrbitInput,createModelHost,mountMesh} from "../web/foundry/wizard/preview.js";

test('existing HairDeck and Turnaround previews infer the filename needed by the native host',async()=>{
    const previous={window:globalThis.window,ResizeObserver:globalThis.ResizeObserver,fetch:globalThis.fetch};
    const loads=[],requests=[];
    const viewer={async loadModel(url,name){loads.push({url,name});await this.host.fetchApi('/api/view?filename='+encodeURIComponent(name));return 'loaded';},handleResize(){},fitToViewer(){},forceRender(){},updateStatusMouseOnViewer(){},dispose(){}};
    globalThis.window={comfyAPI:{createLoad3d:{createLoad3d:(container,host)=>({...viewer,host})},load3dHost:{load3dHost:{fetchApi:()=>{throw Error('Wrong native endpoint');}}}}};
    globalThis.ResizeObserver=class{observe(){}disconnect(){}};
    globalThis.fetch=async url=>{requests.push(url);return {};};
    try{
        for(const [url,name] of [['/hair/file?path=variant%2Fhair_00001_.glb','hair_00001_.glb'],['/view?filename=mesh.glb&type=output','mesh.glb']]){
            const dispose=await mountMesh(new EventTarget(),url,{host:true});
            assert.equal(loads.at(-1).name,name);assert.equal(requests.at(-1),url);dispose();
        }
    }finally{Object.assign(globalThis,previous);}
});

test('embedded native viewers announce readiness so asynchronous splats can paint',async()=>{
    const oldWindow=globalThis.window,oldResize=globalThis.ResizeObserver,events=[];
    const viewer={loadModel:async()=>{events.push('loaded');return 'loaded';},handleResize(){},fitToViewer(){},setLightIntensity(){},forceRender(){},emitModelReady(){events.push('ready');},dispose(){events.push('disposed');},updateStatusMouseOnViewer(){}};
    globalThis.window=new EventTarget();window.comfyAPI={createLoad3d:{createLoad3d:()=>viewer}};
    globalThis.ResizeObserver=class{observe(){}disconnect(){}};
    try{
        const dispose=await mountMesh(new EventTarget(),'/owned/asset.spz',null,'asset.spz');
        assert.deepEqual(events,['loaded','ready']);dispose();assert.equal(events.at(-1),'disposed');
    }finally{globalThis.window=oldWindow;globalThis.ResizeObserver=oldResize;}
});

test('native model requests retain the owning artifact endpoint without changing other requests',async()=>{
    const original=globalThis.fetch,requests=[],hostCalls=[];
    globalThis.fetch=async(...args)=>{requests.push(args);return 'owned';};
    try{
        const host={fetchApi:async(...args)=>{hostCalls.push(args);return 'native';}};
        const first=createModelHost(host,'/owned/first?path=model.glb','model.glb');
        const second=createModelHost(host,'/owned/second?path=model.glb','model.glb');
        assert.equal(await first.fetchApi('api/view?filename=model.glb&type=output'),'owned');
        assert.equal(await second.fetchApi('api/view?filename=model.glb&type=output'),'owned');
        assert.deepEqual(requests.map(r=>r[0]),['/owned/first?path=model.glb','/owned/second?path=model.glb']);
        assert.equal(await first.fetchApi('/api/view?filename=other.glb'),'native');
        assert.equal(hostCalls.length,1);assert.notEqual(first.fetchApi,host.fetchApi);
    }finally{globalThis.fetch=original;}
});

function input(target,type,values={}){
    const event=new Event(type);Object.assign(event,values);target.dispatchEvent(event);
}
test("camera accepts drag and wheel but never idle or stale hover",async()=>{
    const surface=new EventTarget(),host=new EventTarget();
    const controls={enabled:true,autoRotate:true,enableDamping:true};
    const dispose=installOrbitInput(surface,controls,host);
    assert.equal(controls.enabled,false);
    assert.equal(controls.autoRotate,false);assert.equal(controls.enableDamping,false);
    input(surface,"pointermove",{pointerType:"mouse",buttons:0});
    assert.equal(controls.enabled,false);
    input(surface,"pointerdown",{pointerType:"mouse",button:0});
    assert.equal(controls.enabled,true);
    input(host,"pointerup");await new Promise(resolve=>setTimeout(resolve,5));
    assert.equal(controls.enabled,false);
    input(surface,"pointerdown",{pointerType:"mouse",button:0});
    input(surface,"pointermove",{pointerType:"mouse",buttons:0});
    assert.equal(controls.enabled,false,"a missed pointer-up must not turn hover into drag");
    input(surface,"wheel");assert.equal(controls.enabled,true);
    await new Promise(resolve=>setTimeout(resolve,5));assert.equal(controls.enabled,false);
    dispose();input(surface,"pointerdown",{pointerType:"mouse",button:0});
    assert.equal(controls.enabled,false,"disposed previews must not keep listeners");
});
