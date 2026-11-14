import {el,button,field,hint} from '../dom.js';
import {setText,sourceMessage} from '../i18n.js';
import {request} from '../services.js';
import {label} from './pair-preview.js';

function loadImage(source) {
    const image=new Image();
    image.src=source;
    return image.decode().then(()=>image);
}

function meshBand(mesh, bounds, lower, upper, amount) {
    const restore=[];
    const height=bounds.max.y-bounds.min.y;
    const lo=bounds.min.y+height*lower;
    const hi=bounds.min.y+height*upper;
    const feather=height*.035;
    mesh.traverse(child=>{
        if(!child.isMesh||!child.material)return;
        const original=child.material;
        const band=source=>{
            const material=source.clone();
            material.transparent=true;
            material.depthWrite=true;
            material.onBeforeCompile=shader=>{
                shader.vertexShader='varying float foundryHeight;\n'+shader.vertexShader;
                shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>',
                    '#include <project_vertex>\nfoundryHeight = (modelMatrix * vec4(transformed, 1.0)).y;');
                shader.fragmentShader='varying float foundryHeight;\n'+shader.fragmentShader;
                shader.fragmentShader=shader.fragmentShader.replace('#include <alphatest_fragment>',
                    '#include <alphatest_fragment>\n'+
                    'diffuseColor.a *= '+amount.toFixed(5)+' * smoothstep('+lo.toFixed(6)+','+(lo+feather).toFixed(6)+',foundryHeight)'+
                    ' * (1.0 - smoothstep('+(hi-feather).toFixed(6)+','+hi.toFixed(6)+',foundryHeight));\n'+
                    'if (diffuseColor.a < 0.001) discard;');
            };
            material.customProgramCacheKey=()=>[lo,hi,amount].join(':');
            return material;
        };
        const modified=Array.isArray(original)?original.map(band):band(original);
        child.material=modified;
        restore.push(()=>{
            child.material=original;
            for(const item of [modified].flat())item.dispose();
        });
    });
    return ()=>restore.forEach(fn=>fn());
}

function shot(pair, fraction) {
    const {camera,radius}=pair;
    const azimuth=Math.PI*2*fraction+Math.PI/5;
    const distance=radius*(2.35-.36*Math.sin(Math.PI*fraction)**2);
    const elevation=.23-.25*Math.sin(Math.PI*fraction)**2;
    return {...camera,position:camera.target.clone().add(camera.target.clone().set(
        Math.sin(azimuth)*distance,elevation*radius,Math.cos(azimuth)*distance))};
}

async function compose(pair,state,canvas) {
    const {width,height}=canvas;
    pair.mesh.viewer.setCameraState(state);
    pair.splat.viewer.setCameraState(state);
    // Wait for Spark to sort the splats for this exact camera before readback.
    const splat=pair.splat.viewer;
    await splat.sceneManager.whenSplatsSorted(splat.getCameraManager().activeCamera);
    const base=await splat.captureScene(width,height);
    const surface=await pair.mesh.viewer.captureScene(width,height);
    const [background,foreground]=await Promise.all([loadImage(base.scene),loadImage(surface.mask)]);
    const ctx=canvas.getContext('2d',{alpha:false});
    ctx.drawImage(background,0,0);
    ctx.drawImage(foreground,0,0);
}

export function hybridPanel(wizard) {
    const root=el('section',{class:'orbit-hybrid'});
    const canvas=el('canvas',{width:640,height:360,hidden:true,'aria-label':label('preview')});
    const status=el('p',{role:'status',class:'muted'});
    const progress=el('progress',{hidden:true,'aria-label':label('encoding')});
    const saved=wizard.hybridSettings??={low:30,high:67,amount:80};
    const controls=[];
    let pair,controller,closed=false;

    function adjust(key,min,max){
        const output=el('output',{},saved[key]+'%');
        const input=el('input',{type:'range',min,max,value:saved[key],oninput:event=>{
            saved[key]=event.currentTarget.valueAsNumber;
            output.value=saved[key]+'%';
            start.disabled=!pair||saved.high-saved.low<8;
            preview.disabled=start.disabled;
            setText(status,saved.high-saved.low<8?label('small_band'):'');
        }});
        controls.push(input);
        return field(el('span',{},label(key==='high'?'high_height':key),' ',output),input);
    }
    const start=button(label('export_video'),()=>render(true),{class:'primary',disabled:true});
    const preview=button(label('preview'),()=>render(false),{disabled:true});
    const stop=button(label('stop'),()=>controller?.abort(),{hidden:true});
    const videoUrl=wizard.run?.hybrid;
    root.append(el('h3',{},label('hybrid')),hint(label('hybrid_help')),status,
        el('div',{class:'orbit-hybrid-settings'},adjust('low',0,90),adjust('high',10,100),adjust('amount',0,100)),
        el('div',{class:'actions'},preview,start,stop),
        progress,canvas,
        videoUrl?el('video',{class:'orbit-hybrid-video',src:videoUrl,controls:true,playsInline:true,preload:'metadata','aria-label':label('hybrid')}):null,
        videoUrl?el('a',{href:videoUrl,download:'hybrid-orbit.mp4'},label('download_video')):null);
    const endpoint=()=>wizard.path('/hybrid');
    async function render(exportVideo){
        if(!pair||controller||saved.high-saved.low<8)return;
        const abort=new AbortController();
        controller=abort;
        const previous=pair.mesh.viewer.getCameraState();
        const mode=pair.mode();
        const restore=meshBand(pair.mesh.model,pair.bounds,saved.low/100,saved.high/100,saved.amount/100);
        pair.setLocked(true);
        pair.select('both');
        start.disabled=preview.disabled=true;
        controls.forEach(input=>input.disabled=true);
        stop.hidden=!exportVideo;
        let session,finished=false;
        try{
            if(!exportVideo){
                await compose(pair,previous,canvas);
                canvas.hidden=false;
                setText(status,label('hybrid_ready'));
                return;
            }
            session=await request(endpoint(),{});
            const frameCanvas=el('canvas',{width:session.width,height:session.height});
            progress.hidden=false;progress.max=session.frames;progress.value=0;
            setText(status,label('encoding'));
            for(let index=0;index<session.frames;index++){
                abort.signal.throwIfAborted();
                await compose(pair,shot(pair,index/session.frames),frameCanvas);
                const jpeg=await new Promise(resolve=>frameCanvas.toBlob(resolve,'image/jpeg',.94));
                const response=await fetch('/mumblebox-foundry/v1/'+endpoint()+'/'+session.id+'/frames/'+index,
                    {method:'PUT',body:jpeg,signal:abort.signal});
                if(!response.ok)throw Error((await response.json()).error);
                progress.value=index+1;
                // Put progress on screen and allow the cancel button to respond.
                if(index%4===0)await new Promise(resolve=>setTimeout(resolve,0));
            }
            wizard.run=await request(endpoint()+'/'+session.id+'/finish',{});
            finished=true;
        }catch(error){
            if(!closed)setText(status,abort.signal.aborted?label('stopped'):label('export_error',{message:sourceMessage(error.message)}));
        }finally{
            if(session&&!finished)await request(endpoint()+'/'+session.id,undefined,{method:'DELETE'}).catch(()=>{});
            restore();
            controller=null;
            if(!closed){
                pair.select(mode||'both');
                pair.setLocked(false);
                pair.mesh.viewer.setCameraState(previous);
                pair.splat.viewer.setCameraState(previous);
                start.disabled=preview.disabled=false;
                controls.forEach(input=>input.disabled=false);
                stop.hidden=true;
                progress.hidden=true;
                if(finished)wizard.render();
            }
        }
    }
    wizard.previewDisposers.push(()=>{closed=true;controller?.abort();});
    return {root,ready:value=>{pair=value;start.disabled=preview.disabled=false;}};
}
