import {el,button,hint,field,link} from '../dom.js';
import {capturePhoto,inputURL} from '../images/references.js';
import {fileURL} from './controller.js';
import {comparison} from './comparison.js';
export const titles=['Starting image','Generation options','Splat and original mesh','Refine and clean','Review your outputs','Finished asset'];
export const blurbs=['One complete subject','Quality and selected files','Inspect Idol’s reconstruction','Optional refinement and repair','Compare detail and geometry','Downloads and saved History'];
export function page(w){return [input,options,generation,cleanup,review,result][w.page-1](w);}
function input(w){
    const file=el('input',{type:'file',accept:'image/png,image/jpeg,image/webp',hidden:true,onchange:e=>w.act(()=>w.upload(e.target.files[0]))});
    const drop=el('div',{class:'reference-drop',tabIndex:0,ondragover:e=>{e.preventDefault();e.stopPropagation();},ondrop:e=>{e.preventDefault();e.stopPropagation();w.act(()=>w.upload(e.dataTransfer.files[0]));}},
        hint('Drop one image here, or choose an input below.'),file,w.draft.image?el('img',{src:inputURL(w.draft.image),alt:'Starting asset reference',style:'max-height:320px;max-width:100%'}):null,
        el('div',{class:'actions'},button('Upload image',()=>file.click()),button('Take a photo',()=>capturePhoto(w.shell,f=>w.act(()=>w.upload(f)))),button('Choose from Gallery',()=>w.gallery())));
    return el('div',{},w.text('name','Asset name'),hint('Use one clear image with the entire subject visible. A three-quarter view can reveal useful side and front shapes. Hidden surfaces are inferred.'),drop,
        hint('Idol, by Sperid Labs, creates a detailed Gaussian splat and an extracted mesh from your image. We combine that research with optional Hi3D refinement and ComfyUI cleanup.'),
        el('div',{class:'actions'},...w.cap.models.map(m=>link(m.name+' · '+m.creator,m.url))),w.nav({next:()=>w.go(2)}));
}
function options(w){
    const names={splat:'Gaussian splat (SPZ)',raw:'Original extracted mesh (GLB)',master:'Cleaned master (GLB)',companion:'Lightweight companion (GLB)',presentation:'Crease-normal presentation copies (GLB)',orbit:'Splat orbit video (MP4)',previews:'Untextured preview images (PNG)',zip:'Downloadable ZIP package'};
    const selection=el('fieldset',{},el('legend',{},'Files to keep in the package'),...Object.entries(names).map(([key,label])=>el('label',{class:'check-row'},el('input',{type:'checkbox',checked:w.draft.outputs[key],onchange:e=>{w.draft.outputs[key]=e.target.checked;w.remember();}}),el('span',{},label))));
    const advanced=el('details',{},el('summary',{},'Advanced generation settings'),w.number('seed','Idol seed',0,2**53-16),w.number('steps','Sampling steps',1,100),w.number('cfg','Guidance',.1,20,.1),w.number('image_size','Reference preparation size',256,2048,64),w.number('gaussians','Gaussian count',32768,1048576,32768),w.number('decoder_seed','Decoder seed',0,2**53-16),w.number('mesh_resolution','Splat mesh extraction resolution',128,1024,64),w.number('orbit_size','Orbit image size',256,2048,64),w.number('orbit_frames','Orbit frames',16,180),w.number('orbit_fps','Orbit frames per second',1,60));
    return el('div',{},hint('The defaults reproduce our tested lander workflow. Higher settings increase memory use and processing time; they do not guarantee a better reconstruction.'),
        w.check('refine','Use Hi3D geometry refinement','Can improve the extracted mesh before cleanup. Adds processing time. The original splat and extracted mesh are preserved.'),
        selection,advanced,hint('Selected model files are checked and downloaded before processing. The splat supplies visual detail; the companion is separate polygon geometry.'),w.nav({next:()=>w.start('generation'),nextText:'Generate with Idol'}));
}
function generation(w){return el('div',{},hint('Review the splat and its original mesh. The splat preserves appearance; the mesh is the starting geometry for optional refinement and cleanup.'),w.artifact('orbit','Splat orbit'),w.artifact('splat','Gaussian splat',{preview:true}),w.artifact('raw','Original mesh',{preview:true}),w.nav({next:()=>w.go(4),nextText:'Review cleanup settings'}));}
function cleanup(w){
    const resolution=el('select',{value:String(w.draft.refine_resolution),onchange:e=>{w.draft.refine_resolution=Number(e.target.value);w.remember();}},...[512,1024,1536].map(v=>el('option',{value:String(v),selected:v===w.draft.refine_resolution},String(v))));
    const mode=el('select',{onchange:e=>{w.draft.repair_mode=e.target.value;w.remember();}},el('option',{value:'rebuild',selected:w.draft.repair_mode==='rebuild'},'Solid rebuild · tested default'),el('option',{value:'auto',selected:w.draft.repair_mode==='auto'},'Connectivity-based automatic repair'));
    return el('div',{},hint('Hi3D can recover more useful structure. ComfyUI then closes the surface, gently smooths it and creates a separately simplified companion. Both meshes return to the splat’s coordinate frame.'),
        w.check('refine','Use Hi3D refinement'),w.number('companion_triangles','Companion triangle target',1000,500000,1000),
        hint('The final solid rebuild can change the exact triangle count. Fine rails, antennas and panel details may disappear in the lightweight mesh.'),
        el('details',{},el('summary',{},'Advanced refinement and cleanup'),field('Hi3D resolution',resolution),w.number('refine_steps','Hi3D steps',1,100),w.number('refine_seed','Hi3D seed',0,2**53-16),w.check('cpu_offload','Allow CPU offload'),
            w.number('master_resolution','Master remesh resolution',64,1024,32),w.number('master_smoothing','Gentle smoothing iterations',0,10),w.number('master_band','Master closing band',.5,4,.1),w.number('drop_small_components','Small-component filter',0,.1,.0001),w.number('repair_resolution','Companion repair resolution',32,256,8),field('Companion repair',mode),hint('Automatic repair checks connectivity. An independent exported-mesh audit also checks intersections before accepting the result.'),w.number('crease_angle','Presentation crease angle',1,180)),
        w.nav({next:()=>w.start('cleanup'),nextText:'Refine and clean'}),button('Review saved meshes',()=>w.go(5),{disabled:!w.run?.artifacts?.master}));
}
function review(w){return el('div',{},hint('Compare the preserved splat, clean master and lightweight companion. Closed geometry and numerical checks do not certify collision behavior in a particular game engine.'),
    comparison(w),
    w.run?.quality?el('details',{},el('summary',{},'Recorded geometry checks'),el('pre',{},JSON.stringify(w.run.quality,null,2))):null,
    w.nav({next:()=>w.start('export'),nextText:'Save selected package'}));}
function result(w){
    const actions=el('div',{class:'actions'},button('Review meshes',()=>w.go(5)),button('New splat asset',()=>w.shell.openSplatWizard()),button('Choose a workflow',()=>w.shell.open('Choose a Workflow')));
    return el('div',{},w.run?.package?hint('Your selected files are saved, with a readable catalog, model credits and a History entry.'):hint('The selected stages are processing. Completed results remain saved as the workflow advances.'),
    w.run?.artifacts?.companion?comparison(w):w.artifact('orbit','Splat orbit'),
        w.run?.package?.zip_selected?link('Download asset ZIP',fileURL(w.runId,w.run.package.path,true)):null,
        el('div',{class:'actions'},...Object.keys(w.run?.artifacts||{}).map(role=>link('Download '+role.replaceAll('_',' '),fileURL(w.runId,w.run.artifacts[role].relative,true)))),actions,w.nav({back:5}));
}
