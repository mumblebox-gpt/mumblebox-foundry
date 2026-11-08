import {el,icon} from './dom.js';
export const TEXT_SIZES=[['default','Default',100],['larger','112%',112],['large','125%',125],['extra-large','150%',150],['175','175%',175],['200','200%',200]];
export function fontControl(shell){
    const menu=el('details',{class:'font-menu'}),summary=el('summary',{'aria-label':'Font size'},icon('glasses',18),'Font',icon('chevron',14));
    const options=TEXT_SIZES.map(([value,label,percent])=>{
        const input=el('input',{type:'radio',name:'foundry-font-size',value,checked:value==='default',onchange:()=>{shell.setFontSize(value);menu.open=false;summary.focus();}});
        return el('label',{class:'font-option'},input,el('span',{},label));
    });
    menu.append(summary,el('div',{class:'font-options',role:'group','aria-label':'Text size'},...options));
    menu.addEventListener('toggle',()=>{
        if(!menu.open)return;const popup=menu.querySelector('.font-options'),root=shell.root.getBoundingClientRect(),scale=root.width/shell.root.offsetWidth||1;
        popup.style.maxWidth=Math.max(160,shell.root.offsetWidth-24)+'px';popup.style.left='0';popup.style.right='auto';
        const r=popup.getBoundingClientRect();const shift=Math.min(0,root.right-12-r.right);
        popup.style.left=(Math.max(shift,root.left+12-r.left)/scale)+'px';
    });
    const events=new AbortController();
    shell.root.addEventListener('click',e=>{if(!menu.contains(e.target))menu.open=false;},{signal:events.signal});
    menu.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();menu.open=false;summary.focus();}});
    return {element:menu,update(value){for(const input of menu.querySelectorAll('input'))input.checked=input.value===value;summary.title='Text size: '+(TEXT_SIZES.find(x=>x[0]===value)?.[1]||'Default');},dispose(){events.abort();}};
}
