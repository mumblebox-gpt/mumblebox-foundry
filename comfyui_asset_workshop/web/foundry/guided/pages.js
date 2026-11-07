import {el,button,hint,field} from '../dom.js';
import {uploadReference,capturePhoto,inputURL} from '../images/references.js';
import {referenceFilename} from '../graph-adapter.js';
import {mountMesh} from '../wizard/preview.js';
import {exportChoices,validateExports} from '../wizard/export-choices.js';
import {request} from '../services.js';
import {measurements} from '../wizard/pages.js';

const views=['front','right','back','left'];
const title=s=>s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
const set=(w,k,v)=>{w.draft.controls[k]=v;w.remember();};
function number(w,k,label,note,limits={}){
    return field(label,el('input',{type:'number',value:w.draft.controls[k]??w.cap.defaults[k],step:limits.step||1,...limits,
        'aria-label':label,oninput:e=>set(w,k,e.target.valueAsNumber)}),note);
}
function select(w,k,label,choices,note){
    return field(label,el('select',{'aria-label':label,onchange:e=>set(w,k,typeof choices[0][0]==='number'?Number(e.target.value):e.target.value)},
        ...choices.map(([value,text])=>el('option',{value,selected:value===(w.draft.controls[k]??w.cap.defaults[k])},text))),note);
}
function picture(w,key,label){const url=w.artifact(key);return url?el('figure',{},w.image(url,label),el('figcaption',{},label),el('a',{href:url,download:label+'.png'},'Save image')):null;}
function mesh(w,key,label,urlOverride=null){
    const url=urlOverride||w.previewArtifact(key);if(!url)return null;
    const host=el('div',{class:'wizard-mesh','aria-label':label});let disposed=false;
    const old=w.previewDispose;w.previewDispose=()=>{disposed=true;old?.();host._dispose?.();};
    setTimeout(async()=>{try{const dispose=await mountMesh(host,url,w.cap.viewer,key==='print'?'preview.stl':'preview.glb');if(disposed)dispose();else host._dispose=dispose;}catch(e){if(!disposed)host.replaceChildren(hint(e.message));}},0);
    return el('section',{},el('h3',{},label),host,el('a',{href:url,download:w.draft.name+'-'+key.replaceAll(':','-')+'.glb'},'Save this mesh'));
}

export function startingPage(w){
    async function take(file){if(w.id)throw Error('Start a new object to change its original reference. This saved run is preserved.');const ref=await uploadReference(file);w.draft.original=ref.filename;w.remember();w.render();}
    const file=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,'aria-label':'Upload starting object image',onchange:e=>w.act(()=>take(e.target.files[0]))});
    const current=referenceFilename();
    const original=hint(w.draft.original?'Selected reference: '+w.draft.original.split('/').pop():'Choose one complete object as your starting reference.');
    const extra=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,'aria-label':'Upload appearance reference',onchange:e=>w.act(async()=>{
        const ref=await uploadReference(e.target.files[0]);const refs=w.draft.controls.extra_references??=[];
        if(refs.length>=6)throw Error('Use at most six additional references.');refs.push({filename:ref.filename,description:'Appearance and material details'});
    })});
    const category=el('select',{'aria-label':'Object type'},el('option',{value:'props'},'Objects'),
        el('option',{disabled:true},'People · future preset'),el('option',{disabled:true},'Vehicles · future presets'));
    return el('div',{},hint('3D-Guided combines Pixal3D geometry, MoGe 2 camera estimation, Blender rendering and Qwen depth guidance. Measured views provide structure while your references guide appearance.'),
        el('div',{class:'wizard-columns'},field('Asset name',el('input',{value:w.draft.name,'aria-label':'Asset name',maxLength:100,disabled:!!w.id,oninput:e=>{w.draft.name=e.target.value;w.remember();}})),
            field('What are you making?',category,'Objects only in this version. Best suited to solid standalone props readable from front, back and both sides. The treasure chest is the completed example.')),
        file,el('div',{class:'upload-zone',ondragover:e=>e.preventDefault(),ondrop:e=>{e.preventDefault();w.act(()=>take(e.dataTransfer.files[0]));}},el('strong',{},'Drop one starting image here'),
            el('div',{class:'actions'},button('Upload image',()=>file.click(),{disabled:!!w.id}),button('Take a photo',()=>capturePhoto(w.shell,file=>w.act(()=>take(file))),{disabled:!!w.id||!navigator.mediaDevices}),
                current?button('Use existing reference',()=>{w.draft.original=current;w.remember();w.render();},{disabled:!!w.id}):null)),
        original,w.draft.original?w.image(inputURL(w.draft.original),'Starting object reference'):null,
        w.id?button('Start a new object',()=>w.shell.openGuidedWizard(),{disabled:w.active()}):null,
        field('Describe the object',el('textarea',{rows:3,value:w.draft.controls.asset_description||'','aria-label':'Describe the object',maxLength:800,oninput:e=>set(w,'asset_description',e.target.value)}),'Describe its main shape, material, colors and attached parts.'),
        field('Special instructions',el('textarea',{rows:3,value:w.draft.controls.special_instructions||'','aria-label':'Special instructions',maxLength:800,oninput:e=>set(w,'special_instructions',e.target.value)}),'Optional: preserve an emblem, explain the back, or name details that must remain attached.'),
        el('div',{class:'image-invitation'},el('strong',{},"Don't have an image?"),button('Create an image',()=>{w.remember();w.shell.imageOrigin={method:'guided'};w.shell.openImages('Create Images');})),
        el('details',{},el('summary',{},'Additional appearance references'),hint('These guide materials and details. Blender provides the target viewpoints.'),extra,
            button('Add appearance reference',()=>extra.click()),...(w.draft.controls.extra_references||[]).map((r,i)=>el('section',{class:'reference-card'},w.image(inputURL(r.filename),'Appearance reference '+(i+1)),
                field('Reference purpose',el('textarea',{value:r.description,'aria-label':'Appearance reference '+(i+1)+' purpose',oninput:e=>{r.description=e.target.value;w.remember();}})),
                button('Remove reference',()=>{w.draft.controls.extra_references.splice(i,1);w.remember();w.render();})))),
        el('details',{},el('summary',{},'Main view and geometry controls'),
            number(w,'elevation_deg','View elevation (degrees)','Default 10°. Zero gives straight-on views; a small elevation also shows upper surfaces.',{min:0,max:30}),
            select(w,'proxy_processing','Working proxy handling',[['upright_solid_box','Upright solid prop · chest default'],['as_generated','Preserve generated pose · advanced']],'The solid-prop preset estimates box orientation and repairs its actual working mesh. It can change thin or open shapes.'),
            select(w,'refine_resolution','Refinement detail',[[512,'512'],[1024,'1024'],[1536,'1536 · default']],'Higher detail takes more time and memory.'),
            select(w,'texture_size','Texture resolution',[[1024,'1024'],[2048,'2048'],[4096,'4096 · default']],'Final textures are applied after refinement and cleanup.')),
        el('details',{},el('summary',{},'Advanced generation controls'),
            number(w,'turnaround_seed','Concept seed','Fixed default preserves repeatability.'),number(w,'proxy_seed','Rough mesh seed','Default 42.'),
            number(w,'enhancement_seed','Enhancement seed','Default 42. Change to regenerate appearance.'),
            number(w,'enhancement_steps','Enhancement steps','Default 40.',{min:20,max:100}),number(w,'control_strength','Depth guidance strength','Default 1.0.',{min:0,max:2,step:.1}),
            number(w,'refine_steps','Refinement steps','Default 25 per internal resolution pass.',{min:1,max:100}),
            number(w,'reconstruction_seed','Reconstruction seed','Default 42. Keep fixed when comparing selected views.'),
            number(w,'refine_seed','Refinement seed','Default 42.'),number(w,'texture_seed','Texture seed','Default 42.'),
            number(w,'texture_steps','Texture steps','Default 20.',{min:1,max:100}),
            number(w,'texture_guidance','Texture guidance','Default 3.0.',{min:0,max:20,step:.1}),
            field('CPU offloading',el('input',{type:'checkbox',checked:w.draft.controls.cpu_offload??true,'aria-label':'CPU offloading',onchange:e=>set(w,'cpu_offload',e.target.checked)}),'Default on. Uses system RAM to reduce GPU memory requirements.')),
        el('details',{},el('summary',{},'Models, licenses and retained files'),hint(w.cap.license_note),...w.cap.resources.map(r=>el('p',{},el('strong',{},r.name+' · '),r.license||'See source',' ',el('a',{href:r.license_url||r.source,target:'_blank',rel:'noopener noreferrer'},'Read terms'))),
            hint('Originals, intermediate meshes, camera records and settings are retained locally. Asset ZIPs contain selected exports; a separate private production download includes source files.')),
        w.nav({next:()=>w.advance(),label:'Generate concept turnaround',note:'Only the original image makes the rough mesh. The concept turnaround is kept for later appearance guidance.'}));
}

export function guidePage(w){
    const done=w.job?.completed||{};
    const label=!done.concept?'Generate concept turnaround':!done.proxy?'Build rough mesh':!done.render?'Render measured Blender views':'Assemble enhancement sheet';
    return el('div',{},hint('Review the appearance concept, then the actual working proxy and its measured views. The saved working proxy is the same mesh Blender uses.'),
        picture(w,'concept:sheet','Concept appearance turnaround'),w.artifact('concept:sheet')?button('Edit an area of the concept sheet',()=>w.act(()=>w.editConcept()),{disabled:w.active()}):null,
        done.concept?button('Regenerate concept views',()=>w.act(async()=>{w.draft.controls.turnaround_seed=Math.floor(Math.random()*2**32);await w.advance();}),{disabled:w.active()}):null,
        mesh(w,'proxy:glb','Actual working rough mesh'),
        el('div',{class:'view-grid'},...views.map(v=>picture(w,'render:'+v,title(v)+' measured guide'))),
        w.artifact('cameras')?el('a',{href:w.artifact('cameras'),download:'measured-cameras.json'},'Save measured camera information'):null,
        hint('Concept art supplies appearance. Blender supplies the numerical cameras and structural guides. Perspective fidelity after enhancement still requires visual review.'),
        w.nav({next:()=>w.advance(),label,note:'Each completed generation is saved before the next stage.'}));
}

export function enhancementPage(w){
    const done=w.job?.completed||{};const selected=w.draft.controls.selected_view_ids??=[...w.cap.defaults.selected_view_ids];
    const label=!done.sheet?'Assemble enhancement sheet':!done.enhance_sheet?'Enhance the sheet':!done.split?'Split and review four views':!done.prepare?'Prepare selected camera frames':'Build reconstructed mesh';
    return el('div',{},hint('All four panels show the same object. Black separators keep their frames distinct; depth guides constrain structure and the concept sheet supplies appearance.'),
        picture(w,'guide:sheet','Measured Blender sheet'),picture(w,'enhanced:sheet','Enhanced four-view sheet'),
        done.enhance_sheet?button('Regenerate enhanced sheet',()=>w.act(async()=>{w.draft.controls.enhancement_seed=Math.floor(Math.random()*2**32);await w.advance();}),{disabled:w.active()}):null,
        el('div',{class:'view-grid'},...views.map(v=>el('section',{class:'guided-view-choice'},picture(w,'enhanced:'+v,title(v)+' enhanced view'),
            field('Use '+title(v)+' view',el('input',{type:'checkbox','aria-label':'Use '+v+' view',checked:selected.includes(v),disabled:w.active(),onchange:e=>{
                const next=e.target.checked?[...selected,v]:selected.filter(x=>x!==v);w.draft.controls.selected_view_ids=next;
                if(!next.includes(w.draft.controls.reference_view_id||'front'))w.draft.controls.reference_view_id=next[0]||'front';w.remember();w.render();
            }}))))),
        !selected.length?el('p',{role:'alert',class:'error-panel'},'Choose at least one view.'):hint(selected.length+' of four views selected. Only these images and their matching cameras go to reconstruction.'),
        select(w,'reference_view_id','Refinement and texture reference',views.filter(v=>selected.includes(v)).map(v=>[v,title(v)]),'Choose the clearest selected view for final refinement and texture.'),
        w.artifact('enhanced:cameras')?el('a',{href:w.artifact('enhanced:cameras'),download:'enhanced-view-cameras.json'},'Save enhanced-view camera information'):null,
        w.nav({next:async()=>{if(!selected.length)throw Error('Choose at least one view.');await w.advance();},label}));
}

export function meshPage(w){
    const done=w.job?.completed||{};
    const options=[['textured','Textured master'],['refined:glb','After cleanup'],['refine:raw:glb','After Hi3D, before cleanup'],['reconstruction:glb','Before Hi3D']].filter(([key])=>w.artifact(key));
    const preview=options.some(([key])=>key===w.geometryPreview)?w.geometryPreview:options[0]?.[0];
    const picker=el('select',{'aria-label':'Compare geometry checkpoints',onchange:e=>{w.geometryPreview=e.target.value;w.render();}},...options.map(([value,label])=>el('option',{value,selected:value===preview},label)));
    const label=!done.reconstruct?'Build reconstructed mesh':!done.refine?'Refine and clean geometry':!done.texture?'Apply final textures':'Choose output versions';
    return el('div',{},hint('Reconstruction uses selected images and measured cameras. Hi3D refines the result, followed by vertex welding, small-hole filling and conditional solid repair. Texturing uses the finished geometry.'),
        options.length?picker:null,mesh(w,preview,options.find(([key])=>key===preview)?.[1]||'Reconstructed mesh'),
        w.nav({next:()=>done.texture?w.go(5):w.advance(),label,note:'All previous mesh checkpoints remain saved.'}));
}

export function exportPage(w){
    function finishingNumber(key,label,note){return field(label,el('input',{type:'number',value:w.draft.finishing[key]??w.cap.finishing_defaults[key],'aria-label':label,min:1000,max:1000000,
        oninput:e=>{w.draft.finishing[key]=e.target.valueAsNumber;w.remember();}}),note);}
    return el('div',{},hint('Choose the versions and file formats to save. Detailed and reduced triangle meshes and print geometry are available; the detailed master remains retained.'),
        exportChoices(w.cap.exports,w.draft.selection,()=>w.remember()),
        el('details',{},el('summary',{},'Output geometry settings'),finishingNumber('balanced_triangles','Balanced triangle target','Default 250,000.'),
            finishingNumber('compact_triangles','Compact triangle target','Default 100,000.'),w.cap.quad_retopology_enabled?finishingNumber('quad_count','Editable quad target','Default 25,000. QuadriFlow builds editable topology; runtime derivatives are triangulated.'):null,
            field('Print height (millimeters)',el('input',{type:'number',value:w.draft.finishing.print_height_mm??100,'aria-label':'Print height (millimeters)',min:1,max:10000,oninput:e=>{w.draft.finishing.print_height_mm=e.target.valueAsNumber;w.remember();}}),'Physical printing requires separate validation.')),
        w.nav({next:async()=>{validateExports(w.draft.selection);await w.finish();},label:'Prepare selected outputs and package'}));
}

export function resultPage(w){
    const f=w.job?.finishing;const packageURL='guided/runs/'+w.id+'/package';
    const options=[['texture','Detailed master','detailed'],['balanced','Balanced game mesh','game_balanced'],['compact','Compact game mesh','game_compact'],['quads','Editable quad runtime preview','quad_light'],['print','Print mesh (STL)','print'],['clean','Clean geometry',null]]
        .filter(([key,label,variant])=>f?.previews?.[key]&&(!variant||f.selection.variants[variant])&&(key!=='quads'||w.cap.quad_retopology_enabled));
    const selected=options.some(([key])=>key===w.finalPreview)?w.finalPreview:options[0]?.[0];
    const picker=el('select',{'aria-label':'Finished mesh version',onchange:e=>{w.finalPreview=e.target.value;w.render();}},...options.map(([value,label])=>el('option',{value,selected:value===selected},label)));
    const actions=()=>el('nav',{class:'actions result-actions','aria-label':'Finished asset actions'},button('Make a new asset',()=>w.shell.openGuidedWizard(),{class:'primary'}),button('Back to export choices',()=>w.go(5)),button('Choose another workflow',()=>w.shell.open('Choose a Workflow')));
    return el('div',{},f?.package?actions():null,options.length?picker:null,
        mesh(w,selected||'textured',options.find(([key])=>key===selected)?.[1]||'Final textured master',f?.previews?.[selected]),
        f?.package?el('section',{},el('h3',{},'Your selected asset package is ready'),
            el('a',{class:'download-link',href:'/mumblebox-foundry/v1/'+packageURL,download:w.draft.name+'.zip'},'Download asset ZIP'),
            button('Open Output Folder',()=>w.act(()=>request('guided/runs/'+w.id+'/open-package-folder',{}))),
            hint('Includes the selected meshes, matching material maps, measurements, production record and applicable notices. Source images remain separate.')):
            el('div',{},hint(f?.active?'Preparing the selected exports and package. This can take several minutes.':'Select your output versions on the previous page.'),
                f&&!f.active&&!f.package?button('Retry remaining stages',()=>w.act(()=>w.finish()),{class:'primary'}):null),
        el('details',{},el('summary',{},'Save originals, cameras and production files'),
            hint('Private download: contains original images, prompts, intermediate meshes, numerical cameras and local execution records. Review before sharing.'),
            el('a',{class:'download-link',href:'/mumblebox-foundry/v1/guided/runs/'+w.id+'/production',download:'private-production.zip'},'Download private production archive'),
            button('Open retained production folder',()=>w.act(()=>request('guided/runs/'+w.id+'/open-folder',{}))),
            el('a',{href:w.artifact('enhanced:cameras'),download:'camera-information.json'},'Save camera information')),
        f?.measurements?measurements({run:f,showQuads:w.cap.quad_retopology_enabled}):null,
        ...(f?.package?.warnings||[]).map(text=>el('p',{class:'note-panel'},text)),
        f?.package?hint(f.cleanup?.status==='released'?'Models were released. Saved masters, previews and exports are retained.':'Package saved. Memory release status: '+(f.cleanup?.status||'finishing')):null,
        f?.package?actions():w.nav({back:5,note:'Your session and all completed checkpoints are retained.'}));
}
