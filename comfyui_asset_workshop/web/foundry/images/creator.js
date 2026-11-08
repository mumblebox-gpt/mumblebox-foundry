import {modelAccessError} from "../connection-help.js";
import {el,button,hint,field,link} from '../dom.js';
import {request} from '../services.js';
import {referenceControls} from './references.js';
import {workingStar} from '../activity.js';

export function creator(c){
    const draft=c.draft,model=c.model(),busy=!!c.run?.active;
    const text=(key,label,rows=3,placeholder='')=>field(label,el('textarea',{rows,value:draft[key]||'',maxLength:key==='description'?8000:4000,placeholder,
        oninput:e=>{draft[key]=e.target.value;c.remember();}}));
    const number=(key,label,step=1)=>field(label,el('input',{type:'number',step,value:draft.settings[key]??model.defaults[key],
        onchange:e=>{draft.settings[key]=Number(e.target.value);c.remember();}}));
    const category=el('select',{'aria-label':'Image category',onchange:e=>{draft.category=e.target.value;c.remember();c.render();}},
        ...c.cap.categories.map(item=>el('option',{value:item.id,selected:item.id===draft.category},item.name)));
    const subject=el('fieldset',{disabled:busy},el('div',{class:'creator-columns'},
        field('Creation name',el('input',{value:draft.name,maxLength:100,oninput:e=>{draft.name=e.target.value;c.remember();}})),c.singleOrigin?hint('One reference for Single Image or Text. Describe any subject below.'):field('What are you creating?',category)),
        hint(c.cap.categories.find(item=>item.id===draft.category)?.description),
        text('description','Describe your image',4,'The subject, appearance, colors and style you want.'),
        c.paired()?el('div',{class:'creator-columns'},text('front','Front details · optional',2,'Details visible on the front.'),text('back','Back details · optional',2,'Backpack, rear markings or details we cannot see from the front.')):null,
        hint(c.paired()?'You get two images: the front establishes the design, then the model uses it to create the back. Together they describe both sides for the 3D workflow.':'This creates one standalone image without asset framing or posing instructions.'));
    const selectedModel=el('select',{'aria-label':'Image creation model',onchange:e=>{
        draft.model=e.target.value;const chosen=c.model();draft.settings={...chosen.defaults,seed:draft.settings.seed??-1};draft.checkpoint='';
        draft.loras=draft.loras.filter(l=>c.loras.items?.some(i=>i.name===l.name&&i.profiles.includes(draft.model)));
        c.remember();c.render();
    }},...c.cap.models.map(m=>el('option',{value:m.id,selected:m.id===draft.model},m.label)));
    const checkpoints=(c.checkpoints.items||[]).filter(item=>item.kind==='Checkpoint'&&(item.profiles||[item.profile]).includes(draft.model));
    const checkpoint=el('select',{'aria-label':'Installed image checkpoint',onchange:e=>{draft.checkpoint=e.target.value;c.remember();}},el('option',{value:'',selected:!draft.checkpoint},'Included model'),
        ...checkpoints.map(item=>el('option',{value:String(item.file_id),selected:String(item.file_id)===draft.checkpoint},item.model_name||item.name||item.relative_path)));
    const compatible=(c.loras.items||[]).filter(item=>item.profiles.includes(draft.model));
    const loraSelect=el('select',{'aria-label':'Available compatible LoRAs'},el('option',{value:''},'Choose a compatible installed LoRA'),...compatible.map(item=>el('option',{value:item.name},item.name)));
    const loraRows=draft.loras.map((item,index)=>el('div',{class:'creator-lora'},el('strong',{class:'filename'},item.name),
        field('Strength',el('input',{type:'number',min:-3,max:3,step:.1,value:item.strength,onchange:e=>{item.strength=Number(e.target.value);item.strength_clip=item.strength;c.remember();}})),
        field('Trigger words',el('input',{value:item.trigger,maxLength:1000,oninput:e=>{item.trigger=e.target.value;c.remember();}})),
        button('Remove',()=>{draft.loras.splice(index,1);c.remember();c.render();})));
    const modelPanel=el('fieldset',{disabled:busy},el('div',{class:'creator-columns'},field('Image model',selectedModel),field('Checkpoint',checkpoint)),
        hint(model.help.purpose),link(model.license.label,model.license.url),
        model.source_required?hint('This editing model needs at least one reference image.'):null,
        el('details',{},el('summary',{},'LoRAs · '+draft.loras.length+' selected'),hint(model.help.lora),
            el('div',{class:'creator-add-lora'},loraSelect,button('Add LoRA',()=>{
                if(!loraSelect.value||draft.loras.some(l=>l.name===loraSelect.value))return;
                if(draft.loras.length>=8){c.error='Choose up to eight LoRAs.';c.render();return;}
                draft.loras.push({name:loraSelect.value,profile:draft.model,strength:1,strength_clip:1,trigger:''});c.remember();c.render();
            })),...loraRows,el('div',{class:'creator-browse'},button('Browse models and LoRAs',()=>c.shell.open('Integrations')))),
        el('details',{},el('summary',{},'Advanced generation settings'),el('div',{class:'creator-controls'},number('resolution','Image size (pixels)',64),number('steps','Steps'),number('cfg','Guidance',.1),number('seed','Seed · -1 for random')),
            hint('Recommended model defaults are loaded automatically. A pair keeps the same size; the back uses the next seed.'),
            draft.model.startsWith('sdxl')?field('Negative prompt · SDXL',el('textarea',{rows:2,value:draft.settings.negative_prompt||'',oninput:e=>{draft.settings.negative_prompt=e.target.value;c.remember();}})):null,
            draft.model.startsWith('sdxl')?el('div',{class:'creator-controls'},number('reference_strength','SDXL reference strength',.05),number('edit_denoise','SDXL edit strength',.05)):null));
    const sides=c.paired()?['front','back']:['single'];
    const frames=sides.map(side=>{const image=c.revision(side);return el('figure',{class:'creator-frame'},
        el('figcaption',{},el('strong',{},side==='single'?'Image':side==='front'?'Front':'Back'),image?button('Edit '+side,()=>c.act(()=>c.edit(side)),{disabled:busy}):el('span',{class:'muted'},'Not generated yet')),
        image?el('img',{src:image.url,alt:draft.name+' — '+side}):el('div',{class:'creator-empty'},side==='back'?'Uses the front image to keep the design consistent.':'Your image will appear here.'),
        image?el('small',{class:'muted'},image.size.join(' × ')+' px · '+(image.bytes/1024**2).toFixed(1)+' MB'):null);});
    const ready=sides.every(side=>c.revision(side));
    c.progressText=el('p',{class:'muted',role:'status'},busy?(c.run.dependency?.phase==='downloading'?'The model is downloading on first use. This may take some time but only happens once per model.':c.run.stage):c.run?.status==='complete'?'Images ready for review.':'');
    const review=el('div',{},el('div',{class:'creator-runbar'},button(busy?'Generating…':c.run?.status==='failed'?'Retry unfinished images':ready?'Reuse unchanged generation':c.paired()?'Generate front & back':'Generate image',()=>c.act(()=>c.generate()),{class:'primary',disabled:busy||c.working}),
        ready&&!busy?button('Generate a new variation',()=>c.act(()=>c.generate('regenerate'))):null,
        busy?button('Cancel generation',()=>c.act(async()=>{c.run=await request('images/'+c.id+'/cancel',{});})):null,c.progressText),
        c.error?modelAccessError(c.shell,c.error):null,
        busy?el('div',{class:'creator-busy'},workingStar(),el('progress',{'aria-label':'Image generation in progress'})):null,
        el('div',{class:'creator-pair','data-paired':String(c.paired())},...frames),
        c.run?.pair_review?hint(c.run.pair_review):null,
        el('div',{class:'creator-finish actions'},button('Save & Create Another',()=>c.act(()=>c.save('another')),{disabled:!ready||busy}),
            (c.paired()||c.singleOrigin)?button(c.singleOrigin?'Use image in Single Image workflow':'Save & Create a 3D Mesh',()=>c.act(()=>c.save('3d')),{disabled:!ready||busy,class:'primary'}):null,
            button('Save & View Gallery',()=>c.act(()=>c.save('gallery')),{disabled:!ready||busy}),
            ready?el('a',{href:'/mumblebox-foundry/v1/images/'+c.id+'/package',download:''},'Download Images'):null));
    const sections=[['subject','Describe the subject',c.singleOrigin?'One image from your description':'Category and front/back details',subject],['references','Add references','Optional images and camera capture',el('fieldset',{disabled:busy},referenceControls(c))],
        ['model','Choose a model','Defaults, styles and LoRAs',modelPanel],['review','Generate & review','Edit, save or continue to 3D',review]];
    const rail=el('nav',{class:'creator-rail','aria-label':'Image creation sections'},...sections.map(([id,label,description],index)=>button([
        el('span',{class:'creator-step'},String(index+1)),el('span',{},el('strong',{},label),el('small',{},description))],()=>c.host.querySelector('#creator-'+id)?.scrollIntoView({block:'start',behavior:'smooth'}),{'data-section':'creator-'+id})));
    return el('div',{class:'creator-layout'},rail,el('div',{class:'creator-main'},...sections.map(([id,label,,body],index)=>el('section',{class:'creator-section',id:'creator-'+id},
        el('div',{class:'creator-heading'},el('span',{class:'creator-step'},String(index+1)),el('h3',{},label)),body))));
}
