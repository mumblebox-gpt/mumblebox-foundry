import {button, bytes, el, hint} from "../dom.js";
import {msg, replaceContent} from "../i18n.js";
import {request} from "../services.js";

const statusLabels = {
    present: "mesh.preparation_present",
    missing: "mesh.preparation_missing",
    access_required: "mesh.preparation_access_required",
    unknown: "mesh.preparation_check",
};

export class PreparationPreview {
    constructor(stageLabel) {
        this.stageLabel = stageLabel;
        this.content = el("div", {"aria-live": "polite"});
        this.host = el("details", {class: "preparation-preview note-panel", ontoggle: () => {
            if (this.host.open) this.load();
            else this.cancel();
        }}, el("summary", {}, msg("mesh.preparation_files")), this.content);
    }

    update(draft, method, operation) {
        if (!operation) {
            if (this.payload) {
                this.cancel();
                this.payload = null;
                this.key = null;
                this.completed = false;
                this.host.open = false;
                replaceContent(this.content);
            }
            return null;
        }
        // Seed, file formats, and reference contents cannot change this list.
        const variants = Object.keys(draft.selection?.variants ?? {}).sort();
        const {geometry_model, texture_mode} = draft.overrides;
        const configuration = {
            method, profile: draft.profile, turnaround_model: draft.turnaround_model,
            overrides: {geometry_model, texture_mode},
            selection: draft.selection,
        };
        const key = JSON.stringify([operation, method, configuration.profile, configuration.turnaround_model,
                                    geometry_model, texture_mode, variants]);
        if (key !== this.key) {
            this.cancel();
            this.key = key;
            this.completed = false;
            replaceContent(this.content, hint(msg("mesh.preparation_explanation")));
        }
        this.payload = {configuration, operation};
        if (this.host.open) this.load();
        return this.host;
    }

    cancel() {
        this.pending?.abort();
        this.pending = null;
    }

    async load() {
        if (!this.payload || this.completed || this.pending) return;
        const pending = new AbortController();
        this.pending = pending;
        replaceContent(this.content, hint(msg("common.checking")));
        try {
            const data = await request("wizard/preparation-preview", this.payload, {signal: pending.signal});
            if (pending.signal.aborted) return;
            this.completed = true;
            const unknown = Math.max(data.unknown_download_count, data.unknown_storage_count);
            replaceContent(this.content,
                hint(msg("mesh.preparation_sizes", {download: bytes(data.known_download_bytes),
                                                     storage: bytes(data.known_storage_bytes)})),
                unknown ? hint(msg("mesh.preparation_unknown", {count: unknown})) : null,
                data.stages.length ? el("ul", {}, data.stages.map(stage => el("li", {}, this.stageLabel(stage)))) : null,
                data.resources.length ? el("ul", {}, data.resources.map(resource => el("li", {}, resource.label,
                    " — ", msg(statusLabels[resource.status] ?? statusLabels.unknown)))) : null,
                hint(msg("mesh.preparation_explanation")));
        } catch {
            if (!pending.signal.aborted) {
                this.completed = true;
                replaceContent(this.content, hint(msg("mesh.preparation_unavailable")),
                    button(msg("mesh.retry"), () => {
                        this.completed = false;
                        void this.load();
                    }));
            }
        } finally {
            if (this.pending === pending) this.pending = null;
        }
    }
}
