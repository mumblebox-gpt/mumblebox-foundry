import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../web/foundry/wizard/preview.js',import.meta.url),'utf8')
    .replace(/^import .*;$/gm,'').replaceAll('export function','function').replaceAll('export async function','async function');
function fixture(result){
    const calls=[];const viewer={loadModel:async(...args)=>{calls.push(args);return result;},
        handleResize(){},fitToViewer(){},forceRender(){},setLightIntensity(){},remove(){}};
    const context={AbortController,window:{comfyAPI:{createLoad3d:{createLoad3d:()=>viewer}}},
        ResizeObserver:class{observe(){}disconnect(){}}};
    vm.runInNewContext(source+';globalThis.mount=mountMesh;',context);
    return {mount:context.mount,calls,container:new EventTarget()};
}
test('artifact endpoint previews identify their actual mesh format',async()=>{
    const f=fixture('loaded');await f.mount(f.container,'/artifacts/proxy:glb',null,'working-proxy.glb');
    assert.equal(f.calls[0][1],'working-proxy.glb');
    assert.equal(f.calls[0][2].silent,true);
});
test('native viewer failures produce an error instead of a blank successful preview',async()=>{
    const f=fixture('unknown-type');
    await assert.rejects(f.mount(f.container,'/artifacts/proxy:glb',null,'working-proxy.glb'),/unknown-type/);
});
