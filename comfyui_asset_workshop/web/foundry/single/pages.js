import {el,button,hint,field} from '../dom.js';
import {capturePhoto,uploadReference,inputURL} from '../images/references.js';
import {dialog} from '../dialogs.js';
import {request} from '../services.js';
import {optionsPage} from '../wizard/pages.js';
async function replace(w,file){if(!file)return;w.draft.references=[{...await uploadReference(file),role:'primary'}];delete w.draft.image_creation;w.remember();}
async function gallery(w){
    const list=el('div',{class:'hair-gallery'}),status=el('p',{role:'status',class:'muted'}),more=button('Load more',()=>load()),modal=dialog(w.shell,'Choose your reference',el('div',{},list,status,more));
    let cursor='',loading=false;
    async function load(){
        if(loading)return;loading=true;more.disabled=true;status.textContent='Loading saved images…';
        try{
            const data=await request('images?'+new URLSearchParams({limit:24,...(cursor?{cursor}:{})}));
            for(const item of data.items||[])for(const [side,id] of Object.entries(item.accepted||{})){
                const url='/mumblebox-foundry/v1/images/'+item.id+'/files/'+id;
                list.append(button([el('img',{src:url,alt:item.name+' '+side,loading:'lazy'}),el('span',{},item.name+' · '+side)],()=>w.act(async()=>{
                    const r=await fetch(url);if(!r.ok)throw Error('Saved image unavailable.');
                    const blob=await r.blob(),type=blob.type||'image/png',ext=type==='image/webp'?'webp':type==='image/jpeg'?'jpg':'png';
                    await replace(w,new File([blob],'gallery-'+id+'.'+ext,{type}));modal.close();
                })));
            }
            cursor=data.next_cursor||'';more.hidden=!cursor;status.textContent=list.children.length?'':'No saved images yet. Create an image or upload one.';
        }catch(error){status.textContent=error.message;more.hidden=false;more.textContent='Retry';}
        finally{loading=false;more.disabled=false;}
    }
    await load();
}
export function singleInputPage(w){
    const file=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,'aria-label':'Upload single reference',onchange:e=>w.act(()=>replace(w,e.target.files[0]))});
    const ref=w.draft.references[0];
    return el('div',{},hint('One image is all you need. A three-quarter view shows more of the shape; keep the complete subject in frame.'),
        field('Asset name',el('input',{value:w.draft.name,maxLength:100,placeholder:'Name this asset','aria-label':'Asset name',oninput:e=>{w.draft.name=e.target.value;w.remember();}})),file,
        el('div',{class:'upload-zone',ondragover:e=>{e.preventDefault();e.currentTarget.classList.add('dragging');},ondragleave:e=>e.currentTarget.classList.remove('dragging'),ondrop:e=>{
            e.preventDefault();e.currentTarget.classList.remove('dragging');if(e.dataTransfer.files.length!==1){w.error='Drop exactly one image.';w.render();return;}w.act(()=>replace(w,e.dataTransfer.files[0]));}},
            el('strong',{},ref?'Your starting image':'Drop an image here'),
            ref?w.image(inputURL(ref.filename),'Starting reference'):hint('PNG, JPEG or WebP · Up to 20 MB'),
            el('div',{class:'actions'},button(ref?'Replace image':'Upload image',()=>file.click()),
                button('Take a photo',()=>capturePhoto(w.shell,f=>w.act(()=>replace(w,f))),{disabled:!navigator.mediaDevices}),
                button('Choose from Gallery',()=>gallery(w)),
                button('Create Image',()=>{w.remember();w.shell.imageOrigin={method:'single-image',sessionId:w.sessionId};w.shell.openImages('Create Images');},{class:'primary'}))),
        hint('No image? Create one from a description, then choose Use in 3D to return here. Text is used by the image creator; Pixal3D receives your chosen image.'),
        el('details',{},el('summary',{},'How this method works'),hint('Pixal3D by Tencent ARC builds geometry from one view using the official ComfyUI recipe. Hi3D refines it against your reference, then Foundry cleans and textures the finished shape. Hidden surfaces are inferred.')),
        w.nav({next:async()=>{if(!w.draft.references.length)throw Error('Choose or create an image first.');w.go(2);}}));
}
export function singleOptionsPage(w){
    const page=optionsPage(w);
    page.firstChild.textContent='Pixal3D builds from your one reference. Hi3D refines the initial mesh using that same original image, followed by geometry cleanup.';
    page.insertBefore(field('Geometry seed',el('input',{type:'number',value:w.draft.overrides.shape_seed??42,min:0,max:9007199254740976,'aria-label':'Geometry seed',onchange:e=>{w.draft.overrides.shape_seed=Number(e.target.value);w.remember();}}),'Keep the seed fixed to compare settings.'),page.lastChild);
    return page;
}
