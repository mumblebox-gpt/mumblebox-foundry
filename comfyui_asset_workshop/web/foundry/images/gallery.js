import {sourceMessage} from "../i18n.js";
import {dateTime, msg, pluralMessage, setText, replaceContent} from "../i18n.js";
import {el,button,hint,field} from '../dom.js';
import {request} from '../services.js';
import {dialog} from '../dialogs.js';

export async function gallery(shell){
    const state=shell.imageGalleryState??={search:'',category:'',kind:'all',sort:'newest',cursor:''};
    let disposed=false,sequence=0;const selected=new Set(),body=el('div',{}),more=el('div',{}),message=hint('');
    const cap=await request('images/capabilities');
    const categoryLabel = id => cap.categories.find(category => category.id === id)?.name ?? id;
    const revisionLabel = (view, timestamp) => msg("images.gallery_revision_summary", {
        view: msg("images.gallery_" + view), date: dateTime(timestamp * 1000, {timeStyle: "short"}),
    });
    const open=id=>{shell.openImageId=id;return shell.openImages('Create Images');};
    async function remove(ids){
        const files=el('input',{type:'checkbox'}),detail=hint(msg("images.saved_files_stay_on_disk_unless_you_select_the_separate_file_deletion_option"));
        dialog(shell,ids?msg("images.remove_selected_images"):msg("images.purge_image_gallery"),el('div',{},detail,
            el('label',{class:'gallery-actions'},files,msg("images.also_delete_this_creation_s_saved_image_files_copies_already_used_by_the_3d"))),[
            {label:msg("images.cancel"),run:close=>close()},
            {label:msg("images.review_removal"),run:async close=>{
                const review=await request('images/removal-preview',{ids,delete_files:files.checked});close();
                dialog(shell,msg("images.confirm_image_removal"),el('div',{},hint(msg("images.creations_image_revisions", {value1: review.entry_count, value2: review.image_count})),
                    hint(review.delete_files?msg("images.these_image_files_will_also_be_deleted"):msg("images.only_the_gallery_entries_will_be_removed"))),[
                    {label:msg("images.cancel"),run:done=>done()},
                    {label:review.delete_files?msg("images.delete_entries_and_files"):msg("images.remove_entries"),run:async done=>{await request('images/remove',{token:review.token});done();selected.clear();state.cursor='';await load();}}
                ]);
            }}]);
    }
    async function detail(id){
        const record=await request('images/'+id),sides=record.config.paired?['front','back']:['single'];
        const choices=sides.map(side=>{const revision=record.revisions.find(r=>r.id===record.accepted[side]);
            return el('figure',{class:'creator-frame'},el('figcaption',{},msg("images.gallery_" + side)),
                el('img',{src:revision.url,alt:msg("images.gallery_reference_alt", {
                    name: record.config.name, view: msg("images.gallery_" + side),
                })}),
                el('small',{},msg("images.px", {value1: revision.size.join(' × ')})));
        });
        dialog(shell,record.config.name,el('div',{},el('div',{class:'creator-pair','data-paired':String(record.config.paired)},...choices),
            hint(msg("images.gallery_revision_summary", {view: categoryLabel(record.config.category),
                date: dateTime(record.created * 1000, {timeStyle: "short"})})),
            el('details',{},el('summary',{},msg("images.revisions_and_generation_details")),...record.revisions.map(revision=>el('div',{class:'gallery-actions'},
                el('a',{href:revision.url,target:'_blank',rel:'noopener noreferrer'},revisionLabel(revision.side, revision.created)),
                el('span',{class:'badge'},record.accepted[revision.side]===revision.id?msg("images.current"):msg("images.retained_revision")),
                record.accepted[revision.side]!==revision.id?button(msg("images.restore_revision"),async()=>{await request('images/'+id+'/accept',{revision_id:revision.id,expected:record.accepted[revision.side]});await detail(id);}):null)),
                el('pre',{},JSON.stringify({model:record.config.model,settings:record.config.settings,loras:record.config.loras},null,2)))),[
            {label:msg("images.edit_continue"),primary:true,run:async close=>{close();await open(id);}},
            {label:msg("images.reuse_settings"),run:async close=>{const copy=await request('images/'+id+'/reuse',{});close();await open(copy.id);}},
            {label:msg("images.close"),run:close=>close()}]);
    }
    function card(item){
        const thumbs=Object.entries(item.accepted).map(([side,id])=>el('img',{src:'/mumblebox-foundry/v1/images/'+item.id+'/files/'+id,alt:msg("images.gallery_reference_alt", {name: item.name, view: msg("images.gallery_" + side)}),loading:'lazy'}));
        return el('article',{class:'image-gallery-card'},el('div',{class:'pair-thumbnails'},...thumbs),el('div',{class:'card-copy'},
            el('div',{class:'gallery-actions'},el('input',{type:'checkbox','aria-label':msg("images.select", {name: item.name}),checked:selected.has(item.id),onchange:e=>e.target.checked?selected.add(item.id):selected.delete(item.id)}),el('h3',{},item.name)),
            hint(msg("images.gallery_card_summary", {
                kind: msg(item.paired ? "images.gallery_pair" : "images.gallery_single"),
                category: categoryLabel(item.category),
            })),
            el('div',{class:'actions'},button(msg("images.view_edit"),()=>detail(item.id).catch(e=>shell.message(sourceMessage(e.message),true))),
                el('a',{href:'/mumblebox-foundry/v1/images/'+item.id+'/package',download:''},msg("images.download_images")),
                button(msg("images.delete"),()=>remove([item.id]).catch(e=>shell.message(sourceMessage(e.message),true)),{class:'danger'}))));
    }
    async function load(append=false){
        const current=++sequence;setText(message, msg("images.loading_images"));
        try{
            const result=await request('images?'+new URLSearchParams({...state,limit:24}));if(disposed||current!==sequence)return;
            if(!append)body.replaceChildren();body.append(...result.items.map(card));
            setText(message, body.childElementCount?pluralMessage("images.gallery_creation_count", body.childElementCount):msg("images.no_saved_creations_match_these_filters"));
            replaceContent(more, result.next_cursor?button(msg("images.load_more"),()=>{state.cursor=result.next_cursor;load(true);}):'');
        }catch(error){setText(message, sourceMessage(error.message));}
    }
    const filter=(key,label,choices)=>field(label,el('select',{onchange:e=>{state[key]=e.target.value;state.cursor='';load();}},
        ...choices.map(([value,name])=>el('option',{value,selected:state[key]===value},name))));
    const search=el('input',{value:state.search,placeholder:msg("images.search_image_names"),'aria-label':msg("images.search_image_names"),onchange:e=>{state.search=e.target.value;state.cursor='';load();}});
    const host=el('section',{},el('div',{class:'gallery-actions'},button(msg("images.create_images"),()=>shell.openImages('Create Images'),{class:'primary'}),button(msg("images.refresh"),()=>{state.cursor='';load();}),
        button(msg("images.remove_selected"),()=>{if(!selected.size){setText(message, msg("images.select_at_least_one_creation"));return;}remove([...selected]);}),button(msg("images.purge_gallery"),()=>remove(null),{class:'danger'})),
        el('div',{class:'gallery-filters'},field(msg("images.search"),search),filter('category',msg("images.category"),[['',msg("images.all_categories")],...cap.categories.map(c=>[c.id,c.name])]),
            filter('kind',msg("images.image_set"),[['all',msg("images.all")],['pair',msg("images.front_back_pairs")],['single',msg("images.single_images")]]),filter('sort',msg("images.order"),[['newest',msg("images.newest_first")],['oldest',msg("images.oldest_first")]])),message,body,more);
    body.className='image-gallery-grid';state.cursor='';await load();
    return {element:host,dispose(){disposed=true;sequence++;shell.imageGalleryScroll=shell.content.scrollTop;}};
}
