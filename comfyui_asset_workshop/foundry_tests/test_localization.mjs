import test from "node:test";
import assert from "node:assert/strict";
import {msg, setLanguage, sourceText, sourceMessage, capabilityMessages, bindAttribute, setText} from "../web/foundry/i18n.js";

class FakeNode {
    constructor(tag = "") {this.tagName=tag;this.childNodes=[];this.attributes=new Map();this.dataset={};this.value="";this.className="";}
    append(...nodes) {this.childNodes.push(...nodes);}
    prepend(...nodes) {this.childNodes.unshift(...nodes);}
    replaceChildren(...nodes) {this.childNodes=nodes;}
    setAttribute(key, value) {this.attributes.set(key, String(value));}
    getAttribute(key) {return this.attributes.get(key);}
    addEventListener() {}
    get firstChild() {return this.childNodes[0];}
    get textContent() {return this.nodeType===3?this.data:this.childNodes.map(node=>node.textContent).join("");}
}
globalThis.Node=FakeNode;
globalThis.document={createElement:tag=>new FakeNode(tag),createTextNode:value=>Object.assign(new FakeNode(),{nodeType:3,data:value}),createDocumentFragment:()=>new FakeNode()};
const {el}=await import("../web/foundry/dom.js");

test("switching updates only bound text and keeps form/viewer identities", () => {
    setLanguage("en");
    const input=el("input",{value:"Settings <b>我的道具</b>"});
    const viewer=el("div",{"data-model":"saved.glb"});
    const icon=el("span",{class:"icon"});
    const button=el("button",{},icon,msg("common.settings"));
    const root=el("main",{},input,viewer,button);
    setLanguage("zh-CN");
    assert.equal(button.textContent,"设置");
    assert.equal(root.childNodes[0],input);
    assert.equal(root.childNodes[1],viewer);
    assert.equal(button.childNodes[0],icon);
    assert.equal(input.value,"Settings <b>我的道具</b>");
    setLanguage("en");
    assert.equal(button.textContent,"Settings");
});

test("progress updates reuse their text node and keep the latest binding", () => {
    const progress=el("p");
    setText(progress,msg("ccore.downloading",{percent:1}));
    const original=progress.firstChild;
    for(let percent=0;percent<1000;percent++)setText(progress,msg("ccore.downloading",{percent}));
    assert.equal(progress.firstChild,original);
    setLanguage("zh-CN");
    assert.equal(progress.textContent,"正在下载 999%");
});

test("a raw attribute replacement releases its previous translation binding", () => {
    const node=el("div");
    bindAttribute(node,"title",msg("common.settings"));
    bindAttribute(node,"title","user-chosen title");
    setLanguage("en");
    assert.equal(node.getAttribute("title"),"user-chosen title");
});

test("source serialization preserves English machine-facing values", () => {
    setLanguage("zh-CN");
    assert.equal(sourceText(msg("common.settings")),"Settings");
    assert.equal(JSON.stringify({name:msg("common.settings")}),JSON.stringify({name:"Settings"}));
});

test("capability captions translate while model prompts and defaults remain exact", () => {
    const original={label:"Settings",prompt:"Settings",defaults:{prompt:"Do not rewrite 我"},config:{name:"Settings"}};
    const result=capabilityMessages(original);
    assert.equal(String(result.label),"设置");
    assert.equal(result.prompt,"Settings");
    assert.equal(result.defaults,original.defaults);
    assert.equal(result.config,original.config);
});

test("recorded service messages resolve with their original parameters", () => {
    assert.equal(String(sourceMessage("Downloading 37%")),"正在下载37%");
    assert.equal(sourceMessage("unrecognized diagnostic /data/file.glb"),"unrecognized diagnostic /data/file.glb");
});
