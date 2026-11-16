import assert from "node:assert/strict";
import test from "node:test";
import {loadSampleReference} from "../web/foundry/single/sample.js";

const webp = Buffer.from("UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEAAUAmJaQAA3AA/vuUAAA=", "base64").subarray(0, 42);

test("the bundled sample becomes a WebP file accepted by the reference upload", async t => {
    t.mock.method(globalThis, "fetch", async () =>
        new Response(webp, {headers: {"Content-Type": "image/webp"}}));
    const file = await loadSampleReference();
    assert.ok(file instanceof File);
    assert.equal(file.type, "image/webp");
    assert.equal(file.name, "ray-gun-reference.webp");
    assert.deepEqual(Buffer.from(await file.arrayBuffer()), webp);
});

test("missing, corrupt and oversized sample responses leave no file to upload", async t => {
    const cases = [
        new Response("", {status: 404}),
        new Response("This is not an image", {headers: {"Content-Type": "image/webp"}}),
        new Response(webp, {headers: {"Content-Type": "image/png"}}),
        new Response(webp, {headers: {"Content-Type": "image/webp", "Content-Length": String(21 * 1024 ** 2)}}),
    ];
    t.mock.method(globalThis, "fetch", async () => cases.shift());
    for (let index = 0; index < 4; index++) await assert.rejects(loadSampleReference(), /sample image/i);
});

test("a network error is reported in terms of the sample", async t => {
    t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
    await assert.rejects(loadSampleReference(), /sample image/i);
});

test("if the sample request is cancelled, a response arriving later cannot return a file", async t => {
    let respond;
    t.mock.method(globalThis, "fetch", () => new Promise(resolve => { respond = resolve; }));
    const controller = new AbortController();
    const result = loadSampleReference({signal: controller.signal});
    controller.abort();
    respond(new Response(webp, {headers: {"Content-Type": "image/webp"}}));
    await assert.rejects(result, {name: "AbortError"});
});
