import assert from "node:assert/strict";
import test from "node:test";
import {buildProblemDetails} from "../web/foundry/problem-details.js";

test("a report identifies the version, workflow, step, and known failure", () => {
    const report = buildProblemDetails({
        version: "0.1.0-preview.32",
        workflow: "single-image",
        step: 2,
        code: "ReferenceError",
        message: "setText is not defined",
    });
    assert.match(report, /Foundry version: 0\.1\.0-preview\.32/);
    assert.match(report, /Workflow: single-image/);
    assert.match(report, /Step: 2/);
    assert.match(report, /Error code: ReferenceError/);
    assert.match(report, /Error: setText is not defined/);
});

test("report omits private variables from a translated message", () => {
    const report = buildProblemDetails({
        version: "0.1.0-preview.32",
        workflow: "turnaround",
        step: 1,
        message: 'Required node missing: C:\\Private\\secret-user\\scene.png',
    });
    assert.doesNotMatch(report, /Private|secret-user|scene\.png/);
    assert.match(report, /mesh\.required_node_missing/);
});

test("arbitrary worker text, pasted secrets and long Unicode are kept out of the report", () => {
    const privateText = 'hf_privateToken glb: C:/Private/scene.glb\nPrompt: 機密の画像';
    const report = buildProblemDetails({
        version: "0.1.0-preview.32\n" + privateText,
        workflow: privateText,
        step: privateText,
        code: privateText,
        message: privateText + "🪶".repeat(16_384),
    });
    assert.doesNotMatch(report, /hf_privateToken|scene\.glb|機密|🪶/);
    assert.ok(Buffer.byteLength(report, "utf8") <= 32_768);
    assert.match(report, /Error:/);
});

test("empty context still supplies a readable report", () => {
    assert.match(buildProblemDetails(), /Foundry version: Unknown/);
});
