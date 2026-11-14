import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
const localeRequests = [];
let unavailableLocale;
const nativeFetch = globalThis.fetch;
globalThis.fetch = async (resource, options) => {
    const url = new URL(resource);
    if (url.protocol !== "file:") return nativeFetch(resource, options);
    const language = url.pathname.split("/").at(-1).replace(/\.json$/, "");
    localeRequests.push(language);
    if (language === unavailableLocale) return new Response("", {status: 503});
    return new Response(await readFile(url), {headers: {"Content-Type": "application/json"}});
};
const {msg, pluralMessage, setLanguage, currentLanguage, sourceText, sourceMessage, capabilityMessages, bindAttribute, setText} =
    await import("../web/foundry/i18n.js");

test("loads only the next language and can fetch a discarded language again", async () => {
    assert.deepEqual(localeRequests, []);
    await setLanguage("fr");
    assert.ok(localeRequests.length > 0);
    assert.deepEqual([...new Set(localeRequests)], ["fr"]);
    localeRequests.length = 0;
    await setLanguage("en");
    assert.deepEqual(localeRequests, []);
    await setLanguage("fr");
    assert.deepEqual([...new Set(localeRequests)], ["fr"]);
    await setLanguage("en");
});

test("a failed catalog or preference keeps the last language visible", async () => {
    await setLanguage("zh-CN");
    unavailableLocale = "fr";
    let saved = false;
    try {
        await assert.rejects(setLanguage("fr", async () => { saved = true; }));
        assert.equal(saved, false);
        assert.equal(currentLanguage(), "zh-CN");
    } finally {
        unavailableLocale = undefined;
    }
    await assert.rejects(setLanguage("fr", async () => { throw Error("Cannot save"); }), /Cannot save/);
    assert.equal(currentLanguage(), "zh-CN");
    assert.equal(String(msg("common.settings")), "设置");
    await setLanguage("en");
});

test("count descriptors use the current locale and preserve their English source", async () => {
    await setLanguage("en");
    const one = pluralMessage("common.model_file_count", 1);
    const many = pluralMessage("common.model_file_count", 1234);
    assert.equal(String(one), "1 model file found.");
    assert.equal(String(many), "1,234 model files found.");
    await setLanguage("de");
    assert.equal(String(many), "1.234 Modelldateien gefunden.");
    assert.equal(sourceText(one), "1 model file found.");
    await setLanguage("en");
});

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

test("switching updates only bound text and keeps form/viewer identities", async () => {
    await setLanguage("en");
    const input=el("input",{value:"Settings <b>我的道具</b>"});
    const viewer=el("div",{"data-model":"saved.glb"});
    const icon=el("span",{class:"icon"});
    const button=el("button",{},icon,msg("common.settings"));
    const root=el("main",{},input,viewer,button);
    await setLanguage("zh-CN");
    assert.equal(button.textContent,"设置");
    assert.equal(root.childNodes[0],input);
    assert.equal(root.childNodes[1],viewer);
    assert.equal(button.childNodes[0],icon);
    assert.equal(input.value,"Settings <b>我的道具</b>");
    await setLanguage("en");
    assert.equal(button.textContent,"Settings");
});

test("progress updates reuse their text node and keep the latest binding", async () => {
    const progress=el("p");
    setText(progress,msg("ccore.downloading",{percent:1}));
    const original=progress.firstChild;
    for(let percent=0;percent<1000;percent++)setText(progress,msg("ccore.downloading",{percent}));
    assert.equal(progress.firstChild,original);
    await setLanguage("zh-CN");
    assert.equal(progress.textContent,"正在下载 999%");
});

test("a raw attribute replacement releases its previous translation binding", async () => {
    const node=el("div");
    bindAttribute(node,"title",msg("common.settings"));
    bindAttribute(node,"title","user-chosen title");
    await setLanguage("en");
    assert.equal(node.getAttribute("title"),"user-chosen title");
});

test("source serialization preserves English machine-facing values", async () => {
    await setLanguage("zh-CN");
    assert.equal(sourceText(msg("common.settings")),"Settings");
    assert.equal(JSON.stringify({name:msg("common.settings")}),JSON.stringify({name:"Settings"}));
});

test("capability captions translate while model prompts and defaults remain exact", async () => {
    const original={label:"Settings",prompt:"Settings",defaults:{prompt:"Do not rewrite 我"},config:{name:"Settings"}};
    const result=capabilityMessages(original);
    assert.equal(String(result.label),"设置");
    assert.equal(result.prompt,"Settings");
    assert.equal(result.defaults,original.defaults);
    assert.equal(result.config,original.config);
});

test("recorded service messages resolve with their original parameters", async () => {
    assert.equal(String(sourceMessage("Downloading 37%")),"正在下载37%");
    assert.equal(sourceMessage("unrecognized diagnostic /data/file.glb"),"unrecognized diagnostic /data/file.glb");
});
