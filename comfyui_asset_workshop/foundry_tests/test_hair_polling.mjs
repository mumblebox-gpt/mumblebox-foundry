import {msg, sourceText, sourceMessage, setText} from "../web/foundry/i18n.js";
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

test('terminal hair job unlocks Retry when task cleanup finishes after the error arrives', async()=>{
    const source=(await readFile(new URL('../web/foundry/hair/controller.js',import.meta.url),'utf8'))
        .replace(/^import .*;\r?\n/gm,'').replaceAll('import.meta.url',JSON.stringify(import.meta.url)).replace('export class HairWizard','return class HairWizard');
    let active=true;
    const record=()=>({active,status:'failed',stage:'Generating hair',error:'missing dependency',variants:[]});
    const HairWizard=new Function('request','setTimeout','hairFileURL','msg','sourceMessage','setText',source)(async()=>record(),()=>0,()=>{},msg,sourceMessage,setText);
    const wizard=Object.create(HairWizard.prototype);
    Object.assign(wizard,{runId:'existing',run:{...record(),status:'running'},render(){this.renders=(this.renders||0)+1;this.retryVisible=!this.run.active;},paintProgress(){}});
    await wizard.poll();
    assert.equal(wizard.retryVisible,false);
    active=false;
    await wizard.poll();
    assert.equal(wizard.retryVisible,true);
    assert.equal(wizard.renders,2);
});
