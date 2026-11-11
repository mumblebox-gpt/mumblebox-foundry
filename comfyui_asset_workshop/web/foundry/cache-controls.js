import {sourceMessage} from "./i18n.js";
import {msg, setText, bindAttribute, replaceContent} from "./i18n.js";
import {el,button,hint,icon} from './dom.js';
import {request} from './services.js';
const size=bytes=>bytes>=1024**3?(bytes/1024**3).toFixed(2)+' GB':bytes>=1024**2?(bytes/1024**2).toFixed(1)+' MB':bytes>=1024?(bytes/1024).toFixed(1)+' KB':bytes+' B';
import {maintenanceBusy} from './maintenance-state.js';
export function cacheControls(shell){
    let working=false,preview=null,selected=new Set();const status=el('p',{class:'muted',role:'status','aria-live':'polite'}),review=el('div',{class:'cache-review'});
    const control=button([icon('trash',18),msg("common.purge_cache")],async()=>{
        working=true;draw();setText(status, msg("common.checking_disposable_files"));review.replaceChildren();
        try{preview=await request('cache/preview',{});
            setText(status, msg("common.disposable_files", {count: preview.count, value2: size(preview.bytes), value3: preview.truncated?' · first batch; preview again after clearing':''}));
            if(preview.count){
                selected=new Set(preview.groups.filter(g=>g.count).map(g=>g.name));
                const confirm=button(msg("common.clear_these_files", {count: preview.count}),async()=>{
                    working=true;draw();confirm.disabled=true;
                    try{const result=await request('cache/purge',{token:preview.token,groups:[...selected]});review.replaceChildren();setText(status, msg("common.cleared_files_freed", {removed: result.removed, value2: size(result.bytes), value3: result.skipped?' Changed or missing files were kept.':'', value4: result.failures.length?' '+result.failures.length+' files could not be cleared.':''}));}
                    catch(e){setText(status, sourceMessage(e.message));}
                    finally{working=false;draw();}
                },{class:'danger','data-cache-confirm':'true'});
                replaceContent(review, el('ul',{class:'cache-groups'},...preview.groups.filter(g=>g.count).map(g=>el('li',{},el('label',{class:'check-row',title:g.root},el('input',{type:'checkbox',checked:true,'aria-label':msg("common.clear", {name: g.name}),onchange:e=>{if(e.target.checked)selected.add(g.name);else selected.delete(g.name);draw();}}),el('span',{},msg("common.files", {name: g.name, count: g.count, value3: size(g.bytes)})))))), el('details',{},el('summary',{},msg("common.review_exact_files")),el('textarea',{readOnly:true,rows:6,'aria-label':msg("common.cache_files_to_clear"),value:preview.files.map(f=>f.path+' · '+size(f.bytes)).join('\n')})), hint(msg("common.incomplete_downloads_will_start_again_when_needed_this_action_cannot_restore")), el('div',{class:'actions'},confirm,button(msg("common.keep_cache"),()=>{preview=null;review.replaceChildren();setText(status, msg("common.cache_kept"));})));
            }
        }catch(e){setText(status, sourceMessage(e.message));}finally{working=false;draw();}
    });
    function draw(){const fileList=review.querySelector('[data-i18n-control="common.cache_files_to_clear"]');if(fileList&&preview)fileList.value=preview.files.filter(f=>selected.has(f.group)).map(f=>f.path+' · '+size(f.bytes)).join('\n');const busy=maintenanceBusy(shell.status);control.disabled=busy||working;bindAttribute(control, "title", busy?msg("common.wait_for_processing_and_downloads_to_finish"):msg("common.review_temporary_files_and_incomplete_downloads_before_clearing"));const c=review.querySelector('[data-cache-confirm]');if(c){const groups=preview.groups.filter(g=>selected.has(g.name)),count=groups.reduce((n,g)=>n+g.count,0);setText(c, msg("common.clear_selected_files", {count: count}));c.disabled=busy||working||!count;}}
    shell.statusListeners.add(draw);draw();
    return {element:el('section',{class:'settings-section cache-settings'},el('div',{class:'section-heading'},el('h3',{},msg("common.temporary_files")),control),
        hint(msg("common.free_space_used_by_temporary_previews_worker_scratch_and_unfinished_download")),
        el('details',{},el('summary',{},msg("common.what_is_kept")),hint(msg("common.completed_outputs_and_packages_editable_quad_results_material_edits_model_we"))),
        status,review),dispose(){shell.statusListeners.delete(draw);}};
}
