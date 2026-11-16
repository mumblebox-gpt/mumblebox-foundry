import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {registerHooks} from "node:module";
import test from "node:test";

// Comfy supplies these two modules in the browser. The wizard, page renderers,
// translation catalogs and saved-draft handling are the production modules.
const hostModules = new Map([
    ["/scripts/api.js", "export const api = new EventTarget();"],
    ["/scripts/app.js", "export const app = {extensionManager:{workflow:{activeWorkflow:{path:'Single test'}}}};"],
]);
const hostHooks = registerHooks({
    resolve(specifier, context, next) {
        const source = hostModules.get(specifier);
        if (source) return {url: "data:text/javascript," + encodeURIComponent(source), shortCircuit: true};
        return next(specifier, context);
    },
});

class Element extends EventTarget {
    constructor(tagName) {
        super();
        this.tagName = tagName;
        this.childNodes = [];
        this.attributes = new Map();
        this.dataset = {};
        this.value = "";
        this.checked = false;
        this.hidden = false;
        this.open = false;
        this.isConnected = true;
    }
    append(...nodes) { this.childNodes.push(...nodes); }
    replaceChildren(...nodes) { this.childNodes = nodes; }
    insertBefore(node, before) {
        const index = this.childNodes.indexOf(before);
        assert.notEqual(index, -1);
        this.childNodes.splice(index, 0, node);
    }
    setAttribute(key, value) { this.attributes.set(key, String(value)); }
    getAttribute(key) { return this.attributes.get(key) ?? null; }
    get firstChild() { return this.childNodes[0]; }
    get lastChild() { return this.childNodes.at(-1); }
    get textContent() { return this.childNodes.map(node => node.textContent).join(""); }
    getRootNode() { return document; }
    scrollIntoView() {}
    *descendants() {
        for (const node of this.childNodes) {
            if (!(node instanceof Element)) continue;
            yield node;
            yield* node.descendants();
        }
    }
    querySelector(selector) {
        return [...this.descendants()].find(node => selector.startsWith(".")
            ? node.className?.split(" ").includes(selector.slice(1))
            : node.tagName === selector);
    }
    click() { this.dispatchEvent(new Event("click")); }
}

class TextNode {
    nodeType = 3;
    constructor(value) { this.data = value; }
    get textContent() { return this.data; }
}

globalThis.HTMLElement = globalThis.Node = Element;
const customElements = new Map();
globalThis.customElements = {
    get: name => customElements.get(name),
    define: (name, constructor) => customElements.set(name, constructor),
};
globalThis.document = {
    createElement: tag => new (customElements.get(tag) ?? Element)(tag),
    createTextNode: value => new TextNode(value),
};
const storage = new Map();
Object.defineProperty(globalThis, "localStorage", {
    value: {
        setItem: (key, value) => storage.set(key, value),
        getItem: key => storage.get(key) ?? null,
    },
    configurable: true,
});
const {Wizard} = await import("../web/foundry/wizard/controller.js");
const {setLanguage} = await import("../web/foundry/i18n.js");
hostHooks.deregister();

const reference = {id: "saved-ref", filename: "foundry-references/saved.png", role: "primary"};
const selection = {variants: {detailed: {formats: ["glb"]}}};

function openSingle(t, {page = 1, references = [reference], overrides = {}, runId = null} = {}) {
    storage.clear();
    const saved = {page, runId, sessionId: "previous-session",
        draft: {name: "Saved prop", references, overrides, selection}};
    const node = {properties: {foundrySingle: serializedCopy(saved)}};
    const wizard = new Wizard({node, content: {}, data: {version: "0.1.0-preview.32"}, message() {}},
        {method: "single-image", resume: true});
    wizard.cap = {
        defaults: {shape_resolution: 1024, refine_resolution: 1536, refine_steps: 25, refine_seed: 42, cpu_offload: true},
        exports: [{id: "detailed", formats: ["glb"], description: "Detailed asset"}],
    };
    t.after(() => wizard.dispose());
    wizard.render();
    return wizard;
}

function serializedCopy(value) { return JSON.parse(JSON.stringify(value)); }

function control(wizard, predicate) {
    const element = [...wizard.host.descendants()].find(predicate);
    assert.ok(element, "Expected control to be rendered");
    return element;
}

function click(wizard, label) {
    control(wizard, node => node.tagName === "button" && node.textContent === label).click();
    return new Promise(resolve => setImmediate(resolve));
}

test("a saved Single options page renders its own description and translates it in place", async t => {
    t.mock.method(globalThis, "fetch", async url => new Response(await readFile(new URL(url))));
    const wizard = openSingle(t, {page: 2});
    assert.equal(wizard.host.querySelector("h2").textContent, "Mesh and refinement");
    assert.match(wizard.host.textContent, /Pixal3D builds from your one reference/);
    try {
        await setLanguage("fr");
        assert.match(wizard.host.textContent, /Pixal3D génère à partir de votre seule référence/);
    } finally {
        await setLanguage("en");
    }
});

test("Single Next requires a reference before it opens the mesh settings", async t => {
    const wizard = openSingle(t, {references: []});
    await click(wizard, "Next");
    assert.equal(wizard.page, 1);
    assert.match(wizard.host.textContent, /Choose or create an image first/);
});

test("Single Back and Next preserve the uploaded reference and geometry seed", async t => {
    const wizard = openSingle(t);
    await click(wizard, "Next");
    const seed = () => control(wizard, node => node.getAttribute("aria-label") === "Geometry seed");
    assert.equal(String(seed().value), "42");
    const maximum = "9007199254740976";
    assert.equal(seed().getAttribute("max"), maximum);
    seed().value = maximum;
    seed().dispatchEvent(new Event("change"));
    await click(wizard, "Back");
    assert.match(wizard.host.querySelector("img").getAttribute("src"), /filename=saved\.png/);
    await click(wizard, "Next");
    assert.equal(String(seed().value), maximum);
    assert.deepEqual(wizard.node.properties.foundrySingle.draft.references, [reference]);
    assert.equal(wizard.node.properties.foundrySingle.draft.overrides.shape_seed, Number(maximum));
});

test("Single result after a failed finish returns to export choices with the saved draft", async t => {
    const wizard = openSingle(t, {page: 4, runId: "saved-run", overrides: {shape_seed: 17}});
    wizard.run = {status: "failed", operation: "finish", active: false, previews: {}};
    wizard.error = "The finishing worker stopped.";
    wizard.render();
    assert.equal(wizard.host.querySelector("h2").textContent, "Your asset package");
    assert.match(wizard.host.textContent, /The finishing worker stopped/);
    await click(wizard, "Back");
    assert.equal(wizard.host.querySelector("h2").textContent, "Refined mesh and exports");
    assert.deepEqual(wizard.draft.references, [reference]);
    assert.deepEqual(wizard.draft.selection, selection);
    assert.equal(wizard.draft.overrides.shape_seed, 17);
    assert.equal(wizard.runId, "saved-run");
});

test("Copy details includes Single context and keeps the raw worker message out of the clipboard", async t => {
    let copied;
    Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {writeText: async text => { copied = text; }},
    });
    t.after(() => { delete navigator.clipboard; });
    const wizard = openSingle(t, {page: 2});
    wizard.error = "Failed to open C:/private/reference.png";
    wizard.render();
    await click(wizard, "Copy details");
    assert.match(copied, /0\.1\.0-preview\.32/);
    assert.match(copied, /Workflow: single-image/);
    assert.match(copied, /Step: 2/);
    assert.doesNotMatch(copied, /C:\/private|reference\.png/);
    assert.match(wizard.host.textContent, /Copied/);
});

test("when clipboard access fails, the wizard reveals selectable shareable details", async t => {
    Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {writeText: async () => { throw new Error("Not allowed"); }},
    });
    t.after(() => { delete navigator.clipboard; });
    const wizard = openSingle(t, {page: 2});
    wizard.error = "setText is not defined";
    wizard.render();
    await click(wizard, "Copy details");
    const details = control(wizard, node => node.tagName === "pre" && node.textContent.includes("Step: 2"));
    assert.equal(details.hidden, false);
    assert.match(details.textContent, /Error: setText is not defined/);
});

test("a page render error leaves Copy details and Back available without losing the saved reference", async t => {
    const wizard = openSingle(t, {page: 2});
    // Model a malformed capability response at the render boundary.
    wizard.cap.defaults = null;
    wizard.render();
    assert.ok(control(wizard, node => node.getAttribute("role") === "alert"));
    assert.ok(control(wizard, node => node.tagName === "button" && node.textContent === "Copy details"));
    await click(wizard, "Back");
    assert.equal(wizard.page, 1);
    assert.deepEqual(wizard.draft.references, [reference]);
});

test("the sample uploads once, with no generation request", async t => {
    const webp = Buffer.from("UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEAAUAmJaQAA3AA/vuUAAA=", "base64").subarray(0, 42);
    const calls = [];
    let supplySample;
    t.mock.method(globalThis, "fetch", async (resource, options) => {
        calls.push(String(resource));
        if (String(resource).endsWith(".webp")) return new Promise(resolve => { supplySample = resolve; });
        assert.equal(resource, "/upload/image");
        assert.equal(options.body.get("image").name, "ray-gun-reference.webp");
        return Response.json({name: "ray-gun-reference.webp", subfolder: "foundry-references"});
    });
    const wizard = openSingle(t, {references: []});
    const sample = control(wizard, node => node.tagName === "button" && node.textContent === "Use sample image");
    sample.click();
    sample.click();
    supplySample(new Response(webp, {headers: {"Content-Type": "image/webp"}}));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls.length, 2);
    assert.match(wizard.draft.references[0].filename, /ray-gun-reference\.webp$/);
    assert.equal(wizard.page, 1);
    assert.equal(wizard.runId, null);
});

test("a late sample cannot overwrite a manually uploaded reference", async t => {
    let supplySample;
    const uploads = [];
    t.mock.method(globalThis, "fetch", async (resource, options) => {
        if (String(resource).endsWith(".webp")) return new Promise(resolve => { supplySample = resolve; });
        assert.equal(resource, "/upload/image");
        const name = options.body.get("image").name;
        uploads.push(name);
        return Response.json({name, subfolder: "foundry-references"});
    });
    const wizard = openSingle(t, {references: []});
    const sample = control(wizard, node => node.tagName === "button" && node.textContent === "Use sample image");
    sample.click();
    const file = control(wizard, node => node.getAttribute("aria-label") === "Upload single reference");
    file.files = [new File(["test PNG"], "own.png", {type: "image/png"})];
    file.dispatchEvent(new Event("change"));
    supplySample(new Response("late sample", {headers: {"Content-Type": "image/webp"}}));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(uploads, ["own.png"]);
    assert.match(wizard.draft.references[0].filename, /own\.png$/);
});

test("opening first-use details requests only the selected setup and shows unknown costs", async t => {
    const requests = [];
    t.mock.method(globalThis, "fetch", async (url, options) => {
        assert.match(url, /wizard\/preparation-preview$/);
        requests.push(JSON.parse(options.body));
        return Response.json({
            stages: [{id: "single_geometry", label: "Initial mesh"}],
            resources: [{id: "hi3d", label: "Hi3D", status: "unknown"}],
            known_download_bytes: 2 ** 30, known_storage_bytes: 2 ** 30,
            unknown_download_count: 1, unknown_storage_count: 1,
        });
    });
    const wizard = openSingle(t, {page: 2});
    const panel = wizard.host.querySelector(".preparation-preview");
    assert.ok(panel);
    assert.equal(requests.length, 0);
    panel.open = true;
    panel.dispatchEvent(new Event("toggle"));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(requests.length, 1);
    assert.equal(requests[0].operation, "mesh");
    assert.equal(requests[0].configuration.method, "single-image");
    assert.equal(requests[0].configuration.references, undefined);
    assert.match(panel.textContent, /1\.0 GB/);
    assert.match(panel.textContent, /Unknown requirements: 1/);
    wizard.render();
    assert.equal(requests.length, 1);
});
