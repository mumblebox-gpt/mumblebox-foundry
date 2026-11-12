import {sourceMessage} from "../i18n.js";
import {msg} from "../i18n.js";
import {modelAccessError} from "../connection-help.js";
import {el,button,hint,field,link} from '../dom.js';
import {request} from '../services.js';
import {referenceControls} from './references.js';
import {elapsedTime,workingStar} from '../activity.js';

export function creator(c){
    const draft=c.draft,model=c.model(),busy=!!c.run?.active;
    const text=(key,label,rows=3,placeholder='')=>field(label,el('textarea',{rows,value:draft[key]||'',maxLength:key==='description'?8000:4000,placeholder,
        oninput:e=>{draft[key]=e.target.value;c.remember();}}));
    const number=(key,label,step=1)=>field(label,el('input',{type:'number',step,value:draft.settings[key]??model.defaults[key],
        onchange:e=>{draft.settings[key]=Number(e.target.value);c.remember();}}));
    const category=el('select',{'aria-label':msg("images.image_category"),onchange:e=>{draft.category=e.target.value;c.remember();c.render();}},
        ...c.cap.categories.map(item=>el('option',{value:item.id,selected:item.id===draft.category},item.name)));
    const subject=el('fieldset',{disabled:busy},el('div',{class:'creator-columns'},
        field(msg("images.creation_name"),el('input',{value:draft.name,maxLength:100,oninput:e=>{draft.name=e.target.value;c.remember();}})),c.singleOrigin?hint(c.ccoreOrigin?msg("images.create_one_reference_for_your_ccore_prop_describe_the_image_you_want_below"):msg("images.one_reference_for_single_image_or_text_describe_any_subject_below")):field(msg("images.what_are_you_creating"),category)),
        hint(c.cap.categories.find(item=>item.id===draft.category)?.description),
        text('description',msg("images.describe_your_image"),4,msg("images.prompt_placeholder")),
        c.paired()?el('div',{class:'creator-columns'},text('front',msg("images.front_details_optional"),2,msg("images.front_placeholder")),text('back',msg("images.back_details_optional"),2,msg("images.back_placeholder"))):null,
        hint(c.paired()?msg("images.you_get_two_images_the_front_establishes_the_design_then_the_model_uses_it_t"):msg("images.this_creates_one_standalone_image_without_asset_framing_or_posing_instructio")));
    const selectedModel=el('select',{'aria-label':msg("images.image_creation_model"),onchange:e=>{
        draft.model=e.target.value;const chosen=c.model();draft.settings={...chosen.defaults,seed:draft.settings.seed??-1};draft.checkpoint='';
        draft.loras=draft.loras.filter(l=>c.loras.items?.some(i=>i.name===l.name&&i.profiles.includes(draft.model)));
        c.remember();c.render();
    }},...c.cap.models.map(m=>el('option',{value:m.id,selected:m.id===draft.model},m.label)));
    const checkpoints=(c.checkpoints.items||[]).filter(item=>item.kind==='Checkpoint'&&(item.profiles||[item.profile]).includes(draft.model));
    const checkpoint=el('select',{'aria-label':msg("images.installed_image_checkpoint"),onchange:e=>{draft.checkpoint=e.target.value;c.remember();}},el('option',{value:'',selected:!draft.checkpoint},msg("images.included_model")),
        ...checkpoints.map(item=>el('option',{value:String(item.file_id),selected:String(item.file_id)===draft.checkpoint},item.model_name||item.name||item.relative_path)));
    const compatible=(c.loras.items||[]).filter(item=>item.profiles.includes(draft.model));
    const loraSelect=el('select',{'aria-label':msg("images.available_compatible_loras")},el('option',{value:''},msg("images.choose_a_compatible_installed_lora")),...compatible.map(item=>el('option',{value:item.name},item.name)));
    const loraRows=draft.loras.map((item,index)=>el('div',{class:'creator-lora'},el('strong',{class:'filename'},item.name),
        field(msg("images.strength"),el('input',{type:'number',min:-3,max:3,step:.1,value:item.strength,onchange:e=>{item.strength=Number(e.target.value);item.strength_clip=item.strength;c.remember();}})),
        field(msg("images.trigger_words"),el('input',{value:item.trigger,maxLength:1000,oninput:e=>{item.trigger=e.target.value;c.remember();}})),
        button(msg("images.remove"),()=>{draft.loras.splice(index,1);c.remember();c.render();})));
    const modelPanel=el('fieldset',{disabled:busy},el('div',{class:'creator-columns'},field(msg("images.image_model"),selectedModel),field(msg("images.checkpoint"),checkpoint)),
        hint(model.help.purpose),link(model.license.label,model.license.url),
        model.source_required?hint(msg("images.this_editing_model_needs_at_least_one_reference_image")):null,
        el('details',{},el('summary',{},msg("images.loras_selected", {value1: draft.loras.length})),hint(model.help.lora),
            el('div',{class:'creator-add-lora'},loraSelect,button(msg("images.add_lora"),()=>{
                if(!loraSelect.value||draft.loras.some(l=>l.name===loraSelect.value))return;
                if(draft.loras.length>=8){c.error='Choose up to eight LoRAs.';c.render();return;}
                draft.loras.push({name:loraSelect.value,profile:draft.model,strength:1,strength_clip:1,trigger:''});c.remember();c.render();
            })),...loraRows,el('div',{class:'creator-browse'},button(msg("images.browse_models_and_loras"),()=>c.shell.open('Integrations')))),
        el('details',{},el('summary',{},msg("images.advanced_generation_settings")),el('div',{class:'creator-controls'},number('resolution',msg("images.image_size_pixels"),64),number('steps',msg("images.steps")),number('cfg',msg("images.guidance"),.1),number('seed',msg("images.seed_1_for_random"))),
            hint(msg("images.recommended_model_defaults_are_loaded_automatically_a_pair_keeps_the_same_si")),
            draft.model.startsWith('sdxl')?field(msg("images.negative_prompt_sdxl"),el('textarea',{rows:2,value:draft.settings.negative_prompt||'',oninput:e=>{draft.settings.negative_prompt=e.target.value;c.remember();}})):null,
            draft.model.startsWith('sdxl')?el('div',{class:'creator-controls'},number('reference_strength',msg("images.sdxl_reference_strength"),.05),number('edit_denoise',msg("images.sdxl_edit_strength"),.05)):null));
    const sides=c.paired()?['front','back']:['single'];
    const frames=sides.map(side=>{const image=c.revision(side);return el('figure',{class:'creator-frame'},
        el('figcaption',{},el('strong',{},side==='single'?msg("images.image"):side==='front'?msg("images.front"):msg("images.back")),image?button(msg("images.edit", {side: msg(side === "single" ? "images.image" : side === "front" ? "images.front" : "images.back")}),()=>c.act(()=>c.edit(side)),{disabled:busy}):el('span',{class:'muted'},msg("images.not_generated_yet"))),
        image?el('img',{src:image.url,alt:draft.name+' — '+side}):el('div',{class:'creator-empty'},side==='back'?msg("images.uses_the_front_image_to_keep_the_design_consistent"):msg("images.your_image_will_appear_here")),
        image?el('small',{class:'muted'},msg("images.px_mb", {value1: image.size.join(' × '), value2: (image.bytes/1024**2).toFixed(1)})):null);});
    const ready=sides.every(side=>c.revision(side));
    c.progressText=el('p',{class:'muted',role:'status'},busy?(c.run.dependency?.phase==='downloading'?msg("images.the_model_is_downloading_on_first_use_this_may_take_some_time_but_only_happe"):sourceMessage(c.run.stage)):c.run?.status==='complete'?msg("images.images_ready_for_review"):'');
    const review=el('div',{},el('div',{class:'creator-runbar'},button(busy?msg("images.generating"):c.run?.status==='failed'?msg("images.retry_unfinished_images"):ready?msg("images.reuse_unchanged_generation"):c.paired()?msg("images.generate_front_back"):msg("images.generate_image"),()=>c.act(()=>c.generate()),{class:'primary',disabled:busy||c.working}),
        ready&&!busy?button(msg("images.generate_a_new_variation"),()=>c.act(()=>c.generate('regenerate'))):null,
        busy?button(msg("images.cancel_generation"),()=>c.act(async()=>{c.run=await request('images/'+c.id+'/cancel',{});})):null,c.progressText),
        c.error?modelAccessError(c.shell,c.error):null,
        busy?el('div',{class:'creator-busy'},workingStar(),elapsedTime(c.run.started_at*1000),el('progress',{'aria-label':msg("images.image_generation_in_progress")})):null,
        el('div',{class:'creator-pair','data-paired':String(c.paired())},...frames),
        c.run?.pair_review?hint(c.run.pair_review):null,
        el('div',{class:'creator-finish actions'},button(msg("images.save_create_another"),()=>c.act(()=>c.save('another')),{disabled:!ready||busy}),
            (c.paired()||c.singleOrigin)?button(c.orbitOrigin?msg("orbit.use_image"):c.ccoreOrigin?msg("images.use_image_in_ccore"):c.turntableOrigin?msg("virtual_turntable.use_image"):c.singleOrigin?msg("images.use_image_in_single_image_workflow"):msg("images.save_create_a_3d_mesh"),()=>c.act(()=>c.save('3d')),{disabled:!ready||busy,class:'primary'}):null,
            c.ccoreOrigin?button(msg("images.back_to_ccore_wizard"),()=>c.shell.openCcoreWizard({image:true}),{disabled:busy}):null,
            c.orbitOrigin?button(msg("orbit.back_to_wizard"),()=>c.shell.openOrbitToMesh({resume:true}),{disabled:busy}):null,
            c.turntableOrigin?button(msg("virtual_turntable.back_to_wizard"),()=>c.shell.openVirtualTurntable({resume:true}),{disabled:busy}):null,
            button(msg("images.save_view_gallery"),()=>c.act(()=>c.save('gallery')),{disabled:!ready||busy}),
            ready?el('a',{href:'/mumblebox-foundry/v1/images/'+c.id+'/package',download:''},msg("images.download_images")):null));
    const sections=[['subject',msg("images.describe_the_subject"),c.singleOrigin?msg("images.section_single"):msg("images.section_subject"),subject],['references',msg("images.add_references"),msg("images.section_refs"),el('fieldset',{disabled:busy},referenceControls(c))],
        ['model',msg("images.choose_a_model"),msg("images.section_model"),modelPanel],['review',msg("images.generate_review"),msg("images.section_review"),review]];
    const rail=el('nav',{class:'creator-rail','aria-label':msg("images.image_creation_sections")},...sections.map(([id,label,description],index)=>button([
        el('span',{class:'creator-step'},String(index+1)),el('span',{},el('strong',{},label),el('small',{},description))],()=>c.host.querySelector('#creator-'+id)?.scrollIntoView({block:'start',behavior:'smooth'}),{'data-section':'creator-'+id})));
    return el('div',{class:'creator-layout'},rail,el('div',{class:'creator-main'},...sections.map(([id,label,,body],index)=>el('section',{class:'creator-section',id:'creator-'+id},
        el('div',{class:'creator-heading'},el('span',{class:'creator-step'},String(index+1)),el('h3',{},label)),body))));
}
