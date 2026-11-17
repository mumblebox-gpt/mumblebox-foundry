import {button,el,field,hint} from "../dom.js";
import {setText,sourceMessage} from "../i18n.js";
import {rigText as t} from "./entry.js";

export function chainPoints(attachment, tip, segments){
    if(!Number.isInteger(segments)||segments<1||segments>32||
        ![attachment,tip].every(point=>Array.isArray(point)&&point.length===3&&point.every(Number.isFinite))||
        Math.hypot(...attachment.map((coordinate,axis)=>tip[axis]-coordinate))/segments<1e-6){
        throw RangeError("Place the tip away from the attachment and choose 1 to 32 segments.");
    }
    return Array.from({length:segments+1},(_,index)=>
        attachment.map((coordinate,axis)=>coordinate+(tip[axis]-coordinate)*index/segments));
}

const defaults={hand:3,finger:3,toes:2,tail:5,bird_wing:3,bat_wing:3,limb:3,custom:3};
const digits=["thumb","index","middle","ring","little"];

export class PartAuthor {
    constructor(viewport, parent, revision, preview, submit){
        this.viewport=viewport;
        this.parent=parent;
        this.revision=revision;
        this.preview=preview;
        this.waypoints=[];
        this.attachment=parent.tail;
        const direction=parent.tail.map((value,axis)=>value-parent.head[axis]);
        this.tip=parent.tail.map((value,axis)=>value+direction[axis]);
        this.type=el("select",{onchange:()=>{this.segments.value=defaults[this.type.value];this.redraw();}},
            ...Object.keys(defaults).map(type=>el("option",{value:type},t("part_"+type))));
        this.type.value="custom";
        this.segments=el("input",{type:"number",min:1,max:32,step:1,value:3,oninput:()=>this.redraw()});
        this.digit=el("select",{onchange:()=>this.redraw()},
            ...digits.map(value=>el("option",{value},t("digit_"+value))));
        this.digit.value="index";
        this.digitField=field(t("digit"),this.digit);
        this.width=button(t("part_width"),()=>this.viewport.placePoint(this.widthPoint||this.tip,point=>{
            this.widthPoint=point;this.redraw();
        }));
        this.pathPoint=button(t("part_waypoint"),()=>this.viewport.placePoint(this.tip,point=>{
            if(this.waypoints.length<6)this.waypoints.push(point);
            this.redraw();
        }));
        this.clear=button(t("part_clear_waypoints"),()=>{this.waypoints=[];this.widthPoint=null;this.redraw();});
        this.note=hint(t("place_part_tip"));
        this.apply=button(t("apply_part"),()=>submit(this.command()));
        this.element=el("div",{class:"rig-part-author",onkeydown:event=>{
            if(event.key==="Escape"){event.preventDefault();submit(null);}
        }},
        field(t("part_type"),this.type),field(t("segments"),this.segments),this.digitField,
        button(t("place_tip"),()=>this.viewport.placePoint(this.tip,point=>{
            this.tip=point;this.redraw();
        })),this.width,this.pathPoint,this.clear,this.note,el("div",{class:"actions"},this.apply,
            button(t("cancel_part"),()=>submit(null))));
        this.redraw();
    }

    redraw(){
        this.apply.disabled=true;
        this.digitField.hidden=this.type.value!=="finger";
        this.width.hidden=!["hand","toes","bird_wing","bat_wing"].includes(this.type.value);
        this.pathPoint.hidden=["hand","toes","finger"].includes(this.type.value);
        this.pathPoint.disabled=this.waypoints.length===6;
        const serial=this.serial=(this.serial||0)+1;
        clearTimeout(this.timer);
        try{
            chainPoints(this.attachment,this.tip,this.segments.valueAsNumber);
        }catch{
            this.viewport.ghostPart=null;
            this.viewport.draw();
            setText(this.note,t("invalid_part_tip"));
            return;
        }
        this.timer=setTimeout(async()=>{
            try{
                const {part}=await this.preview(this.payload());
                if(this.serial!==serial)return;
                this.viewport.ghostPart=part;
                this.apply.disabled=false;
                setText(this.note,t("place_part_tip"));
            }catch(error){
                if(this.serial!==serial)return;
                this.viewport.ghostPart=null;
                setText(this.note,sourceMessage(error.message,error.i18n));
            }
            this.viewport.draw();
        },100);
    }

    payload(){
        return {parent_id:this.parent.id,part:this.type.value,tip:this.tip,segments:this.segments.valueAsNumber,
            width_point:this.widthPoint,waypoints:this.pathPoint.hidden?[]:this.waypoints,digit:this.digit.value};
    }

    command(){
        return {action:"add_part",rigRevision:this.revision,...this.payload()};
    }

    dispose(){
        this.viewport.pointPicker=null;
        clearTimeout(this.timer);
        this.serial++;
        this.viewport.ghostPart=null;
        this.viewport.draw();
    }
}
