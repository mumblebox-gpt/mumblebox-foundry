import {el, button, field, hint} from '../dom.js';
import {currentLanguage, msg, setText} from '../i18n.js';

export const ux = (key, values) => msg('virtual_turntable.ux_' + key, values);
const orbitText = (key, values) => msg('orbit.' + key, values);
const same = (values, recipe) => Object.entries(recipe).every(([key, value]) => values[key] === value);
const number = value => new Intl.NumberFormat(currentLanguage(), {maximumFractionDigits: 1}).format(value);
const grid = (...children) => el('div', {class:'turntable-fields'}, ...children);
const block = (name, ...children) => el('fieldset', {class:'turntable-settings-block'}, el('legend', {}, name), ...children);

function dropdown({id, label, choices, selected, disabled, help, change}) {
    const description = el('p', {id:id+'-help',class:'muted'});
    const select = el('select', {id,disabled,'aria-describedby':description.id,onchange:() => change(select.value)},
        ...choices.map(({id,label}) => el('option', {value:id,selected:id===selected}, label)));
    return {select,element:el('div',{class:'turntable-choice'},field(label,select),description),
        describe:() => {setText(description,help(select.value));description.hidden=!description.textContent;}};
}

export function orbitSettings(wizard) {
    const {cap,busy,key} = wizard;
    const values = wizard.draft.controls.orbit;
    const defaults = cap.defaults.orbit;
    const recipes = cap.orbit_presets;
    const recipesFor = key === 'orbit-to-mesh' ? {
        standard:[orbitText('preset_standard'),orbitText('preset_standard_help')],
        low_vram:[orbitText('preset_low_vram'),orbitText('preset_low_vram_help')],
        full_steps:[orbitText('preset_full_steps'),orbitText('preset_full_steps_help')],
    } : {
        standard:[ux('standard_short'),ux('standard_short_help')],
        long:[ux('long_orbit'),orbitText('preset_standard_help')],
        low_vram:[orbitText('preset_low_vram'),ux('low_vram_full_help')],
    };
    const recipeMatch = () => Object.keys(recipes).find(id => values.fps===defaults.fps&&same(values,recipes[id])) || 'custom';
    const mainChoice = dropdown({
        id:key+'-orbit-recipe',label:ux('orbit_recipe'),disabled:busy,
        choices:[...Object.keys(recipes).map(id => ({
            id,label:same(defaults,recipes[id])?ux('default_choice',{label:recipesFor[id][0]}):recipesFor[id][0],
        })),{id:'custom',label:ux('custom')}],
        selected:recipeMatch(), help:id=>recipesFor[id]?.[1]||ux('custom_orbit_help'),
        change:id=>{
            if(id==='custom'){exact.hidden=false;mainChoice.describe();return;}
            applyRecipe(id);
        },
    });
    function applyRecipe(id) {
        Object.assign(values,recipes[id],{fps:defaults.fps});
        wizard.remember();
        wizard.renderAt(mainChoice.select.id);
    }
    const useLowVram = button(ux('use_low_vram'),()=>applyRecipe('low_vram'),{disabled:busy});
    const metrics = el('p',{class:'turntable-recipe-metrics','aria-live':'polite'});
    const risk = el('div',{class:'turntable-memory-note'},hint(ux('heavy_video_help')),useLowVram);
    const issue = el('div',{class:'turntable-field-error',role:'status',hidden:true});
    const changes = [];
    const refresh = () => {
        const match=recipeMatch();
        if(mainChoice.select.value!=='custom'||match==='custom')mainChoice.select.value=match;
        mainChoice.describe();
        exact.hidden=mainChoice.select.value!=='custom';
        setText(metrics,ux('orbit_metrics',{width:values.width,height:values.height,
            seconds:number(values.length/values.fps),frames:number(values.length),fps:number(values.fps)}));
        const safe=recipes.standard;
        risk.hidden=values.width*values.height*values.length<=safe.width*safe.height*safe.length ||
            same(values,recipes.low_vram);
        const error=wizard.orbitIssue();
        issue.hidden=!error;
        setText(issue,error);
        for(const update of changes)update();
        wizard.refreshActions();
    };
    const control = name => wizard.input('orbit', name, {change:refresh});
    const samplingFields = ['steps','turbo','sampler','scheduler'];
    const samplingValues = turbo => {
        const recipe = Object.values(recipes).find(recipe=>recipe.turbo===turbo);
        return Object.fromEntries(samplingFields.map(name=>[name,recipe[name]]));
    };
    function valuePreset(id, label, options, fields, help) {
        const match = () => options.find(option=>same(values,option.values))?.id || 'custom';
        const chosen = dropdown({
            id:key+'-'+id,label,disabled:busy,
            choices:[...options,{id:'custom',label:ux('custom')}],
            selected:match(),help,
            change:next=>{
                const option=options.find(option=>option.id===next);
                if(option){
                    Object.assign(values,option.values);
                    for(const name of fields){
                        const input=manual.querySelector('[id="'+key+'-orbit-'+name+'"]');
                        if(input.type==='checkbox')input.checked=values[name];
                        else input.value=String(values[name]);
                    }
                    wizard.remember();
                }
                manual.hidden=next!=='custom';
                chosen.describe();
                refresh();
            },
        });
        const manual=grid(...fields.map(control));
        manual.hidden=chosen.select.value!=='custom';
        chosen.describe();
        changes.push(()=>{
            if(manual.hidden)chosen.select.value=match();
            chosen.describe();
        });
        return el('div',{class:'turntable-preset-field'},chosen.element,manual);
    }
    const size = valuePreset('video-size',ux('video_size'),
        [512,768].map(size=>({id:String(size),label:size+' × '+size,values:{width:size,height:size}})),
        ['width','height'],id=>ux(id==='512'?'size_low_help':id==='768'?'size_standard_help':'size_custom_help'));
    const duration = valuePreset('orbit-length',ux('orbit_length'),
        [[73,'short_length'],[141,'medium_length'],[243,'long_length']].map(([length,label])=>({
            id:String(length),label:ux(label,{frames:length}),values:{length},
        })),['length'],id=>ux(id==='custom'?'length_custom_help':'length_help'));
    const speed = valuePreset('playback-speed',ux('playback_speed'),
        [24,30,60].map(fps=>({id:String(fps),label:fps===defaults.fps?
            ux('default_choice',{label:ux('fps_choice',{fps})}):ux('fps_choice',{fps}),values:{fps}})),
        ['fps'],()=>ux('speed_help'));
    const samplingPreset = valuePreset('sampling-recipe',ux('sampling_recipe'),
        [{id:'turbo',label:ux('sampling_turbo'),values:samplingValues(true)},
         {id:'full',label:ux('sampling_full'),values:samplingValues(false)}].map(option=>({
             ...option,label:same(defaults,option.values)?ux('default_choice',{label:option.label}):option.label,
         })),samplingFields,id=>ux('sampling_'+id+'_help'));
    const exact=el('section',{class:'turntable-custom-orbit',hidden:mainChoice.select.value!=='custom'},
        grid(size,duration,speed,samplingPreset));
    const groups=[
        ['motion',['lora_strength','side_fraction','three_quarter_fraction','back_fraction','margin','background']],
        ['sampling',['seed','turbo_strength','denoise']],
        ['memory',['feedforward_chunks','attention_chunks','chunk_threshold','decode_tile','decode_overlap','decode_frames','temporal_overlap','release_previous_models']],
    ];
    const advanced=el('details',{class:'turntable-advanced','data-disclosure':'orbit-expert'},
        el('summary',{},ux('expert_orbit')),
        control('prompt'),
        ...groups.map(([name,fields])=>block(ux(name),grid(...fields.filter(field=>field in values).map(control)))));
    mainChoice.describe();
    setText(metrics,ux('orbit_metrics',{width:values.width,height:values.height,
        seconds:number(values.length/values.fps),frames:number(values.length),fps:number(values.fps)}));
    risk.hidden=values.width*values.height*values.length<=recipes.standard.width*recipes.standard.height*recipes.standard.length;
    const currentIssue=wizard.orbitIssue();
    issue.hidden=!currentIssue;
    setText(issue,currentIssue||'');
    return el('fieldset',{class:'turntable-control-section turntable-orbit-settings'},
        el('legend',{},ux('orbit_settings')),
        el('div',{class:'turntable-recipe'},mainChoice.element,metrics,risk),
        exact,control('subject_direction'),advanced,issue,
        wizard.resetGroup('orbit',ux('reset_orbit')));
}

export function viewCount(wizard, change=()=>{}) {
    const values=wizard.draft.controls.views;
    const choices=Object.entries(wizard.cap.view_presets).map(([id,count])=>({id,label:orbitText('view_count_'+count)}));
    const fieldId=wizard.key+'-reference-views';
    const {element,describe}=dropdown({
        id:fieldId,label:orbitText('reference_views'),choices,selected:values.preset,disabled:wizard.busy,
        help:id=>orbitText('view_help_'+wizard.cap.view_presets[id]),
        change:id=>{
            values.preset=id;
            wizard.remember();
            describe();
            change();
        },
    });
    describe();
    return element;
}
