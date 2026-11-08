import {syncSingleGraph,showSingleWorkflow} from '../single/graph.js';
import {el,button,hint} from "../dom.js";
import {showWorkflow,showHairWorkflow,savedWizardState,savedSingleWizardState} from "../graph-adapter.js";
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
    const url=new URL("../../assets/foundry/"+id+(id.startsWith("method-")?".webp":".png"),import.meta.url);
    // New artwork must not reuse a cached failed response from an older install.
    url.searchParams.set('v','single-image-1');
    return el("img",{src:url.href,alt,loading:"lazy",decoding:"async",width:512,height:512});
};

export function home(shell) {
    const saved = savedWizardState(shell.node);
    const methods=el('div',{class:'mesh-methods'},
        el('article',{class:'mesh-method recommended','data-method':'single'},el('div',{},el('span',{class:'badge'},'Recommended · Single Image or Text'),
            el('h3',{},'Single Image or Text'),hint('Start with one image, or create one from text. Pixal3D builds the mesh; Hi3D refines it before cleanup, texturing and exports.'),
            hint('Best for a direct start · Fewer stages and models · Try a three-quarter view.'),
            el('div',{class:'actions'},button('Open Single Image wizard',()=>shell.openMeshMethod('single'),{class:'primary'}),
                button('View workflow',async()=>{syncSingleGraph(await request('wizard/single-template'),shell.node);showSingleWorkflow();}),
                (savedSingleWizardState(shell.node)?.runId||savedSingleWizardState(shell.node)?.draft?.references?.length)?button('Resume Single Image',()=>shell.openWizard({method:'single-image',resume:true})):null))),
        el('article',{class:'mesh-method','data-method':'turnaround'},el('div',{},el('span',{class:'badge'},'Turnaround'),
            el('h3',{},'Turnaround'),hint('Generate consistent views with Qwen or FLUX, build with Pixal3D, then refine with Hi3D and texture with TRELLIS.2.'),
            hint('Best for humanoids · Review four views before building. Vehicle, prop and creature recipes are being improved.'),
            el('div',{class:'actions'},button('Open Turnaround wizard',()=>shell.openMeshMethod('turnaround'),{class:'primary'}),
                button('View Turnaround workflow',()=>showWorkflow(shell.node)),saved?button('Resume Turnaround',()=>shell.openWizard({resume:true})):null))),
        el('article',{class:'mesh-method','data-method':'3d-guided'},el('div',{},el('span',{class:'badge'},'3D-Guided · Objects'),
            el('h3',{},'3D-Guided'),hint('Use a Pixal3D proxy and measured camera views with MoGe 2 and Qwen depth guidance. Hi3D and TRELLIS.2 finish the asset.'),
            hint('Best for controlled object views · Choose the angles before reconstruction. More processing; comparative quality is still being evaluated.'),
            el('div',{class:'actions'},button('Open 3D-Guided wizard',()=>shell.openMeshMethod('guided'),{class:'primary'}),
                button('View 3D-Guided workflow',()=>showGuidedWorkflow()),shell.node.properties.foundryGuided?.id?button('Resume 3D-Guided',()=>shell.openGuidedWizard({resume:true})):null))));
    methods.append(el('article',{class:'mesh-method','data-method':'splat'},el('div',{},el('span',{class:'badge'},'Idol · Splat & Solid'),
        el('h3',{},'Splat & Solid'),hint('Create an Idol Gaussian splat by Sperid Labs with separate, cleaned companion geometry. Add optional Hi3D refinement.'),
        hint('Best for detailed appearance plus lightweight geometry · Orbit previews, mesh checks and selected downloads.'),
        el('div',{class:'actions'},button('Open Splat & Solid wizard',()=>shell.openMeshMethod('splat'),{class:'primary'}),
            button('View Splat & Solid workflow',async()=>{syncSplatGraph(await request('splat/template'),shell.node);showSplatWorkflow();}),
            shell.node.properties.foundrySplat?.runId?button('Resume Splat & Solid',()=>shell.openSplatWizard({resume:true})):null))));
    for(const [method,id,alt] of [['single','single','One reference becoming a refined robot mesh'],['turnaround','turnaround','Consistent character views beside a finished mesh'],['3d-guided','guided','Measured cameras around a cargo rover'],['splat','splat','Detailed splat and simple companion geometry']]){
        const card=methods.querySelector('[data-method="'+method+'"]');card.prepend(artwork('method-'+id,alt));
        card.querySelector('div').append(el('div',{class:'formats'},...(method==='splat'?['SPZ','GLB','MP4','ZIP']:method==='3d-guided'?['GLB','FBX','STL','ZIP']:['GLB','FBX','Quads','STL','ZIP']).map(x=>el('span',{class:'badge'},x))));
    }
    const card = el("details",{class:"mesh-category",open:true},
      el('summary',{class:'workflow-card'},
        el("div",{class:"art workflow-art"},artwork("image-to-3d","Reference image becoming a sculpted 3D figure")),
        el("div",{class:"card-body"},el("span",{class:"eyebrow"},"IMAGE TO 3D  /  01"),
            el("h3",{},"Create a Mesh from an Image"),
            el("p",{},"Choose how to turn a reference—or an image you create—into a 3D asset."),
            hint("Each method has its own steps, previews and exports. Start with Single Image or Text for the most direct route."),
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
        hint('Powered by HairDeck from hyz317 and its researchers, with FengLairh’s ComfyUI integration. Create and fit stylized hair cards, adjust materials, and export GLB or spring-bone VRM with motion preview.')));
    return el("div",{},card,el("div",{class:"future-workflows"},imageCard,hairCard,...planned.map(([id,name,description])=>el("article",{class:"planned-workflow"},artwork(id,name),el("div",{},el("span",{class:"badge"},"Coming soon"),el("h3",{},name),hint(description))))));
}
