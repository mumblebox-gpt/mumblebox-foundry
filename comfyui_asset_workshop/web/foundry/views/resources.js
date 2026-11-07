import {el,button,hint} from '../dom.js';
import {request} from '../services.js';
const size=n=>n>=1024**3?(n/1024**3).toFixed(2)+' GB':(n/1024**2).toFixed(1)+' MB';
export function resourceLists(shell){
    let disposed=false,cursor=0;
    const lists=el('ul',{class:'resource-rows'}),feedback=el('p',{role:'status',class:'muted'});
    const refresh=button('Refresh list',()=>load(true)),more=button('Show more models',()=>load(false),{hidden:true});
    const root=el('section',{},el('div',{class:'section-heading'},el('h3',{},'Installed models'),refresh),
        hint('Models across ComfyUI and registered workflow runtimes. Deleting weights preserves images, meshes and saved results. Required published models are prepared again before workflow processing.'),feedback,lists,more);
    async function load(reset=false){
        refresh.disabled=true;more.disabled=true;if(reset){cursor=0;lists.replaceChildren();}
        try{
            const data=await request('resources?cursor='+cursor+'&limit=100');if(disposed)return;
            feedback.textContent=data.total+' model files found'+(data.truncated?' · inventory limit reached.':'.');
            for(const item of data.items){
                const details=el('div',{},el('strong',{},item.name),el('small',{class:'muted'},size(item.bytes)+' · '+item.location),
                    hint(item.workflows.length?'Used by: '+item.workflows.join(', '):'Available to installed workflows; origin is not recorded.'),item.reason?hint(item.reason):null);
                const row=el('li',{},details);
                const remove=button('Delete',async()=>{
                    remove.disabled=true;
                    try{
                        const p=await request('resources/delete-preview',{id:item.id});
                        const confirmation=el('div',{class:'resource-confirm'},hint('Delete '+p.exact_path+' ('+size(p.bytes)+')?'),
                            hint(p.workflows.length?'Affected workflows: '+p.workflows.join(', '):'Other workflows may use this file.'),
                            p.shared_links>1?hint('Other hard links remain and may retain this file’s disk space.'):null,
                            p.symlink?hint('This removes the selected cache link. Its shared data remains available to other cached models.'):null,
                            hint(p.download_known?'The workflow prepares missing published resources again when needed.':'No download source is recorded for this custom model. Keep its source if you will need it again.'),
                            button('Cancel',()=>{confirmation.remove();remove.disabled=false;}),
                            button('Delete file',async()=>{try{await request('resources/delete',{token:p.token});shell.message(item.name+' deleted.');await load(true);}catch(e){feedback.textContent=e.message;await load(true);}},{class:'danger'}));
                        row.append(confirmation);
                    }catch(e){feedback.textContent=e.message;remove.disabled=!item.deletable;}
                },{class:'danger',disabled:!item.deletable,title:item.reason||'Review deletion of this model'});
                row.append(remove);lists.append(row);
            }
            cursor=data.next_cursor;more.hidden=cursor===null;
        }catch(e){if(!disposed)feedback.textContent=e.message;}
        finally{refresh.disabled=false;more.disabled=false;}
    }
    load(true);return {element:root,dispose:()=>{disposed=true;}};
}
