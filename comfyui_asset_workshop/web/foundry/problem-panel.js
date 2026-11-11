import {setText} from "./i18n.js";
import {msg, appendContent} from "./i18n.js";
import {el,button} from './dom.js';
export function problemPanel(message){
    const text=String(message||'This stage could not finish.');
    const technical=text.length>280||/Traceback|Node errors:|File \"|<urlopen error/.test(text);
    const topology=/Boundary exceeds|Remesh defects exceed/.test(text);
    const summary=topology?'QuadriFlow left openings in this mesh. Your saved triangle meshes are kept. Retry quads, or return to output choices to continue without them.':technical?text.split(/Traceback|Node errors:/)[0].slice(0,220).trim():text;
    const panel=el('div',{class:'error-panel',role:'alert'},el('p',{},summary||'This stage could not finish. Your saved work is kept.'));
    if(technical){const copied=el('span',{role:'status'});appendContent(panel, el('details',{},el('summary',{},msg("common.technical_details")),el('pre',{},text),
        button(msg("common.copy_details"),async()=>{try{await navigator.clipboard.writeText(text);setText(copied, msg("common.copied"));}catch{setText(copied, msg("common.select_the_details_and_copy_them"));}}),copied));}
    return panel;
}
