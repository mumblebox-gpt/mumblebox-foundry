import {msg, setText, appendContent} from "../i18n.js";
import {el,button,hint} from '../dom.js';
import {mountMesh} from '../wizard/preview.js';
import {fileURL} from './controller.js';

// A paired geometry inspector owns both viewers and all camera subscriptions.
// The canonical meshes remain welded; shaded copies are display-only.
export function comparison(w){
    const available=[['master',msg("splat.clean_master")],['companion',msg("splat.lightweight_companion")]].filter(([key])=>w.run?.artifacts?.[key]);
    if(available.length<2)return hint(msg("splat.the_paired_geometry_inspector_appears_when_both_meshes_are_saved"));
    const root=el('section',{class:'splat-comparison','aria-label':msg("splat.linked_geometry_comparison")});
    const grid=el('div',{class:'splat-comparison-grid'}),views=[],handles=[],removers=[];
    let disposed=false,linked=true,syncing=false,wire=false;
    const status=el('p',{role:'status',class:'muted'},msg("splat.loading_both_geometry_views"));
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
        const target=el('div',{class:'splat-compare-canvas',tabIndex:0,'aria-label':msg("splat.rotatable_preview", {label: label})});
        const counts=q?`${q.triangles.toLocaleString()} triangles · ${q.components.toLocaleString()} connected ${q.components===1?'shell':'shells'}`:'Geometry checks not recorded';
        appendContent(grid, el('article',{},el('h3',{},label),hint(counts),target,
            el('span',{class:'badge'},q?.passed?msg("splat.closed_geometry_checks_passed"):msg("splat.geometry_checks_pending"))));
        views.push({target,art});
    }
    const wireButton=button(msg("splat.show_wireframe"),()=>{
        wire=!wire;for(const v of views)v.viewer?.setMaterialMode(wire?'wireframe':'original');
        setText(wireButton, wire?msg("splat.show_solid_surface"):msg("splat.show_wireframe"));wireButton.setAttribute('aria-pressed',String(wire));
    },{'aria-pressed':'false',disabled:true});
    const reset=button(msg("splat.reset_both_views"),()=>{for(const v of views)v.viewer?.fitToViewer();sync(0);},{disabled:true});
    appendContent(root, el('h3',{},msg("splat.detail_versus_lightweight_geometry")), hint(msg("splat.drag_either_model_to_inspect_both_from_the_same_angle_the_splat_keeps_the_ap")), el('div',{class:'actions'},el('label',{class:'check-row'},link,msg("splat.link_rotation_and_zoom")),wireButton,reset), grid, status);
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
            setText(status, master&&companion?msg("splat.fewer_triangles_in_the_companion_inspect_small_features_before_using_it_for", {value1: (100*(1-companion/master)).toFixed(1)}):msg("splat.drag_to_rotate_scroll_to_zoom_right_drag_to_pan"));
        }catch(e){if(!disposed)setText(status, msg("splat.comparison_preview", {message: e.message}));}
    });
    w.disposers.push(()=>{disposed=true;removers.forEach(f=>f());handles.forEach(f=>f());});
    return root;
}
