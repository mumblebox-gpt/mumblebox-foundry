import {el,button,hint,icon} from './dom.js';
import {request} from './services.js';
const size=bytes=>bytes>=1024**3?(bytes/1024**3).toFixed(2)+' GB':bytes>=1024**2?(bytes/1024**2).toFixed(1)+' MB':bytes>=1024?(bytes/1024).toFixed(1)+' KB':bytes+' B';
import {maintenanceBusy} from './maintenance-state.js';
export function cacheControls(shell){
    let working=false,preview=null,selected=new Set();const status=el('p',{class:'muted',role:'status','aria-live':'polite'}),review=el('div',{class:'cache-review'});
    const control=button([icon('trash',18),'Purge Cache'],async()=>{
        working=true;draw();status.textContent='Checking disposable files…';review.replaceChildren();
        try{preview=await request('cache/preview',{});
            status.textContent=preview.count+' disposable files · '+size(preview.bytes)+(preview.truncated?' · first batch; preview again after clearing':'');
            if(preview.count){
                selected=new Set(preview.groups.filter(g=>g.count).map(g=>g.name));
                const confirm=button('Clear these '+preview.count+' files',async()=>{
                    working=true;draw();confirm.disabled=true;
                    try{const result=await request('cache/purge',{token:preview.token,groups:[...selected]});review.replaceChildren();status.textContent='Cleared '+result.removed+' files · '+size(result.bytes)+' freed.'+(result.skipped?' Changed or missing files were kept.':'')+(result.failures.length?' '+result.failures.length+' files could not be cleared.':'');}
                    catch(e){status.textContent=e.message;}
                    finally{working=false;draw();}
                },{class:'danger','data-cache-confirm':'true'});
                review.replaceChildren(el('ul',{class:'cache-groups'},...preview.groups.filter(g=>g.count).map(g=>el('li',{},el('label',{class:'check-row',title:g.root},el('input',{type:'checkbox',checked:true,'aria-label':'Clear '+g.name,onchange:e=>{if(e.target.checked)selected.add(g.name);else selected.delete(g.name);draw();}}),el('span',{},g.name+': '+g.count+' files · '+size(g.bytes)))))),
                    el('details',{},el('summary',{},'Review exact files'),el('textarea',{readOnly:true,rows:6,'aria-label':'Cache files to clear',value:preview.files.map(f=>f.path+' · '+size(f.bytes)).join('\n')})),
                    hint('Incomplete downloads will start again when needed. This action cannot restore cleared cache files.'),
                    el('div',{class:'actions'},confirm,button('Keep cache',()=>{preview=null;review.replaceChildren();status.textContent='Cache kept.';})));
            }
        }catch(e){status.textContent=e.message;}finally{working=false;draw();}
    });
    function draw(){const fileList=review.querySelector('[aria-label="Cache files to clear"]');if(fileList&&preview)fileList.value=preview.files.filter(f=>selected.has(f.group)).map(f=>f.path+' · '+size(f.bytes)).join('\n');const busy=maintenanceBusy(shell.status);control.disabled=busy||working;control.title=busy?'Wait for processing and downloads to finish':'Review temporary files and incomplete downloads before clearing';const c=review.querySelector('[data-cache-confirm]');if(c){const groups=preview.groups.filter(g=>selected.has(g.name)),count=groups.reduce((n,g)=>n+g.count,0);c.textContent='Clear '+count+' selected files';c.disabled=busy||working||!count;}}
    shell.statusListeners.add(draw);draw();
    return {element:el('section',{class:'settings-section cache-settings'},el('div',{class:'section-heading'},el('h3',{},'Temporary files'),control),
        hint('Free space used by temporary previews, worker scratch and unfinished downloads. Saved assets, references, models and settings are protected.'),
        el('details',{},el('summary',{},'What is kept?'),hint('Completed outputs and packages, editable quad results, material edits, model weights and your settings. This only clears registered Foundry/Comfy temporary areas; it does not sweep other apps or system folders.')),
        status,review),dispose(){shell.statusListeners.delete(draw);}};
}
