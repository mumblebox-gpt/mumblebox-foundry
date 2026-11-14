import {sourceMessage} from "../i18n.js";
import {currentLanguage, msg, pluralMessage, setText} from "../i18n.js";
import {el,button,hint} from '../dom.js';
import {request} from '../services.js';
const size=n=>n>=1024**3?(n/1024**3).toFixed(2)+' GB':(n/1024**2).toFixed(1)+' MB';
const sortKey = 'mumblebox-foundry/model-sort';
const sortOrders = {
    name_asc: msg("common.name_a_z"), name_desc: msg("common.name_z_a"),
    size_desc: msg("common.size_largest_first"), size_asc: msg("common.size_smallest_first"),
    date_desc: msg("common.date_added_newest_first"), date_asc: msg("common.date_added_oldest_first"),
};
export function resourceLists(shell){
    let disposed=false,cursor=0;
    const lists=el('ul',{class:'resource-rows'}),feedback=el('p',{role:'status',class:'muted'});
    const refresh=button(msg("common.refresh_list"),()=>load(true)),more=button(msg("common.show_more_models"),()=>load(false),{hidden:true});
    const sort = el('select', {onchange: async () => {
        try {
            shell.data.preferences = await request('preferences', {model_sort:sort.value}, {method:'PATCH'});
            localStorage.removeItem(sortKey);
            await load(true);
        } catch (error) { setText(feedback, sourceMessage(error.message)); }
    }}, Object.entries(sortOrders).map(([value, label]) => el('option', {value}, label)));
    const savedSort = shell.data?.preferences?.model_sort ?? localStorage.getItem(sortKey);
    sort.value = Object.hasOwn(sortOrders, savedSort) ? savedSort : 'name_asc';
    const open = button(msg("common.open_models_folder"), async () => {
        try {await request('resources/open-folder', {});}
        catch (error) {setText(feedback, sourceMessage(error.message));}
    });
    const root=el('section',{},el('div',{class:'section-heading'},
        el('h3',{},msg("common.installed_models")),
        el('div',{class:'resource-list-tools'},el('label',{},msg("common.sort_models"),sort),refresh,open)),
        hint(msg("common.models_across_comfyui_and_registered_workflow_runtimes_deleting_weights_pres")),feedback,lists,more);
    async function load(reset=false){
        refresh.disabled=true;more.disabled=true;sort.disabled=true;if(reset){cursor=0;lists.replaceChildren();}
        try{
            const query = new URLSearchParams({cursor, limit: 100, sort: sort.value});
            const data=await request('resources?' + query);if(disposed)return;
            const count = pluralMessage("common.model_file_count", data.total);
            setText(feedback, data.truncated ? msg("common.model_inventory_limited", {count}) : count);
            const dateFormat=new Intl.DateTimeFormat(currentLanguage(),{dateStyle:'medium'});
            for(const item of data.items){
                const added = Number.isFinite(item.added_at)
                    ? msg('common.model_added',{date:dateFormat.format(item.added_at * 1000)}) : msg('common.model_date_unknown');
                const details=el('div',{class:'installed-model-details'},el('strong',{},item.display_name||item.name),
                    item.display_name&&item.display_name!==item.name?el('div',{class:'filename'},msg('common.model_file',{name:item.name})):null,
                    el('small',{class:'muted'},size(item.bytes)+' · '+item.location+' · ',added),
                    hint(item.workflows.length?msg("common.used_by", {value1: item.workflows.join(', ')}):msg("common.available_to_installed_workflows_origin_is_not_recorded")),item.reason?hint(item.reason):null);
                const row=el('li',{},details);
                const remove=button(msg("common.delete"),async()=>{
                    remove.disabled=true;
                    try{
                        const p=await request('resources/delete-preview',{id:item.id});
                        const confirmation=el('div',{class:'resource-confirm'},hint(msg("common.delete_2", {value1: p.exact_path, value2: size(p.bytes)})),
                            hint(p.workflows.length?msg("common.affected_workflows", {value1: p.workflows.join(', ')}):msg("common.other_workflows_may_use_this_file")),
                            p.shared_links>1?hint(msg("common.other_hard_links_remain_and_may_retain_this_file_s_disk_space")):null,
                            p.symlink?hint(msg("common.this_removes_the_selected_cache_link_its_shared_data_remains_available_to_ot")):null,
                            hint(p.download_known?msg("common.the_workflow_prepares_missing_published_resources_again_when_needed"):msg("common.no_download_source_is_recorded_for_this_custom_model_keep_its_source_if_you")),
                            button(msg("common.cancel"),()=>{confirmation.remove();remove.disabled=false;}),
                            button(msg("common.delete_file"),async()=>{try{await request('resources/delete',{token:p.token});shell.message(msg("common.deleted", {name: item.name}));await load(true);}catch(e){setText(feedback, sourceMessage(e.message));await load(true);}},{class:'danger'}));
                        row.append(confirmation);
                    }catch(e){setText(feedback, sourceMessage(e.message));remove.disabled=!item.deletable;}
                },{class:'danger',disabled:!item.deletable,title:item.reason||'Review deletion of this model'});
                row.append(remove);lists.append(row);
            }
            cursor=data.next_cursor;more.hidden=cursor===null;
        }catch(e){if(!disposed)setText(feedback, sourceMessage(e.message));}
        finally{refresh.disabled=false;more.disabled=false;sort.disabled=false;}
    }
    load(true);return {element:root,dispose:()=>{disposed=true;}};
}
