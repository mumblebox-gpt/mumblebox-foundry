import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {test} from "node:test";

class Element {
    constructor() {
        this.childNodes = [];
        this.attributes = new Map();
        this.handlers = {};
        this.isConnected = true;
    }
    append(...nodes) { this.childNodes.push(...nodes); }
    replaceChildren(...nodes) { this.childNodes = nodes; }
    get firstChild() { return this.childNodes[0]; }
    setAttribute(key, value) { this.attributes.set(key, value); }
    addEventListener(key, handler) { this.handlers[key] = handler; }
    get textContent() {
        return this.nodeType === 3 ? this.data : this.childNodes.map(node => node.textContent).join("");
    }
}
const definitions = new Map();
globalThis.HTMLElement = globalThis.Node = Element;
globalThis.customElements = {
    get: key => definitions.get(key),
    define: (key, type) => definitions.set(key, type),
};
globalThis.document = {
    createElement: key => new (definitions.get(key) ?? Element)(),
    createTextNode: data => Object.assign(new Element(), {nodeType: 3, data}),
};

const {activityTip} = await import("../web/foundry/activity-tips.js");
const {languages, setLanguage} = await import("../web/foundry/i18n.js");
const catalog = JSON.parse(await readFile(new URL("../web/foundry/tips/locales/en.json", import.meta.url), "utf8"));
const text = node => node.childNodes[0].childNodes[1].textContent;
const toggle = node => node.childNodes[1].handlers.click();

test("tips prioritize the stage, alternate with app advice, and survive rerender without repeating", t => {
    t.mock.timers.enable({apis: ["Date", "setTimeout"], now: 100_000});
    const first = activityTip("orbit-with-splats", "sample", "splat");
    first.connectedCallback();
    const opening = text(first);
    assert.ok(Object.entries(catalog).some(([key, value]) => key.startsWith("splat_") && value === opening));
    t.mock.timers.tick(15_000);
    first.disconnectedCallback();

    const next = activityTip("orbit-with-splats", "sample", "texture");
    next.connectedCallback();
    assert.equal(text(next), opening);
    t.mock.timers.tick(15_000);
    assert.ok(Object.entries(catalog).some(([key, value]) =>
        /^(foundry|pinokio)_/.test(key) && value === text(next)));

    const seen = new Set([opening, text(next)]);
    for (let count = 0; count < 42; count++) {
        t.mock.timers.tick(30_000);
        assert.ok(!seen.has(text(next)), text(next));
        seen.add(text(next));
    }
    const previous = text(next);
    t.mock.timers.tick(30_000);
    assert.notEqual(text(next), previous);
    next.disconnectedCallback();
});

test("pause holds the tip, resume restarts the delay, and closing the panel stops its timer", t => {
    t.mock.timers.enable({apis: ["Date", "setTimeout"], now: 100_000});
    const panel = activityTip("images", "another", "image");
    panel.connectedCallback();
    const opening = text(panel);
    toggle(panel);
    t.mock.timers.tick(60_000);
    assert.equal(text(panel), opening);
    assert.equal(panel.childNodes[1].textContent, "Resume tips");
    toggle(panel);
    t.mock.timers.tick(29_999);
    assert.equal(text(panel), opening);
    t.mock.timers.tick(1);
    const rotated = text(panel);
    assert.notEqual(rotated, opening);

    panel.disconnectedCallback();
    t.mock.timers.tick(60_000);
    assert.equal(text(panel), rotated);
});

test("every supported language has a complete catalog and updates a paused tip in place", async t => {
    t.mock.method(globalThis, "fetch", async url => new Response(await readFile(new URL(url))));
    const panel = activityTip("single-image", "language-check", "geometry");
    panel.connectedCallback();
    toggle(panel);
    const key = Object.keys(catalog).find(key => catalog[key] === text(panel));
    assert.ok(key);
    try {
        for (const {id} of languages) {
            const translated = JSON.parse(await readFile(
                new URL("../web/foundry/tips/locales/" + id + ".json", import.meta.url), "utf8"));
            assert.deepEqual(Object.keys(translated).sort(), Object.keys(catalog).sort(), id);
            assert.equal(Object.keys(translated).length, 65 + 3, id);
            assert.equal(new Set(Object.values(translated)).size, 65 + 3, id);
            assert.ok(Object.values(translated).every(value => typeof value === "string" && value.trim()), id);
            await setLanguage(id);
            assert.equal(text(panel), translated[key], id);
            assert.equal(panel.childNodes[1].textContent, translated.resume, id);
        }
    } finally {
        panel.disconnectedCallback();
        await setLanguage("en");
    }
});

test("tip state survives recent rerenders and forgets the least recent run when capacity is reached", t => {
    t.mock.timers.enable({apis: ["Date", "setTimeout"], now: 100_000});
    function mount(id) {
        const panel = activityTip("single-image", id, "geometry");
        panel.connectedCallback();
        panel.disconnectedCallback();
        return panel;
    }

    const panel = mount("old-run");
    toggle(panel);
    for (let index = 0; index < 23; index++) mount("other-" + index);
    assert.equal(mount("old-run").childNodes[1].textContent, "Resume tips");
    for (let index = 0; index < 24; index++) mount("new-" + index);
    assert.equal(mount("old-run").childNodes[1].textContent, "Pause tips");
});
