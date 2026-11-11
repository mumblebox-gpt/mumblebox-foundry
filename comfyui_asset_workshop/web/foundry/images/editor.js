import {msg} from "../i18n.js";
import {openImageEditor} from '../../image-editor.js';
import {el} from '../dom.js';
import {request} from '../services.js';
import {showImageStage} from './graph.js';

export async function editImage(c,side){
    const image=c.revision(side),other=c.revision(side==='front'?'back':'front');
    if(!image)throw Error(msg("images.generate_this_image_before_opening_the_editor"));
    const scroll=c.shell.content.scrollTop;
    const download=revision=>el('a',{href:revision.url,download:c.draft.name+'-'+revision.side+'.png'},msg("images.download", {side: revision.side}));
    const modal=await openImageEditor({element:el,sourceURL:image.url,title:c.draft.name+' · '+side,
        model:c.cap.models.find(m=>m.id===c.run.config.model)?.label||c.run.config.model,container:c.shell.root,comparison:other?{url:other.url,label:other.side}:null,
        onSwitch:other?()=>editImage(c,other.side):null,download:()=>download(image),
        progress:()=>({message:c.run?.dependency?.phase==='downloading'?'The model is downloading on first use. This may take some time but only happens once per model.':c.run?.stage}),
        stop:()=>request('images/'+c.id+'/cancel',{}),
        generate:async options=>{
            const form=new FormData();form.append('mask',options.mask,'selection.png');
            form.append('options',JSON.stringify({side,source_id:image.id,prompt:options.prompt,feather:options.feather,replace_detail:options.replaceDetail}));
            const response=await fetch('/mumblebox-foundry/v1/images/'+c.id+'/edit',{method:'POST',body:form});const prepared=await response.json();
            if(!response.ok)throw Error(prepared.error||'The edit could not be prepared.');
            c.run=await request('images/'+c.id+'/start',{operation:'edit',request_id:crypto.randomUUID()});
            while(c.run.active){await new Promise(resolve=>setTimeout(resolve,1000));c.run=await request('images/'+c.id);showImageStage(c.run,c.node);}
            if(c.run.status!=='complete')throw Error(c.run.error||'The edit did not finish.');
            const revision=c.run.revisions.find(r=>r.id===c.run.candidate);
            if(!revision)throw Error(msg("images.the_edit_completed_without_a_preview"));
            return {...revision,recipe:revision.provenance,download:download(revision)};
        },
        accept:async candidate=>{c.run=await request('images/'+c.id+'/accept',{revision_id:candidate.id,expected:image.id});c.render();}
    });
    modal.addEventListener('close',()=>{c.render();c.shell.content.scrollTop=scroll;});
}
