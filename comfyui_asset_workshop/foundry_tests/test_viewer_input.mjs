import test from "node:test";
import assert from "node:assert/strict";
import {installOrbitInput,createModelHost,mountMesh} from "../web/foundry/wizard/preview.js";

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
