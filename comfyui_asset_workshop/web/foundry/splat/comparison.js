import {el,button,hint} from '../dom.js';
import {mountMesh} from '../wizard/preview.js';
import {fileURL} from './controller.js';

// A paired geometry inspector owns both viewers and all camera subscriptions.
// The canonical meshes remain welded; shaded copies are display-only.
export function comparison(w){
    const available=[['master','Clean master'],['companion','Lightweight companion']].filter(([key])=>w.run?.artifacts?.[key]);
    if(available.length<2)return hint('The paired geometry inspector appears when both meshes are saved.');
    const root=el('section',{class:'splat-comparison','aria-label':'Linked geometry comparison'});
    const grid=el('div',{class:'splat-comparison-grid'}),views=[],handles=[],removers=[];
    let disposed=false,linked=true,syncing=false,wire=false;
    const status=el('p',{role:'status',class:'muted'},'Loading both geometry views…');
    const link=el('input',{type:'checkbox',checked:true,onchange:e=>{linked=e.target.checked;if(linked)sync(0);}});
    function sync(index){
        if(!linked||syncing||views.some(v=>!v.viewer))return;
        syncing=true;
        try{
            const source=views[index].viewer,target=views[1-index].viewer;
            target.cameraManager.setCameraState(source.cameraManager.getCameraState());
            target.controlsManager.controls.update();target.forceRender();
        }finally{syncing=false;}
    }
    for(const [role,label] of available){
        const q=w.run.quality?.[role],art=w.run.artifacts[role+'_presentation']||w.run.artifacts[role];
        const target=el('div',{class:'splat-compare-canvas',tabIndex:0,'aria-label':label+' rotatable preview'});
        const counts=q?`${q.triangles.toLocaleString()} triangles · ${q.components.toLocaleString()} connected ${q.components===1?'shell':'shells'}`:'Geometry checks not recorded';
        grid.append(el('article',{},el('h3',{},label),hint(counts),target,
            el('span',{class:'badge'},q?.passed?'Closed geometry · checks passed':'Geometry checks pending')));
        views.push({target,art});
    }
    const wireButton=button('Show wireframe',()=>{
        wire=!wire;for(const v of views)v.viewer?.setMaterialMode(wire?'wireframe':'original');
        wireButton.textContent=wire?'Show solid surface':'Show wireframe';wireButton.setAttribute('aria-pressed',String(wire));
    },{'aria-pressed':'false',disabled:true});
    const reset=button('Reset both views',()=>{for(const v of views)v.viewer?.fitToViewer();sync(0);},{disabled:true});
    root.append(el('h3',{},'Detail versus lightweight geometry'),hint('Drag either model to inspect both from the same angle. The splat keeps the appearance; these meshes provide separate geometry.'),
        el('div',{class:'actions'},el('label',{class:'check-row'},link,'Link rotation and zoom'),wireButton,reset),grid,status);
    requestAnimationFrame(async()=>{
        try{
            for(const v of views){
                if(disposed)return;
                const handle=await mountMesh(v.target,fileURL(w.runId,v.art.relative),w.cap.viewer_module,v.art.relative.split('/').at(-1));
                if(disposed){handle();return;}handles.push(handle);v.viewer=handle.viewer;
                v.viewer.setLightIntensity?.(1);
                v.viewer.toggleGrid?.(false);
            }
            views.forEach((v,i)=>{const controls=v.viewer.controlsManager.controls,changed=()=>sync(i);controls.addEventListener('change',changed);removers.push(()=>controls.removeEventListener('change',changed));});
            sync(0);wireButton.disabled=false;reset.disabled=false;
            const master=w.run.quality?.master?.triangles,companion=w.run.quality?.companion?.triangles;
            status.textContent=master&&companion?`${(100*(1-companion/master)).toFixed(1)}% fewer triangles in the companion. Inspect small features before using it for collision.`:'Drag to rotate. Scroll to zoom. Right-drag to pan.';
        }catch(e){if(!disposed)status.textContent='Comparison preview: '+e.message;}
    });
    w.disposers.push(()=>{disposed=true;removers.forEach(f=>f());handles.forEach(f=>f());});
    return root;
}
