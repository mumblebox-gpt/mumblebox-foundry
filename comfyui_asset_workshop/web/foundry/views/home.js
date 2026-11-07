import {el,button,hint} from "../dom.js";
import {showWorkflow,showHairWorkflow,savedWizardState} from "../graph-adapter.js";
import {showGuidedWorkflow} from '../guided/graph.js';
import {showSplatWorkflow} from '../splat/graph.js';
import {syncSplatGraph} from '../splat/graph.js';
import {request} from '../services.js';

const planned=[
["repair","Refine and Repair an Existing Mesh","Supply an existing mesh and a matching image for refinement and new output versions."],
["video","Start with a Video","Use a recorded subject as the starting point for a 3D asset."],
["turntable","PC-Controlled Turntable and Camera Capture","Capture a subject with a compatible ComXim Bluetooth turntable and connected camera."],
["figure","Action Figure Mode","Use identity references and figure presets to create a personalized figure, with optional base choices."]
];
const artwork=(id,alt)=>{
    const url=new URL("../../assets/foundry/"+id+".png",import.meta.url);
    // New artwork must not reuse a cached failed response from an older install.
    url.searchParams.set('v','hairdeck-1');
    return el("img",{src:url.href,alt,loading:"lazy",decoding:"async",width:512,height:512});
};

export function home(shell) {
    const saved = savedWizardState(shell.node);
    const methods=el('div',{class:'mesh-methods'},
        el('article',{class:'mesh-method','data-method':'turnaround'},el('div',{},el('span',{class:'badge'},'Turnaround'),
            el('h3',{},'Turnaround'),hint('Create consistent views with Qwen or FLUX, reconstruct with Pixal3D/TRELLIS.2, then refine with Hi3D and prepare selected exports.'),
            hint('A strong starting point for humanoids. Review the generated views before committing to geometry; vehicle, prop and creature recipes are still being improved.'),
            el('div',{class:'actions'},button('Open Turnaround wizard',()=>shell.openMeshMethod('turnaround'),{class:'primary'}),
                button('View Turnaround workflow',()=>showWorkflow(shell.node)),saved?button('Resume Turnaround',()=>shell.openWizard({resume:true})):null))),
        el('article',{class:'mesh-method','data-method':'3d-guided'},el('div',{},el('span',{class:'badge'},'3D-Guided · Objects'),
            el('h3',{},'3D-Guided'),hint('Combine Pixal3D, MoGe 2 camera estimation and measured Blender views with Qwen depth guidance before reconstruction. Hi3D and TRELLIS.2 prepare the final geometry and textures.'),
            hint('Objects preset: front, back and both sides. Includes view selection, refinement, cleanup, texturing, detailed/reduced triangle meshes and print exports. Additional processing; comparative quality is not yet benchmarked.'),
            el('div',{class:'actions'},button('Open 3D-Guided wizard',()=>shell.openMeshMethod('guided'),{class:'primary'}),
                button('View 3D-Guided workflow',()=>showGuidedWorkflow()),shell.node.properties.foundryGuided?.id?button('Resume 3D-Guided',()=>shell.openGuidedWizard({resume:true})):null))));
    methods.append(el('article',{class:'mesh-method','data-method':'splat'},el('div',{},el('span',{class:'badge'},'Idol · Splat & Solid'),
        el('h3',{},'Splat & Solid'),hint('Create a detailed Gaussian splat with Idol by Sperid Labs, plus separate cleaned and lightweight companion meshes. Optional Hi3D refinement can improve the geometry before ComfyUI cleanup.'),
        hint('Use the splat for appearance and the closed companion for further editing or collision setup. Includes saved stages, geometry checks, orbit previews and selected downloads.'),
        el('div',{class:'actions'},button('Open Splat & Solid wizard',()=>shell.openMeshMethod('splat'),{class:'primary'}),
            button('View Splat & Solid workflow',async()=>{syncSplatGraph(await request('splat/template'),shell.node);showSplatWorkflow();}),
            shell.node.properties.foundrySplat?.runId?button('Resume Splat & Solid',()=>shell.openSplatWizard({resume:true})):null))));
    const card = el("details",{class:"mesh-category",open:!!shell.pendingMeshHandoff},
      el('summary',{class:'workflow-card'},
        el("div",{class:"art workflow-art"},artwork("image-to-3d","Reference image becoming a sculpted 3D figure")),
        el("div",{class:"card-body"},el("span",{class:"eyebrow"},"IMAGE TO 3D  /  01"),
            el("h3",{},"Create a Mesh from an Image"),
            el("p",{},"Upload references or photograph a subject with your connected webcam. Choose a textured mesh workflow, or create a detailed Gaussian splat with separate companion geometry. Keep detailed masters and selected versions for editing, game development or print preparation."),
            hint("Choose the output and approach that suit your project. Each method has an independent wizard with saved stages and selected exports."),
            el("div",{class:"formats"},["SPZ","GLB","FBX","OBJ","BLEND","STL","PNG","MP4","ZIP"].map(x=>el("span",{class:"badge"},x))),
            el('span',{class:'method-disclosure'},'Choose your workflow method \u25be'))),
        shell.pendingMeshHandoff?hint('Your created image is ready. Choose which mesh method should use it.'):null,methods);
    const imageCard=el('article',{class:'planned-workflow'},artwork('text','Develop images from a description'),el('div',{},
        el('div',{class:'workflow-card-heading'},el('span',{class:'badge'},'Available'),
            button('Create Images',()=>{delete shell.imageOrigin;shell.openImages('Create Images');},{class:'primary'})),
        el('h3',{},'Create Images and 3D Assets from a Text Prompt'),
        hint('Create and edit references with models from Qwen and Black Forest Labs, then keep the images or continue into your chosen 3D workflow.')));
    const hairCard=el('article',{class:'planned-workflow'},artwork('hair','Stylized hair cards with matching spring bones'),el('div',{},
        el('div',{class:'workflow-card-heading'},el('span',{class:'badge'},'HairDeck'),
            el('div',{class:'workflow-card-controls'},button('Open Hair Wizard',()=>shell.openHairWizard(),{class:'primary'}),
                button('View Graph',()=>showHairWorkflow(),{title:'View Hair Workflow'}),
                shell.node.properties.foundryHair?.runId?button('Resume',()=>shell.openHairWizard({resume:true}),{title:'Resume hair asset'}):null)),
        el('h3',{},'Create Rigged Hair with HairDeck'),
        hint('Powered by HairDeck from hyz317 and its researchers, with FengLairh’s ComfyUI integration. Create editable stylized hair cards, fit and color them, then export static GLB or spring-bone VRM with optional motion preview.')));
    return el("div",{},card,el("div",{class:"future-workflows"},imageCard,hairCard,...planned.map(([id,name,description])=>el("article",{class:"planned-workflow"},artwork(id,name),el("div",{},el("span",{class:"badge"},"Coming soon"),el("h3",{},name),hint(description))))));
}
