import {el, button} from "./dom.js";
import {msg, setText} from "./i18n.js";

const rotationMs = 30_000;
const recentRunLimit = 24;
const runs = new Map();

const general = [
    "foundry_updates", "foundry_history", "foundry_rocket", "foundry_connect", "foundry_agent",
    "foundry_models", "foundry_unload", "foundry_font", "foundry_gallery", "foundry_package",
    "pinokio_setup", "pinokio_update", "pinokio_listing", "pinokio_first_use", "pinokio_logs",
    "pinokio_repair", "pinokio_restart", "pinokio_install_url", "pinokio_community", "pinokio_reload",
    "pinokio_dev_install", "pinokio_dev_gepeto", "pinokio_dev_live_logs", "pinokio_dev_pterm", "pinokio_dev_bug_reports",
];

const topics = {
    reference: ["reference_three_quarter", "reference_background", "reference_crop", "reference_lighting"],
    images: ["images_material", "images_reverse", "images_seed", "images_variation"],
    orbit: ["orbit_single_turn", "orbit_stationary", "orbit_blur", "orbit_inspect"],
    views: ["views_consistency", "views_details", "views_label", "views_coverage"],
    geometry: ["geometry_silhouette", "geometry_unseen", "geometry_refiner", "geometry_quads"],
    texture: ["texture_resolution", "texture_back", "texture_maps", "texture_light"],
    splat: ["splat_pair", "splat_brush", "splat_budget", "splat_collision"],
    ccore: ["ccore_single_prop", "ccore_examples", "ccore_budget", "ccore_image"],
    character: ["hair_visible", "hair_variation", "garment_drape", "garment_pose"],
    export: ["export_glb", "export_stl", "export_scale", "export_compact"],
};

const workflowTopics = {
    "single-image": ["reference", "geometry", "texture", "export"],
    turnaround: ["reference", "views", "geometry", "texture", "export"],
    guided: ["reference", "views", "geometry", "texture", "export"],
    "virtual-turntable": ["orbit", "views", "geometry", "texture", "export"],
    "orbit-to-mesh": ["orbit", "views", "geometry", "texture", "export"],
    "orbit-with-splats": ["orbit", "views", "splat", "geometry", "texture", "export"],
    "splat-solid": ["splat", "reference", "geometry", "export"],
    ccore: ["ccore", "export"],
    "ccore-image": ["ccore", "reference", "export"],
    images: ["images", "reference"],
    hair: ["character", "reference", "export"],
    garment: ["character", "reference", "export"],
};

const stageTopics = {
    preparing: "setup", concept: "views", turnaround: "views", orbit: "orbit", frames: "orbit",
    cameras: "views", views: "views", render: "views", sheet: "views",
    enhance_sheet: "views", split: "views", prepare: "views",
    proxy: "geometry", geometry: "geometry", reconstruct: "geometry",
    refine: "geometry", refinement: "geometry", cleanup: "geometry", quads: "geometry",
    texture: "texture", splat: "splat", balanced: "export",
    compact: "export", print: "export", package: "export", export: "export",
};

function runState(workflow, runId) {
    const key = JSON.stringify([workflow, runId]);
    const state = runs.get(key) ?? {
        seen: new Set(),
        showGeneral: false,
        key: null,
        due: 0,
        paused: false,
    };
    runs.delete(key);
    runs.set(key, state);
    if (runs.size > recentRunLimit) runs.delete(runs.keys().next().value);
    return state;
}

function tipGroups(workflow, stage) {
    const allowed = workflowTopics[workflow] ?? [];
    const stageTopic = stageTopics[stage];
    const workflowTips = allowed.flatMap(topic => topics[topic]).filter(key => {
        if (key === "splat_brush" || key === "splat_budget") return workflow === "orbit-with-splats";
        if (key === "ccore_image") return workflow === "ccore-image";
        if (key === "export_stl" || key === "export_compact") {
            return !["ccore", "ccore-image", "hair", "garment", "splat-solid"].includes(workflow);
        }
        if (key.startsWith("hair_")) return workflow === "hair";
        if (key.startsWith("garment_")) return workflow === "garment";
        return true;
    });
    const stageTips = stageTopic === "setup"
        ? ["pinokio_first_use", "foundry_models"]
        : workflowTips.filter(key => topics[stageTopic]?.includes(key));
    return {stageTips, workflowTips};
}

function nextTip(state, workflow, stage) {
    const {stageTips, workflowTips} = tipGroups(workflow, stage);
    const unseen = keys => keys.filter(key => !state.seen.has(key));
    if (!unseen(general).length && !unseen(workflowTips).length) {
        state.seen.clear();
        if (state.key) state.seen.add(state.key);
    }

    const pools = state.showGeneral ? [general, stageTips, workflowTips] : [stageTips, workflowTips, general];
    const choices = pools.map(unseen).find(pool => pool.length);
    const key = choices[Math.floor(Math.random() * choices.length)];
    state.seen.add(key);
    state.showGeneral = !general.includes(key);
    return key;
}

class FoundryActivityTip extends HTMLElement {
    connectedCallback() {
        const {state, workflow, stage} = this;
        if (!state.key) {
            state.key = nextTip(state, workflow, stage);
            state.due = Date.now() + rotationMs;
        }
        const message = el("span");
        const toggle = button("", () => {
            state.paused = !state.paused;
            if (!state.paused) state.due = Date.now() + rotationMs;
            this.renderTip();
        }, {class: "quiet"});
        this.replaceChildren(el("p", {}, el("strong", {}, msg("tips.heading")), message), toggle);
        this.renderTip = () => {
            clearTimeout(this.rotation);
            setText(message, msg("tips." + state.key));
            setText(toggle, msg(state.paused ? "tips.resume" : "tips.pause"));
            if (!state.paused) {
                this.rotation = setTimeout(() => {
                    if (!this.isConnected) return;
                    state.key = nextTip(state, workflow, stage);
                    state.due = Date.now() + rotationMs;
                    this.renderTip();
                }, Math.max(0, state.due - Date.now()));
            }
        };
        this.renderTip();
    }

    disconnectedCallback() {
        clearTimeout(this.rotation);
    }
}

if (!customElements.get("foundry-activity-tip")) customElements.define("foundry-activity-tip", FoundryActivityTip);

export function activityTip(workflow, runId, stage) {
    if (!runId) return null;
    const element = el("foundry-activity-tip", {class: "foundry-activity-tip", "aria-live": "off"});
    element.workflow = workflow;
    element.stage = stage;
    element.state = runState(workflow, runId);
    return element;
}
