import {api} from '/scripts/api.js';
import {el} from '../dom.js';
import {msg,sourceMessage} from '../i18n.js';

export function orbitMedia(run,samplerId,playing=false){
    if(run?.active&&run.stage==='orbit'){
        const preview=el('img',{class:'turntable-sheet',alt:msg('orbit.live_preview'),hidden:true});
        const panel=el('figure',{class:'orbit-live-preview',hidden:true},
            preview,el('figcaption',{class:'muted'},msg('orbit.live_preview')));
        let url;
        const receive=({detail})=>{
            if(!detail||String(detail.nodeId)!==String(samplerId)||!run.pending||
                detail.jobId!==run.pending.prompt_id||!(detail.blob instanceof Blob))return;
            if(url)URL.revokeObjectURL(url);
            url=URL.createObjectURL(detail.blob);
            preview.src=url;
            preview.hidden=false;
            panel.hidden=false;
        };
        api.addEventListener('b_preview_with_metadata',receive);
        return {element:panel,release:()=>{
            api.removeEventListener('b_preview_with_metadata',receive);
            if(url)URL.revokeObjectURL(url);
        }};
    }
    const url=run?.previews?.orbit;
    if(!url)return {element:null};
    const video=el('video',{src:url,controls:true,loop:playing,playsInline:true,preload:'metadata',
        muted:true,defaultMuted:true,'aria-label':sourceMessage('Generated 360-degree orbit')});
    video.autoplay=playing;
    if(playing)queueMicrotask(()=>{if(video.isConnected)video.play().catch(()=>{});});
    return {element:video};
}
