import {msg, appendContent, setText} from "./i18n.js";
import {el,button} from './dom.js';
import {buildProblemDetails} from "./problem-details.js";

export function problemPanel(message, context){
    const text=String(message||'This stage could not finish.');
    const technical=text.length>280||/Traceback|Node errors:|File \"|<urlopen error/.test(text);
    const topology=/Boundary exceeds|Remesh defects exceed/.test(text);
    const summary=topology?'QuadriFlow left openings in this mesh. Your saved triangle meshes are kept. Retry quads, or return to output choices to continue without them.':technical?text.split(/Traceback|Node errors:/)[0].slice(0,220).trim():text;
    const panel=el('div',{class:'error-panel',role:'alert'},el('p',{},summary||'This stage could not finish. Your saved work is kept.'));
    if(technical)appendContent(panel, el('details',{},el('summary',{},msg("common.technical_details")),el('pre',{},text)));
    if(context || technical){
        const status=el('span',{role:'status'});
        const selectable=el('pre',{hidden:true,tabIndex:0,'aria-label':msg("common.copy_details")});
        const copy=button(msg("common.copy_details"),async()=>{
            if(copy.disabled)return;
            copy.disabled=true;
            const report=buildProblemDetails({...context,message:text});
            try{
                await navigator.clipboard.writeText(report);
                if(panel.isConnected){
                    selectable.hidden=true;
                    setText(status,msg("common.copied"));
                }
            }catch{
                if(panel.isConnected){
                    setText(selectable,report);
                    selectable.hidden=false;
                    setText(status,msg("common.select_the_details_and_copy_them"));
                }
            }finally{copy.disabled=false;}
        });
        appendContent(panel,el('div',{class:'actions'},copy,status),selectable);
    }
    return panel;
}
