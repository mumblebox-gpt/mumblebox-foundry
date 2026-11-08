import {el,button,hint} from '../dom.js';
import {dialog} from '../dialogs.js';
import {mountMesh} from '../wizard/preview.js';

export const hairFileURL=(id,path,download=false)=>'/mumblebox-foundry/v1/hair/runs/'+id+'/file?'+new URLSearchParams({path,...(download?{download:'1'}:{})});

const labels={preview:['result','HairDeck multi-view sheet'],preprocess:['input','HairDeck processing sheet'],model_input:['input','Model input crop'],hair_mask:['input','Detected hair'],face_mask:['input','Detected face'],base_color:['material','Base color and opacity'],normal:['material','Strand normal map'],roughness:['material','Roughness'],alpha:['material','Opacity'],uv_layout:['material','UV layout for painting'],metallic_roughness:['material','glTF metallic and roughness'],unity_metallic_smoothness:['material','Unity metallic and smoothness']};
export function displayFiles(item){
    if(item?.displays)return item.displays;
    // Older saved runs stay reviewable without rewriting their assets.
    return (item?.files||[]).flatMap(f=>{
        const role=Object.keys(labels).find(k=>f.filename===k+'.png'||f.filename.startsWith(k+'_0')&&f.filename.endsWith('.png'));
        return role?[{role,group:labels[role][0],label:labels[role][1],path:f.subfolder+'/'+f.filename}]:[];
    });
}

export function preprocessingWarnings(item){
    const data=item?.preprocess_notes||{};
    const messages={matte_uncertain:'HairDeck is unsure about this image’s segmentation. Check the processing sheet.',
        box_from_low_scores:'Hair or face detection had low confidence. Check the crop before continuing.',
        matte_disagree:'The foreground masks disagree. Review the processing sheet carefully.',
        box_fallback:'HairDeck used a fallback crop. Check that the complete hairstyle is visible.',
        no_person_mask:'No foreground person mask was detected.',no_hair:'HairDeck did not detect hair; the face was used to frame the reference.',
        no_hair_no_face:'Neither hair nor face was detected; HairDeck used the whole image.'};
    const explained=[data.status,...(data.notes||[])].filter(n=>messages[n]).map(n=>messages[n]);
    return [...new Set(explained.length?explained:data.warnings||[])];
}

export function imageSheet(wizard,item,group){
    const images=displayFiles(item).filter(f=>f.group===group);
    if(!images.length)return null;
    return el('div',{class:'hair-diagnostics','data-hair-sheet':group},...images.map(f=>el('figure',{},
        button(el('img',{src:hairFileURL(wizard.runId,f.path),alt:f.label,loading:'lazy'}),()=>{
            dialog(wizard.shell,f.label,el('img',{class:'hair-full-image',src:hairFileURL(wizard.runId,f.path),alt:f.label}));
        },{class:'hair-image-button','aria-label':'Enlarge '+f.label}),
        el('figcaption',{},f.label,el('a',{href:hairFileURL(wizard.runId,f.path,true),class:'hair-save-image'},'Download PNG')))));
}

export function hairViewer(wizard,item,{compact=false}={}){
    if(!item)return hint('The saved HairDeck preview will appear here.');
    const host=el('div',{class:'wizard-mesh hair-viewer'+(compact?' hair-viewer-compact':''),'aria-label':'HairDeck variation seed '+item.measurements?.seed});
    const state=(wizard.reviewState??={})[item.checkpoint]??={head:true,chains:false};
    const download=el('a',{class:'hair-view-download',title:'Static review GLB. Visible chain tubes are diagnostic geometry, not a bone rig.'},'Download view GLB');
    let disposed=false,cleanup,revision=0;
    const show=async()=>{
        const current=++revision;cleanup?.();host.replaceChildren();
        const key=(state.head?'head':'hair')+(state.chains?'_chains':'');
        const path=item.views?.[key]||(state.chains&&item.bone_model?item.bone_model:item.model);
        download.href=hairFileURL(wizard.runId,path,true);download.download=path.split('/').at(-1);
        try{
            const dispose=await mountMesh(host,hairFileURL(wizard.runId,path),wizard.cap.viewer_module);
            if(disposed||current!==revision)dispose();else{
                cleanup=dispose;host.dataset.loaded=path;host.hairViewer=dispose.viewer;
                // HairDeck's reference previews use a clear studio background.
                // Keep the native renderer, without a distracting modelling grid.
                dispose.viewer?.toggleGrid?.(false);dispose.viewer?.setBackgroundColor?.('#edf0e8');
            }
        }catch(error){if(!disposed&&current===revision)host.replaceChildren(el('p',{role:'alert'},error.message));}
    };
    wizard.disposers.push(()=>{disposed=true;revision++;cleanup?.();});
    setTimeout(()=>{if(!disposed)show();},0);
    const toolbar=el('div',{class:'hair-viewer-tools'},
        item.views?el('label',{},el('input',{type:'checkbox',checked:state.head,onchange:e=>{state.head=e.target.checked;wizard.remember();show();}}),'Reference head'):null,
        item.views?.head_chains||item.bone_model?el('label',{},el('input',{type:'checkbox',checked:state.chains,onchange:e=>{state.chains=e.target.checked;wizard.remember();show();}}),'Predicted chains'):null,
        button('Reset view',()=>{cleanup?.viewer?.fitToViewer();cleanup?.viewer?.forceRender();}),download);
    return el('section',{class:'hair-model-review'},toolbar,host,compact?null:hint('Drag to orbit; scroll to zoom. Orange chains show the prediction. The exported VRM contains the actual skinning and spring physics.'));
}

export function variationCards(wizard){
    return el('div',{class:'hair-variations','aria-label':'Compare HairDeck variations'},...(wizard.run?.variants||[]).map((item,index)=>
        el('article',{class:'hair-variation'+((wizard.selected||0)===index?' selected':''),'data-variation':index},
            el('header',{},el('h3',{},'Variation '+(index+1)),el('span',{},'Seed '+item.measurements.seed)),
            hairViewer(wizard,item,{compact:true}),
            hint(item.measurements.hair_cards+' cards · '+item.measurements.generated_chains+' predicted chains'),
            button((wizard.selected||0)===index?'Selected for editing and export':'Use this variation',()=>{
                wizard.selected=index;wizard.remember();wizard.render();
            },{'aria-pressed':String((wizard.selected||0)===index),class:(wizard.selected||0)===index?'primary':''}))));
}
