import {el,hint} from "../dom.js";
export async function mountMesh(container,url,module,filename) {
    let factory=window.comfyAPI?.createLoad3d?.createLoad3d;
    if(!factory&&module)factory=(await import(module.url))[module.export];
    if(!factory)throw Error("The native Comfy 3D viewer is not available.");
    const viewer=module?.host?factory(container,createModelHost(window.comfyAPI.load3dHost.load3dHost,url,filename)):factory(container);
    let disposed=false;
    const resize=new ResizeObserver(()=>viewer.handleResize());
    resize.observe(container);
    const events=new AbortController();
    container.addEventListener("pointerenter",()=>viewer.updateStatusMouseOnViewer(true),{signal:events.signal});
    container.addEventListener("pointerleave",()=>viewer.updateStatusMouseOnViewer(false),{signal:events.signal});
    const controls=viewer.getControlsManager?.()?.controls||viewer.controlsManager?.controls;
    const releaseInput=controls?installOrbitInput(container,controls):()=>{};
    const dispose=()=>{disposed=true;events.abort();releaseInput();resize.disconnect();viewer.remove?.();viewer.dispose?.();};
    try{
        // Native loaders infer format from a filename query or this explicit
        // name. Owned artifact routes have neither a filename nor an extension.
        const loadURL=module?.host?url+(url.includes('?')?'&':'?')+'filename='+encodeURIComponent(filename):url;
        const status=await viewer.loadModel(loadURL,filename,{silent:true});
        if(status&&status!=='loaded')throw Error('The mesh preview could not load: '+status);
        if(disposed)return dispose;
        viewer.handleResize();viewer.fitToViewer();
        // Apply the native viewer's intended light multiplier, which its bare
        // factory leaves unapplied until a UI control supplies the setting.
        viewer.setLightIntensity?.(3);
        // The native component normally emits this after mounting. Embedded
        // consumers must do so too, allowing Spark to repaint when its splat
        // buffers become paintable instead of leaving the first frame blank.
        viewer.emitModelReady?.();
        viewer.forceRender();
    }catch(error){dispose();throw error;}
    // The disposer also exposes the native viewer for an owning comparison
    // surface. Existing callers still own exactly one callable cleanup handle.
    dispose.viewer=viewer;
    return dispose;
}

// Recent native viewers turn every model URL into api/view. Keep that native
// loader while routing only this viewer's requested model to its owned file
// endpoint. Never patch the global host or expose arbitrary filesystem paths.
export function createModelHost(host,url,filename){
    return {...host,fetchApi:(route,options)=>{
        const request=new URL(route,'http://native.invalid/');
        if(/\/(?:api\/)?view$/.test(request.pathname)&&request.searchParams.get('filename')===filename)return fetch(url,options);
        return host.fetchApi(route,options);
    }};
}

// OrbitControls can retain a drag after the pointer leaves the embedded canvas.
// Gate camera input by real button state so a subsequent hover cannot move it.
export function installOrbitInput(container,controls,windowTarget=window){
    const events=new AbortController();
    const options={capture:true,signal:events.signal};
    let releaseTimer;
    const stop=()=>{controls.enabled=false;};
    // Run after native pointer/wheel handlers, including when Comfy captures
    // the event. A microtask can run between browser event listeners.
    const afterInput=()=>{clearTimeout(releaseTimer);releaseTimer=setTimeout(stop,0);};
    controls.autoRotate=false;controls.enableDamping=false;stop();
    container.addEventListener("pointerdown",event=>{
        controls.enabled=event.pointerType==="touch"||event.button===0||event.button===2;
    },options);
    container.addEventListener("pointermove",event=>{
        if(event.pointerType!=="touch"&&event.buttons===0)stop();
    },options);
    container.addEventListener("pointerleave",event=>{if(event.buttons===0)stop();},options);
    for(const type of ["pointerup","pointercancel"])
        windowTarget.addEventListener(type,afterInput,options);
    windowTarget.addEventListener("blur",stop,{signal:events.signal});
    container.addEventListener("wheel",()=>{controls.enabled=true;afterInput();},options);
    return ()=>{clearTimeout(releaseTimer);stop();events.abort();};
}
