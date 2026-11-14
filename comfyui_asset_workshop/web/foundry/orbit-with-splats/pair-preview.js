import {el, button, hint} from '../dom.js';
import {msg, setText} from '../i18n.js';
import {mountMesh} from '../wizard/preview.js';

export const label=(key, values)=>msg('orbit_splats.'+key, values);

function prepare(viewer, gaussian) {
    const model=viewer.getCurrentModel();
    if (!model) throw Error(label('load_failed'));
    model.position.set(0,0,0);
    model.scale.setScalar(1);
    model.rotation.set(0,0,0);
    // Comfy's PLY adapter applies an X half-turn for conventional scan input.
    // Foundry's PLY is already in the exact same Y-up frame as its GLB.
    if (gaussian) model.children[0].quaternion.identity();
    model.updateMatrixWorld(true);
    viewer.toggleGrid?.(false);
    viewer.sceneManager.setBackgroundColor('#353632');
    viewer.forceRender();
    return model;
}

export function pairedReview(wizard, onReady) {
    const root=el('section',{class:'orbit-pair'});
    const grid=el('div',{class:'orbit-pair-grid','data-view':'both'});
    const status=el('p',{role:'status',class:'muted'},label('loading'));
    const specs=[['paired_mesh','mesh','textured-mesh.glb'],['gaussian','splat','gaussian-splat.ply']];
    const panes=specs.map(([role,key,filename])=>{
        const mount=el('div',{class:'turntable-mesh-preview',tabIndex:0,'aria-label':label(key)});
        grid.append(el('article',{'data-role':key},el('h3',{},label(key)),mount));
        return {role,key,filename,mount};
    });
    const switches=el('div',{class:'actions',role:'group','aria-label':label('display')});
    const handles=[], listeners=[];
    let disposed=false,syncing=false;
    let locked=false;
    let camera;
    const select=mode=>{
        wizard.pairMode=mode;
        grid.dataset.view=mode;
        for(const control of switches.children) control.setAttribute('aria-pressed',String(control.dataset.mode===mode));
        for(const pane of panes) if(mode==='both'||mode===pane.key) pane.viewer?.handleResize();
    };
    for(const key of ['both','mesh','splat'])
        switches.append(button(label(key),()=>select(key),{'data-mode':key,'aria-pressed':String(key==='both')}));
    const reset=button(label('reset_view'),()=>camera&&panes.forEach(pane=>pane.viewer.setCameraState(camera)),{disabled:true});
    root.append(el('h3',{},label('pair_title')),hint(label('pair_help')),switches,grid,reset,status);

    const setLocked=value=>{
        locked=value;
        for(const control of [...switches.children,reset])control.disabled=value;
        grid.inert=value;
    };
    const synchronize=(source,target)=>{
        if(syncing||locked)return;
        syncing=true;
        try{target.viewer.setCameraState(source.viewer.getCameraState());}
        finally{syncing=false;}
    };
    const release=()=>{disposed=true;listeners.forEach(fn=>fn());handles.forEach(fn=>fn());};
    wizard.previewDisposers.push(release);
    requestAnimationFrame(async()=>{
        try{
            for(const pane of panes){
                if(disposed)return;
                const handle=await mountMesh(pane.mount,wizard.artifact(pane.role),wizard.cap.viewer,pane.filename);
                if(disposed){handle();return;}
                handles.push(handle);
                pane.viewer=handle.viewer;
                pane.model=prepare(handle.viewer,pane.key==='splat');
            }
            const [mesh,splat]=panes;
            const bounds=mesh.viewer.modelManager.getCurrentBounds();
            const size=bounds.getSize(mesh.model.position.clone());
            const target=bounds.getCenter(mesh.model.position.clone());
            const radius=Math.max(size.x,size.y,size.z);
            if(!(radius>0))throw Error(label('load_failed'));
            const position=target.clone().add(target.clone().set(.95,.45,1.8).multiplyScalar(radius));
            camera={...mesh.viewer.getCameraState(),position,target,zoom:1,cameraType:'perspective',fov:37};
            for(const pane of panes){
                const manager=pane.viewer.getCameraManager();
                manager.perspectiveCamera.near=radius/100;
                manager.perspectiveCamera.far=radius*100;
                pane.viewer.setCameraState(camera);
                const controls=pane.viewer.getControlsManager().controls;
                const changed=()=>synchronize(pane,pane===mesh?splat:mesh);
                controls.addEventListener('change',changed);
                listeners.push(()=>controls.removeEventListener('change',changed));
            }
            reset.disabled=false;
            setText(status,label('ready'));
            select(wizard.pairMode||'both');
            onReady({mesh,splat,bounds,camera,radius,setLocked,select,mode:()=>wizard.pairMode});
        }catch(error){
            if(!disposed)setText(status,label('preview_error',{message:error.message}));
        }
    });
    return root;
}
