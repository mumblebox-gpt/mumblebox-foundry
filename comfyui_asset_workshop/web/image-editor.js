import {imageMagnet} from './image-selection.js';
// Selection tools and review stay in this dialog while the visible graph executes.
export async function openImageEditor({element:el, sourceURL, title, model, generate, accept, stop, progress, download,
                                      mode="image", initialMaskURL=null, prepareMask=null, keepLabel=null,
                                      container=document.body,comparison=null,onSwitch=null,settingsSummary=null}) {
    const foreground=mode==="foreground";
    container.querySelector(".aw-image-editor")?.close();
    const source = new Image();
    source.src = sourceURL;
    await source.decode();
    let magnet;
    const mask = document.createElement("canvas"), canvas = document.createElement("canvas");
    mask.width = canvas.width = source.naturalWidth;
    mask.height = canvas.height = source.naturalHeight;
    canvas.setAttribute("aria-label", "Image selection canvas");
    canvas.tabIndex = 0;
    const context = canvas.getContext("2d"), selected = mask.getContext("2d");
    const operations = [];
    let initialMask=null;
    async function loadInitialMask(url) {
        const saved=new Image();saved.src=url;await saved.decode();
        if(saved.naturalWidth!==mask.width || saved.naturalHeight!==mask.height)
            throw Error("The saved foreground does not match this image. Remove its background again.");
        initialMask=document.createElement("canvas");initialMask.width=mask.width;initialMask.height=mask.height;
        const context=initialMask.getContext("2d");context.drawImage(saved,0,0);
        const pixels=context.getImageData(0,0,mask.width,mask.height);
        for(let i=0;i<pixels.data.length;i+=4) {
            pixels.data[i+3]=pixels.data[i];pixels.data[i]=pixels.data[i+1]=pixels.data[i+2]=255;
        }
        context.putImageData(pixels,0,0);operations.push({tool:"initial"});
    }
    if(initialMaskURL)await loadInitialMask(initialMaskURL);
    let tool = "rectangle", stroke = null, polygon = [], anchors = [], busy = false, candidate = null;
    let resultImage = null, display = "selection", zoom = 1, cursor = null, phase = 0;
    const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
    const fill = document.createElement("canvas"), outline = document.createElement("canvas"), ants = document.createElement("canvas");
    for(const layer of [fill,outline,ants]) {layer.width=canvas.width;layer.height=canvas.height;}
    let dots, stripes, screenPixel = 1;
    const status = el("p", {role:"status",class:"editor-status"}, foreground?"The highlighted area is kept. Erase background or paint missing parts of the object.":"Draw over the area you want to change.");
    const progressBar = el("progress",{"aria-label":"Image edit progress",hidden:true});
    const prompt = el("textarea", {"aria-label":"Describe the selected-area change",
        placeholder:"For example: Change this handle to cobalt blue. Keep its shape."});
    const width = el("input", {type:"range",min:1,max:512,step:1,value:40,"aria-label":"Brush size in image pixels"});
    const featherDefault=foreground?0:4;
    const feather = el("input", {type:"range",min:0,max:32,step:1,value:featherDefault,"aria-label":"Edge softness in image pixels"});
    const replaceDetail = el("input", {type:"checkbox","aria-label":"Replace selected details"});
    replaceDetail.addEventListener("change",()=>rebuild());
    const button = (text, action, cls="") => el("button",{type:"button",class:cls,onclick:action},text);
    const paths = {
        ellipse:'M12 4a10 8 0 1 0 0 16 10 8 0 0 0 0-16Z',
        magnetic:'M5 4v9a7 7 0 0 0 14 0V4h-4v9a3 3 0 0 1-6 0V4Z',
        rectangle:"M4 4h16v16H4z", brush:"m14 5 5-3 3 3-9 10-4-4z M9 13c-6-1-2 7-7 7 6 2 10-1 9-5",
        polygon:"m5 5 14-2 2 14-10 4-8-9z M4 4h2v2H4z M18 2h2v2h-2z M20 16h2v2h-2z",
        finish:"m4 12 5 5L20 6", erase:"m4 12 9-9 8 8-9 9H9z M8 8l8 8 M12 20h9",
        undo:"M9 5 3 11l6 6 M3 11h10a7 7 0 0 1 7 7",
        clear:"M5 5l14 14 M19 5 5 19", all:"M3 8V3h5 M16 3h5v5 M21 16v5h-5 M8 21H3v-5",
        reset:"M3 10a9 9 0 1 1 2 9 M3 3v7h7",
    };
    const labelButton = (target,text,kind) => {
        const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
        for(const [key,value] of Object.entries({viewBox:"0 0 24 24",width:20,height:20,fill:"none",stroke:"currentColor","stroke-width":1.8,"stroke-linecap":"round","stroke-linejoin":"round","aria-hidden":"true"})) svg.setAttribute(key,value);
        const path=document.createElementNS(svg.namespaceURI,"path");path.setAttribute("d",paths[kind]);svg.append(path);
        target.replaceChildren(svg,el("span",{},text));
    };
    const slider = (input,label,initial) => {
        const value=el("output",{},`${initial} px`);
        const reset=button("Reset",()=>{input.value=initial;input.dispatchEvent(new Event("input"));},"editor-reset");
        labelButton(reset,"Reset","reset");reset.setAttribute("aria-label",`Reset ${label.toLowerCase()} to ${initial} pixels`);
        reset.title=`Default: ${initial} pixels`;
        input.addEventListener("input",()=>{value.textContent=`${input.value} px`;paint();});
        return {reset,element:el("div",{class:"editor-slider"},el("label",{},el("span",{class:"editor-slider-label"},label,value),input),reset)};
    };
    const brushControl=slider(width,"Brush size",40), softnessControl=slider(feather,"Edge softness",featherDefault);
    if(foreground) feather.addEventListener("input",()=>rebuild());
    const tools = {};
    const toolRow = el("div",{class:"row editor-tools",role:"toolbar","aria-label":"Selection tools"});
    for (const [value,label] of Object.entries({rectangle:"Rectangle",ellipse:"Ellipse",brush:"Brush",polygon:"Polygon lasso",magnetic:"Magnetic lasso",erase:"Erase"})) {
        tools[value] = button(label,()=>{
            if(['polygon','magnetic'].includes(value) && tool===value && polygon.length) {finishPolygon();return;}
            tool=value; stroke=null; polygon=[]; anchors=[]; display="selection"; paint(); update();
        });
        labelButton(tools[value],label,value);
        tools[value].title={rectangle:"Drag to select a rectangular area.",ellipse:"Drag to select an oval area.",magnetic:"Click anchors along an edge; the lasso follows nearby contrast. Click again to finish after three anchors.",brush:foreground?"Paint parts of the object to keep.":"Paint the area to change.",polygon:"Click at least three points, then click this button again to finish.",erase:foreground?"Erase background from the kept area.":"Brush away part of the selection."}[value];
        tools[value].setAttribute("aria-pressed",String(value===tool));
        toolRow.append(tools[value]);
    }
    const undo = button("Undo selection",()=>{if(polygon.length)polygon.splice(anchors.pop()??Math.max(0,polygon.length-1));else operations.pop();rebuild();});
    const clear = button("Clear selection",()=>{operations.length=0; polygon=[]; anchors=[]; stroke=null; rebuild();});
    const all = button("Select whole image",()=>{push({tool:"rectangle",points:[[0,0],[mask.width,mask.height]]});});
    labelButton(undo,"Undo selection","undo");labelButton(clear,"Clear selection","clear");labelButton(all,"Select whole image","all");
    toolRow.append(undo,clear,all);
    function finishPolygon() {
        if(anchors.length<3) {status.textContent="Add at least three points to finish the polygon.";return;}
        if(tool==='magnetic'){magnet??=imageMagnet(source);polygon.push(...magnet(polygon.at(-1),polygon[0]));}
        const points=polygon;polygon=[];anchors=[];push({tool:"polygon",points});
        status.textContent=foreground?"Selection ready. Preview the cutout to check the kept area.":"Selection ready. Describe what you want to change.";
    }
    const show = el("div",{class:"row"});
    const comparisonButtons=[];
    for (const [value,label] of Object.entries({selection:"Show selection",original:"Show original",edited:"Show edited preview"}))
        comparisonButtons.push(button(label,()=>{display=value;paint();update();}));
    show.append(...comparisonButtons);
    const animationPreference=localStorage.getItem("mumblebox.animateSelection");
    const animateSelection=el("input",{type:"checkbox","aria-label":"Animate selection"});
    animateSelection.checked=animationPreference===null?!reducedMotion.matches:animationPreference==="true";
    animateSelection.addEventListener("change",()=>{
        localStorage.setItem("mumblebox.animateSelection",String(animateSelection.checked));phase=0;paint();
    });
    show.append(el("label",{class:"editor-animation"},animateSelection,"Animate selection"));
    const viewport = el("div",{class:`editor-viewport${foreground?" foreground-viewport":""}`},canvas);
    const applyZoom = () => {
        const fit=Math.min((viewport.clientWidth-2)/canvas.width,(viewport.clientHeight-2)/canvas.height);
        canvas.style.width=`${canvas.width*fit*zoom}px`;canvas.style.maxWidth="none";
        screenPixel=1/(fit*zoom);buildOverlay();paint();
    };
    const zoomTools = el("div",{class:"row"},button("Zoom in",()=>{zoom=Math.min(4,zoom+.5);applyZoom();}),
        button("Zoom out",()=>{zoom=Math.max(1,zoom-.5);applyZoom();}),
        button("Fit image",()=>{zoom=1;applyZoom();}));
    const generateButton = button(foreground?"Remove Background":"Generate edit preview",()=>run(false),"primary");
    const retry = button("Try again",()=>run(true));
    retry.hidden=foreground;
    const keep = button(keepLabel||(foreground?"Keep Cutout":"Keep this edit"),async()=>{
        if(!candidate || busy) return;
        busy=true;update();
        try {await accept(candidate);dialog.close();} catch(error){status.textContent=error.message;}
        finally {busy=false;update();}
    },"primary");
    const stopButton = button("Stop generation",async()=>{await stop();});
    const cancel = button("Cancel",()=>{if(!busy) dialog.close();});
    const resultDownload = el("span");
    const dialog = el("dialog",{class:"aw aw-image-editor","aria-labelledby":"aw-editor-title"},
        el("header",{class:"editor-header"},el("div",{},el("h2",{id:"aw-editor-title"},`${foreground?"Background removal":"Edit image"} — ${title}`),
            el("p",{class:"hint"},foreground?"Keep the object, remove its surroundings, then preview and save the cutout. Your original image stays unchanged.":"Select an area, describe the change, then review the preview before keeping it.")),cancel),
        el("div",{class:"editor-body"},
            el("section",{},toolRow,el("p",{class:"hint"},
                foreground?"Highlighted areas stay in the cutout. Use Brush or Polygon lasso to add missing parts; use Erase to remove background.":"Select the area to change. Polygon lasso becomes Finish polygon after your first point; add at least three points, then click it again."),
                viewport,show,zoomTools),
            el("aside",{},foreground?null:el("label",{},"Describe the change",prompt),
                foreground?null:el("label",{class:"editor-animation",
                    title:"Hide the old detail inside your selection before rebuilding it. Leave off when changing colors or materials while keeping the same shape."},
                    replaceDetail,"Replace selected details"),
                foreground?null:el("p",{class:"hint"},"Turn on to remove or rebuild a part. Leave off to keep its shape while changing its color or material."),
                el("div",{class:"editor-sliders"},brushControl.element,softnessControl.element),
                el("p",{class:"hint"},foreground?"Edge softness fades the cutout inward. Start at 0 to preserve thin parts and the automatic mask's soft edges.":"Edge softness blends inward from your selection. Pixels outside it stay unchanged."),
                el("p",{class:"hint"},foreground?"This changes transparency only. It does not redraw the object or load an image generator.":settingsSummary??`Using ${model} and your current steps, CFG, seed and LoRAs. Try again uses a new seed.`),
                status,progressBar,el("div",{class:"row"},generateButton,stopButton),
                el("div",{class:"row"},keep,retry),
                el("p",{class:"hint"},foreground?"Your original image stays unchanged. Keeping the cutout saves its transparency.":"Your original stays in use until you choose Keep this edit."),
                el("div",{class:"row"},download(),resultDownload))));
    if(comparison){
        const pane=el('figure',{class:'editor-pair-reference'},el('figcaption',{},comparison.label+' · unchanged comparison'),
            el('img',{src:comparison.url,alt:comparison.label}));
        if(onSwitch)pane.append(button('Edit '+comparison.label,()=>{if(!busy){dialog.close();onSwitch();}}));
        const pair=el('div',{class:'editor-pair'},viewport,pane);
        toolRow.parentElement.insertBefore(pair,show);
        zoomTools.append(button('Toggle comparison',()=>{pane.hidden=!pane.hidden;pair.classList.toggle('single',pane.hidden);applyZoom();}));
    }
    container.append(dialog);
    const previousFocus = document.activeElement;
    dialog.addEventListener("cancel",event=>{if(busy){event.preventDefault();status.textContent="Use Stop generation before closing the editor.";}});
    dialog.addEventListener("close",()=>{clearInterval(timer);clearInterval(animation);resize.disconnect();dialog.remove();previousFocus?.focus?.({preventScroll:true});});
    dialog.addEventListener("keydown",event=>{
        if(event.target===canvas && !busy && event.key==="Enter" && polygon.length) {event.preventDefault();finishPolygon();}
        if(event.target===canvas && !busy && (event.ctrlKey || event.metaKey) && event.key==="z") {event.preventDefault();undo.click();}
    });
    function draw(op) {
        const points=op.points;
        selected.save();
        selected.globalCompositeOperation=op.tool==="erase"?"destination-out":"source-over";
        selected.fillStyle=selected.strokeStyle="white";
        selected.lineWidth=op.width || 1;selected.lineJoin=selected.lineCap="round";
        if(op.tool==="initial") selected.drawImage(initialMask,0,0);
        else if(op.tool==="rectangle") {
            const [a,b]=points;selected.fillRect(Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.abs(b[0]-a[0]),Math.abs(b[1]-a[1]));
        } else if(op.tool==='ellipse') {
            const [a,b]=points;selected.beginPath();selected.ellipse((a[0]+b[0])/2,(a[1]+b[1])/2,Math.abs(a[0]-b[0])/2,Math.abs(a[1]-b[1])/2,0,0,Math.PI*2);selected.fill();
        } else if(op.tool==="polygon") {
            selected.beginPath();points.forEach(([x,y],i)=>i?selected.lineTo(x,y):selected.moveTo(x,y));
            selected.closePath();selected.fill();
        } else {
            selected.beginPath();points.forEach(([x,y],i)=>i?selected.lineTo(x,y):selected.moveTo(x,y));
            if(points.length===1){selected.arc(points[0][0],points[0][1],selected.lineWidth/2,0,2*Math.PI);selected.fill();}
            else selected.stroke();
        }
        selected.restore();
    }
    function rebuild() {
        selected.clearRect(0,0,mask.width,mask.height);
        for(const op of operations) draw(op);
        if(stroke) draw(stroke);
        candidate=null;resultImage=null;display="selection";resultDownload.replaceChildren();
        buildOverlay();paint();update();
        if(!stroke && !polygon.length)
            status.textContent=foreground
                ? (operations.length?"Highlighted areas will be kept. Preview the cutout to check its edges.":"Select the object to keep.")
                : (operations.length?"Selection updated. Describe the change, then generate a preview.":"Draw over the area you want to change.");
    }
    function push(op) {
        if(operations.length>=2000) {status.textContent="This selection has 2000 strokes. Undo or clear it before adding more.";return;}
        operations.push(op);rebuild();
    }
    function buildOverlay() {
        const tile=document.createElement("canvas");tile.width=tile.height=Math.max(4,Math.round(10*screenPixel));
        const tileContext=tile.getContext("2d");
        tileContext.fillStyle="rgba(5,9,16,.40)";tileContext.fillRect(0,0,tile.width,tile.height);
        tileContext.fillStyle="rgba(255,211,105,.85)";tileContext.beginPath();
        tileContext.arc(tile.width/2,tile.height/2,Math.max(1,screenPixel),0,2*Math.PI);tileContext.fill();
        dots=context.createPattern(tile,"repeat");
        const fc=fill.getContext("2d");fc.clearRect(0,0,fill.width,fill.height);fc.drawImage(mask,0,0);
        fc.globalCompositeOperation="source-in";fc.fillStyle=dots;fc.fillRect(0,0,fill.width,fill.height);fc.globalCompositeOperation="source-over";
        const oc=outline.getContext("2d");oc.clearRect(0,0,outline.width,outline.height);
        const radius=2.5*screenPixel;
        for(const [x,y] of [[-1,-1],[0,-1],[1,-1],[-1,0],[1,0],[-1,1],[0,1],[1,1]]) oc.drawImage(mask,x*radius,y*radius);
        oc.globalCompositeOperation="destination-out";oc.drawImage(mask,0,0);oc.globalCompositeOperation="source-over";
        const stripe=document.createElement("canvas");stripe.width=stripe.height=Math.max(4,Math.round(12*screenPixel));
        const sc=stripe.getContext("2d"), size=stripe.width;
        sc.fillStyle="#080b10";sc.fillRect(0,0,size,size);sc.fillStyle="#fff";
        for(const offset of [-size,0,size]) {
            sc.beginPath();sc.moveTo(offset,0);sc.lineTo(offset+size/2,0);
            sc.lineTo(offset+size/2-size,size);sc.lineTo(offset-size,size);sc.closePath();sc.fill();
        }
        stripes=context.createPattern(stripe,"repeat");
    }
    function paint() {
        context.clearRect(0,0,canvas.width,canvas.height);
        context.drawImage(display==="edited" && resultImage?resultImage:source,0,0,canvas.width,canvas.height);
        if(display==="selection") {
            context.drawImage(fill,0,0);
            if(stripes) {
                stripes.setTransform(new DOMMatrix().translate(phase*screenPixel,0));
                const ac=ants.getContext("2d");ac.clearRect(0,0,ants.width,ants.height);
                ac.fillStyle=stripes;ac.fillRect(0,0,ants.width,ants.height);
                ac.globalCompositeOperation="destination-in";ac.drawImage(outline,0,0);ac.globalCompositeOperation="source-over";
                context.drawImage(ants,0,0);
            }
            if(polygon.length) {
                context.save();context.lineJoin="round";context.beginPath();
                polygon.forEach(([x,y],i)=>i?context.lineTo(x,y):context.moveTo(x,y));
                if(cursor) context.lineTo(...cursor);
                if(polygon.length>=3) {context.closePath();context.fillStyle=dots;context.fill();}
                context.strokeStyle="#080b10";context.lineWidth=5*screenPixel;context.stroke();
                context.strokeStyle="#fff";context.lineWidth=2.5*screenPixel;context.setLineDash([6*screenPixel,6*screenPixel]);
                context.lineDashOffset=-phase*screenPixel;context.stroke();context.setLineDash([]);
                for(const [x,y] of polygon){
                    context.beginPath();context.arc(x,y,4*screenPixel,0,2*Math.PI);
                    context.fillStyle="#ffd369";context.fill();context.strokeStyle="#080b10";context.lineWidth=2*screenPixel;context.stroke();
                }
                context.restore();
            }
            if(cursor && !busy) {
                const [x,y]=cursor;context.save();context.beginPath();
                if(tool==="brush" || tool==="erase") context.arc(x,y,Number(width.value)/2,0,2*Math.PI);
                context.moveTo(x-9*screenPixel,y);context.lineTo(x+9*screenPixel,y);
                context.moveTo(x,y-9*screenPixel);context.lineTo(x,y+9*screenPixel);
                context.strokeStyle="#080b10";context.lineWidth=4*screenPixel;context.stroke();
                context.strokeStyle="#fff";context.lineWidth=1.5*screenPixel;context.stroke();context.restore();
            }
        }
    }
    function update() {
        for(const [value,b] of Object.entries(tools)){b.disabled=busy;b.setAttribute("aria-pressed",String(value===tool));}
        undo.disabled=busy || (!operations.length && !polygon.length);
        clear.disabled=busy || (!operations.length && !polygon.length);
        all.disabled=busy;
        const polygonLabel=polygon.length?"Finish polygon":"Polygon lasso";
        if(tools.polygon.textContent!==polygonLabel) labelButton(tools.polygon,polygonLabel,polygon.length?"finish":"polygon");
        labelButton(tools.magnetic,tool==='magnetic'&&polygon.length?'Finish magnetic lasso':'Magnetic lasso',tool==='magnetic'&&polygon.length?'finish':'magnetic');
        generateButton.disabled=busy || !!polygon.length || !operations.length || (!foreground && !prompt.value.trim());
        retry.disabled=busy || !candidate;keep.disabled=busy || !candidate;cancel.disabled=busy;
        stopButton.hidden=!busy || (foreground&&!prepareMask);progressBar.hidden=!busy;prompt.disabled=width.disabled=feather.disabled=replaceDetail.disabled=busy;
        brushControl.reset.disabled=softnessControl.reset.disabled=busy;
        canvas.style.cursor=display==="selection" && !busy?"none":"default";
        for(const b of comparisonButtons) {
            const chosen=b.textContent==={selection:"Show selection",original:"Show original",edited:"Show edited preview"}[display];
            b.setAttribute("aria-pressed",String(chosen));
            b.disabled=b.textContent==="Show edited preview" && !candidate;
        }
    }
    function point(event) {
        const box=canvas.getBoundingClientRect();
        return [Math.max(0,Math.min(mask.width,(event.clientX-box.left)*mask.width/box.width)),
                Math.max(0,Math.min(mask.height,(event.clientY-box.top)*mask.height/box.height))];
    }
    canvas.addEventListener("pointerdown",event=>{
        if(busy || event.button!==0) return;
        event.preventDefault();canvas.focus();display="selection";
        if(tool==='polygon'||tool==='magnetic'){
            const next=point(event);
            anchors.push(polygon.length);
            if(tool==='magnetic'&&polygon.length){magnet??=imageMagnet(source);polygon.push(...magnet(polygon.at(-1),next));}
            else polygon.push(next);
            candidate=null;resultImage=null;resultDownload.replaceChildren();
            status.textContent=polygon.length<3?"Click at least three points, then Finish polygon.":"Add more points or click Finish polygon.";
            paint();update();return;
        }
        canvas.setPointerCapture(event.pointerId);
        stroke={tool,width:Math.max(1,Math.min(512,Number(width.value)||40)),points:[point(event)]};
        if(tool==='rectangle'||tool==='ellipse') stroke.points.push(point(event));
        rebuild();
    });
    canvas.addEventListener("pointermove",event=>{
        cursor=point(event);
        if(!stroke) {paint();return;}
        if(stroke.tool==='rectangle'||stroke.tool==='ellipse') stroke.points[1]=point(event);
        else if(stroke.points.length<10000) stroke.points.push(point(event));
        rebuild();
    });
    canvas.addEventListener("pointerup",event=>{
        if(!stroke) return;
        const completed=stroke;stroke=null;push(completed);
        if(canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointercancel",()=>{stroke=null;rebuild();});
    canvas.addEventListener("pointerleave",()=>{cursor=null;paint();});
    prompt.addEventListener("input",update);
    async function run(random) {
        if(busy) return;
        busy=true;candidate=null;resultImage=null;display="selection";resultDownload.replaceChildren();
        paint();update();status.textContent=foreground?"Preparing the cutout preview…":"Preparing your edit…";
        try {
            const exportMask=document.createElement("canvas");exportMask.width=mask.width;exportMask.height=mask.height;
            const ctx=exportMask.getContext("2d");ctx.fillStyle="black";ctx.fillRect(0,0,mask.width,mask.height);ctx.drawImage(mask,0,0);
            const blob=await new Promise(resolve=>exportMask.toBlob(resolve,"image/png"));
            const result=await generate({mask:blob,prompt:prompt.value,feather:Number(feather.value),
                replaceDetail:replaceDetail.checked,random});
            candidate=result;resultImage=new Image();resultImage.src=result.url;await resultImage.decode();
            display="edited";paint();resultDownload.replaceChildren(result.download);
            status.textContent=foreground?"Background removed. Keep the cutout to continue, or return to Show selection to adjust it.":`Preview ready. Seed used: ${result.recipe.seed}. Compare it with the original, then keep it or try again.`;
        } catch(error) {status.textContent=error.message;}
        finally {busy=false;update();}
    }
    const timer=setInterval(()=>{
        if(!busy) return;
        const state=progress();
        if(state?.message) status.textContent=state.message;
        if(state?.progress?.max) {progressBar.max=state.progress.max;progressBar.value=state.progress.value;}
        else progressBar.removeAttribute("value");
    },700);
    const animation=setInterval(()=>{
        if(!dialog.open || document.hidden || display!=="selection" || !animateSelection.checked || (!operations.length && !polygon.length && !stroke)) return;
        phase=(phase+1)%12;paint();
    },120);
    const resize=new ResizeObserver(applyZoom);
    dialog.showModal();resize.observe(viewport);rebuild();applyZoom();paint();update();
    if(foreground) canvas.focus();else prompt.focus();
    if(foreground&&prepareMask) {
        busy=true;update();status.textContent="Finding the object’s outline…";
        try {await loadInitialMask(await prepareMask());rebuild();status.textContent="The highlighted area is kept. Adjust it if needed, then choose Remove Background.";}
        catch(error){status.textContent=error.message;}
        finally {busy=false;update();}
    }
    return dialog;
}
