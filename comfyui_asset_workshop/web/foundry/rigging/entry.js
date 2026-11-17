import {button,el} from "../dom.js";
import {msg,sourceMessage} from "../i18n.js";

export const rigText=(key,args)=>msg("rigging."+key,args);

export function afterExport(shell,identity,variant,eligible=true){
    if(!eligible||!identity||(!identity.exportId&&!identity.recordId))return null;
    return el("div",{class:"rig-next-step"},
        el("span",{},rigText("after_export")),
        button(rigText("rig_mesh"),()=>shell.openRigWizard({...identity,variant})
            .catch(error=>shell.message(sourceMessage(error.message),true))));
}
