import {msg, setText} from "../i18n.js";
import {el,button,hint,field} from '../dom.js';
import {dialog} from '../dialogs.js';
import {request} from '../services.js';

export function galleryReference(creationId, side, revisionId) {
    return request('images/'+creationId+'/handoff',{mode:'single',side,revision_id:revisionId});
}

export const inputURL=name=>{const parts=name.split('/');return '/view?'+new URLSearchParams({filename:parts.pop(),subfolder:parts.join('/'),type:'input'});};

export async function uploadReference(file){
    if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error(msg("images.use_png_jpeg_or_webp"));
    if(file.size>20*1024**2)throw Error(msg("images.use_an_image_smaller_than_20_mb"));
    const body=new FormData();body.append('image',file);body.append('subfolder','foundry-references');body.append('overwrite','false');
    const response=await fetch('/upload/image',{method:'POST',body});const data=await response.json();
    if(!response.ok)throw Error(data.error||'The image could not be uploaded.');
    return {id:crypto.randomUUID(),filename:(data.subfolder?data.subfolder+'/':'')+data.name,role:'detail',description:''};
}

export function capturePhoto(shell,onPhoto){
    let stream,closed=false,capture,url;
    const video=el('video',{autoplay:true,playsInline:true,muted:true,class:'webcam-preview'});
    const preview=el('img',{class:'webcam-preview',alt:msg("images.captured_reference"),hidden:true});
    const status=hint(msg("images.starting_camera"));
    const stop=()=>stream?.getTracks().forEach(track=>track.stop());
    const modal=dialog(shell,msg("images.take_a_reference_photo"),el('div',{},video,preview,status),[
        {label:msg("images.retake"),run:()=>{capture=null;preview.hidden=true;video.hidden=false;setText(status, msg("images.frame_the_subject_then_capture"));}},
        {label:msg("images.capture"),run:async()=>{
            if(!video.videoWidth)return;
            const canvas=document.createElement('canvas');canvas.width=video.videoWidth;canvas.height=video.videoHeight;
            canvas.getContext('2d').drawImage(video,0,0);
            capture=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
            if(url)URL.revokeObjectURL(url);url=URL.createObjectURL(capture);preview.src=url;
            preview.hidden=false;video.hidden=true;setText(status, msg("images.keep_this_photo_or_retake_it"));
        }},
        {label:msg("images.use_photo"),primary:true,run:async close=>{
            if(!capture){setText(status, msg("images.capture_a_photo_first"));return;}
            await onPhoto(new File([capture],'camera-'+Date.now()+'.png',{type:'image/png'}));close();
        }}]);
    modal.surface.addEventListener('foundry-close',()=>{closed=true;stop();if(url)URL.revokeObjectURL(url);});
    navigator.mediaDevices.getUserMedia({video:true,audio:false}).then(value=>{
        stream=value;if(closed){stop();return;}video.srcObject=stream;setText(status, msg("images.frame_a_face_object_or_drawing_no_audio_is_recorded"));
    }).catch(error=>{setText(status, msg("images.camera_unavailable_file_upload_is_still_available", {message: error.message}));});
}

export function referenceControls(c){
    const add=async files=>{for(const file of files){
        if(c.draft.references.length>=c.referenceLimit())throw Error(msg("images.this_model_allows_references_for_this_creation", {value1: c.referenceLimit()}));
        c.draft.references.push(await uploadReference(file));c.remember();
    }};
    const input=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',multiple:true,hidden:true,
        onchange:e=>c.act(()=>add(e.target.files))});
    const list=c.draft.references.map((ref,index)=>el('article',{class:'creator-reference'},el('img',{src:inputURL(ref.filename),alt:msg("images.reference", {value1: index+1})}),
        el('div',{},field(msg("images.image_purpose", {value1: index+1}),el('select',{value:ref.role,onchange:e=>{ref.role=e.target.value;c.remember();}},
            ...['detail','front','back','face','body','accessory','style','material'].map(role=>el('option',{value:role,selected:role===ref.role},role)))),
            field(msg("images.what_this_reference_contributes"),el('textarea',{rows:2,value:ref.description,maxLength:2000,placeholder:msg("images.for_example_wear_this_backpack"),oninput:e=>{ref.description=e.target.value;c.remember();}}))),
        el('div',{class:'actions'},index?button(msg("images.move_earlier"),()=>{[c.draft.references[index-1],c.draft.references[index]]=[ref,c.draft.references[index-1]];c.remember();c.render();}):null,
            button(msg("images.remove"),()=>{c.draft.references.splice(index,1);c.remember();c.render();}))));
    return el('div',{},input,el('div',{class:'creator-drop',ondragover:e=>e.preventDefault(),ondrop:e=>{e.preventDefault();c.act(()=>add(e.dataTransfer.files));}},
        el('div',{class:'actions'},button(msg("images.upload_references"),()=>input.click()),button(msg("images.take_a_photo_with_connected_camera"),()=>capturePhoto(c.shell,file=>c.act(()=>add([file]))),{disabled:!navigator.mediaDevices})),
        hint(msg("images.drop_images_here_references_describe_each_image_so_the_model_knows_its_purpo", {value1: c.draft.references.length, value2: c.referenceLimit()}))),...list);
}
