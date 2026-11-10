import {el,button,hint,field} from '../dom.js';
import {dialog} from '../dialogs.js';
import {request} from '../services.js';

export function galleryReference(creationId, side, revisionId) {
    return request('images/'+creationId+'/handoff',{mode:'single',side,revision_id:revisionId});
}

export const inputURL=name=>{const parts=name.split('/');return '/view?'+new URLSearchParams({filename:parts.pop(),subfolder:parts.join('/'),type:'input'});};

export async function uploadReference(file){
    if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error('Use PNG, JPEG or WebP.');
    if(file.size>20*1024**2)throw Error('Use an image smaller than 20 MB.');
    const body=new FormData();body.append('image',file);body.append('subfolder','foundry-references');body.append('overwrite','false');
    const response=await fetch('/upload/image',{method:'POST',body});const data=await response.json();
    if(!response.ok)throw Error(data.error||'The image could not be uploaded.');
    return {id:crypto.randomUUID(),filename:(data.subfolder?data.subfolder+'/':'')+data.name,role:'detail',description:''};
}

export function capturePhoto(shell,onPhoto){
    let stream,closed=false,capture,url;
    const video=el('video',{autoplay:true,playsInline:true,muted:true,class:'webcam-preview'});
    const preview=el('img',{class:'webcam-preview',alt:'Captured reference',hidden:true});
    const status=hint('Starting camera…');
    const stop=()=>stream?.getTracks().forEach(track=>track.stop());
    const modal=dialog(shell,'Take a reference photo',el('div',{},video,preview,status),[
        {label:'Retake',run:()=>{capture=null;preview.hidden=true;video.hidden=false;status.textContent='Frame the subject, then capture.';}},
        {label:'Capture',run:async()=>{
            if(!video.videoWidth)return;
            const canvas=document.createElement('canvas');canvas.width=video.videoWidth;canvas.height=video.videoHeight;
            canvas.getContext('2d').drawImage(video,0,0);
            capture=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
            if(url)URL.revokeObjectURL(url);url=URL.createObjectURL(capture);preview.src=url;
            preview.hidden=false;video.hidden=true;status.textContent='Keep this photo, or retake it.';
        }},
        {label:'Use Photo',primary:true,run:async close=>{
            if(!capture){status.textContent='Capture a photo first.';return;}
            await onPhoto(new File([capture],'camera-'+Date.now()+'.png',{type:'image/png'}));close();
        }}]);
    modal.surface.addEventListener('foundry-close',()=>{closed=true;stop();if(url)URL.revokeObjectURL(url);});
    navigator.mediaDevices.getUserMedia({video:true,audio:false}).then(value=>{
        stream=value;if(closed){stop();return;}video.srcObject=stream;status.textContent='Frame a face, object or drawing. No audio is recorded.';
    }).catch(error=>{status.textContent='Camera unavailable: '+error.message+'. File upload is still available.';});
}

export function referenceControls(c){
    const add=async files=>{for(const file of files){
        if(c.draft.references.length>=c.referenceLimit())throw Error('This model allows '+c.referenceLimit()+' references for this creation.');
        c.draft.references.push(await uploadReference(file));c.remember();
    }};
    const input=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',multiple:true,hidden:true,
        onchange:e=>c.act(()=>add(e.target.files))});
    const list=c.draft.references.map((ref,index)=>el('article',{class:'creator-reference'},el('img',{src:inputURL(ref.filename),alt:'Reference '+(index+1)}),
        el('div',{},field('Image '+(index+1)+' purpose',el('select',{value:ref.role,onchange:e=>{ref.role=e.target.value;c.remember();}},
            ...['detail','front','back','face','body','accessory','style','material'].map(role=>el('option',{value:role,selected:role===ref.role},role)))),
            field('What this reference contributes',el('textarea',{rows:2,value:ref.description,maxLength:2000,placeholder:'For example: wear this backpack.',oninput:e=>{ref.description=e.target.value;c.remember();}}))),
        el('div',{class:'actions'},index?button('Move earlier',()=>{[c.draft.references[index-1],c.draft.references[index]]=[ref,c.draft.references[index-1]];c.remember();c.render();}):null,
            button('Remove',()=>{c.draft.references.splice(index,1);c.remember();c.render();}))));
    return el('div',{},input,el('div',{class:'creator-drop',ondragover:e=>e.preventDefault(),ondrop:e=>{e.preventDefault();c.act(()=>add(e.dataTransfer.files));}},
        el('div',{class:'actions'},button('Upload references',()=>input.click()),button('Take a photo with connected camera',()=>capturePhoto(c.shell,file=>c.act(()=>add([file]))),{disabled:!navigator.mediaDevices})),
        hint('Drop images here. '+c.draft.references.length+' / '+c.referenceLimit()+' references. Describe each image so the model knows its purpose.')),...list);
}
