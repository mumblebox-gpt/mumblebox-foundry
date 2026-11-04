import {openImageEditor} from '../../image-editor.js';
import {el} from '../dom.js';
import {uploadReference} from '../images/references.js';
import {request} from '../services.js';

export async function editConcept(w){
    const source=w.artifact('concept:sheet');if(!source)throw Error('Generate a concept sheet first.');
    const modal=await openImageEditor({element:el,sourceURL:source,title:'Concept turnaround · selected-area edit',
        model:'Qwen Image 2.1 · Union inpainting',container:w.shell.root,
        settingsSummary:'Using Qwen Image 2.1 Union inpainting, '+w.job.spec.enhancement_steps+' steps, CFG 1, and the enhancement seed. No LoRA is used. Try again chooses a new seed.',
        download:()=>el('a',{href:source,download:'original-concept-sheet.png'},'Save original sheet'),
        progress:()=>({message:w.job?.current_stage||'Editing selected concept area'}),
        stop:()=>request('guided/runs/'+w.id+'/action',{operation:'cancel'}),
        generate:async options=>{
            const file=new File([options.mask],'concept-selection.png',{type:'image/png'});const uploaded=await uploadReference(file);
            w.job=await request('guided/runs/'+w.id+'/concept-edit',{mask_filename:uploaded.filename,prompt:options.prompt,feather:options.feather,replace_detail:options.replaceDetail,
                seed:options.random?Math.floor(Math.random()*2**32):w.job.spec.enhancement_seed});
            while(w.job.active||w.job.status==='running'){
                await new Promise(resolve=>setTimeout(resolve,1200));w.job=await request('guided/runs/'+w.id);
            }
            if(w.job.concept_editor?.status!=='candidate')throw Error(w.job.error||'The edit did not produce a candidate.');
            return {id:w.job.concept_editor.id,url:w.artifact('concept:edit_candidate'),recipe:{seed:w.job.concept_editor.seed,mask:w.job.concept_editor.mask,unmasked_pixels_preserved:true},download:el('a',{href:w.artifact('concept:edit_candidate'),download:'edited-concept-sheet.png'},'Save edit candidate')};
        },
        accept:async()=>{w.job=await request('guided/runs/'+w.id+'/accept-concept-edit',{});w.outputs();w.render();}
    });
    modal.addEventListener('close',()=>w.render());
}
