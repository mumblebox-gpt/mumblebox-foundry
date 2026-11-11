import {t} from "../i18n.js";
import {sourceMessage} from "../i18n.js";
import {msg, setText, replaceContent} from "../i18n.js";
import {api} from '/scripts/api.js';
import {el, button, field, hint, link} from '../dom.js';
import {elapsedTime, workingStar} from '../activity.js';
import {inputURL, uploadReference} from '../images/references.js';
import {pollResources, request} from '../services.js';
import {mountMesh} from '../wizard/preview.js';
import {ccoreDraftKey, ccoreTitle, syncPropGraph} from './graph.js';

const titles = [msg("ccore.describe_your_prop"), msg("ccore.review_your_prop"), msg("ccore.download_your_asset")];
const credits = 'https://huggingface.co/ccore/Qwen3.5-4B-GLB-3D-Coder';
const defaults = {name: 'New prop', prompt: '', seed: 42, max_tokens: 65536};
const budgetUses = {16384: msg("ccore.simple_props"), 32768: msg("ccore.more_detail"), 65536: msg("ccore.most_room_default")};
const precisionOptions = {
    q4_k_m: [msg("ccore.standard"), 'Q4_K_M', msg("ccore.uses_less_gpu_memory_and_leaves_more_room_for_longer_generations")],
    q8_0: [msg("ccore.higher_precision"), 'Q8_0', msg("ccore.keeps_more_of_the_model_s_original_precision_and_uses_more_gpu_memory")],
};
// CCORE enhancement uses the default Q8 weights from description_helper.py.
const enhancementModel = 'Qwen3.5-9B-Heretic';
const runUrl = id => 'ccore/runs/' + id;
const fileUrl = (id, kind, download = false) =>
    '/mumblebox-foundry/v1/' + runUrl(id) + '/file?' + new URLSearchParams({kind, ...(download ? {download: '1'} : {})});

export class CcoreWizard {
    constructor(shell, {resume = false, image = false, handoff = null, runId = null} = {}) {
        this.shell = shell;
        this.withImage = image;
        this.saved = shell.node.properties[ccoreDraftKey(image)] || {};
        this.draft = {...defaults, ...this.saved.draft};
        if (image && handoff?.references[0]) this.draft.image = handoff.references[0].filename;
        this.id = runId || (resume ? this.saved.id : null);
        if (runId) this.saved = {...this.saved, id: runId};
        this.runStartedAt = this.saved.startedAt;
        this.page = 0;
        this.element = el('div', {class: 'wizard', 'data-ccore-wizard': ''});
    }

    async init() {
        this.capabilities = await request('ccore/capabilities');
        this.draft.model_variant ??= this.capabilities.default_model_variant;
        this.draft.translation_precision ??= this.capabilities.translation.default_precision;
        if (this.id) {
            this.run = await request(runUrl(this.id));
            this.draft = {...this.run.config, translation_precision: this.draft.translation_precision ?? this.capabilities.translation.default_precision};
            this.page = 1;
        }
        this.remember();
        this.render();
        if (this.run?.active) this.poll();
        return this.element;
    }

    remember() {
        this.shell.node.properties[ccoreDraftKey(this.withImage)] = {...this.saved, draft: {...this.draft}};
    }

    update(key, value) {
        this.draft[key] = value;
        this.remember();
    }

    chooseExample(id) {
        const example = this.capabilities.examples.find(item => item.id === id);
        if (!example && id !== 'custom') return;
        this.example = id;
        this.originalDescription = undefined;
        this.enhanceMessage = '';
        this.error = '';
        this.draft.name = example ? String(msg("ccore.preset_" + id + "_name")) : defaults.name;
        this.draft.prompt = example ? t("ccore.preset_" + id + "_prompt") : "";
        this.remember();
        this.render();
        this.element.querySelector('textarea')?.focus();
    }

    async transformDescription(kind = "enhance") {
        if (this.enhancing || !this.draft.prompt.trim()) return;
        const original = this.draft.prompt;
        const operation = {kind, id: crypto.randomUUID().replaceAll('-', ''), cancelled: false, startedAt: Date.now()};
        this.enhancing = operation;
        this.error = '';
        this.enhanceMessage = msg(kind === "translate" ? "ccore.translating" : "ccore.preparing_assistant");
        this.render();
        const stopPolling = pollResources(status => {
            const helper = status.description_helper;
            if (operation.cancelled || helper?.asset !== operation.id || !helper.running) return;
            const download = status.download;
            const progress = helper.downloading && download?.total
                ? ' · ' + Math.min(100, Math.floor(100 * download.bytes / download.total)) + '%' : '';
            this.showEnhanceMessage(msg("ccore.task_progress", {phase:sourceMessage(helper.phase || "Enhancing your description…"),progress}));
        }, () => {});
        try {
            const result = await request('ccore/' + kind, {request_id: operation.id, prompt: original, ...(kind === "translate" ? {precision:this.draft.translation_precision} : {})});
            if (this.disposed) return;
            if (operation.cancelled || result.cancelled) {
                this.enhanceMessage = msg(kind === "translate" ? "ccore.translation_stopped" : "ccore.enhancement_stopped");
            } else if (this.draft.prompt === original) {
                this.originalDescription = original;
                this.example = '';
                this.update('prompt', result.text);
                this.enhanceMessage = msg(kind === "translate" ? "ccore.translation_ready" : "ccore.description_enhanced");
            }
        } catch (error) {
            if (!this.disposed) {
                this.enhanceMessage = operation.cancelled ? msg(kind === "translate" ? "ccore.translation_stopped" : "ccore.enhancement_stopped") : "";
                if (!operation.cancelled) this.error = error.message;
            }
        } finally {
            stopPolling();
            this.enhancing = null;
            this.render();
            if (!this.disposed) this.element.querySelector('textarea')?.focus();
        }
    }

    showEnhanceMessage(message) {
        this.enhanceMessage = message;
        if (this.enhanceStatus) setText(this.enhanceStatus, message);
    }

    async stopEnhancement() {
        const operation = this.enhancing;
        if (!operation || operation.cancelled) return;
        operation.cancelled = true;
        if (!this.disposed) {
            this.showEnhanceMessage(msg("ccore.stopping_assistant"));
            this.stopEnhanceButton.disabled = true;
        }
        try {
            await request('ccore/enhance/' + operation.id + '/cancel', {});
        } catch (error) {
            if (!this.disposed && this.enhancing === operation) {
                this.error = error.message;
                this.render();
            }
        }
    }

    restoreDescription() {
        this.update('prompt', this.originalDescription);
        this.originalDescription = undefined;
        this.error = '';
        this.enhanceMessage = msg("ccore.original_restored");
        this.render();
        this.element.querySelector('textarea')?.focus();
    }

    canGenerate() {
        return Boolean(this.draft.prompt.trim() && (!this.withImage || this.draft.image));
    }

    async upload(file) {
        if (!file || this.uploading || this.starting) return;
        this.uploading = true;
        this.error = '';
        this.render();
        try {
            this.update('image', (await uploadReference(file)).filename);
        } catch (error) {
            this.error = error.message;
        } finally {
            this.uploading = false;
            this.render();
        }
    }

    reference() {
        const image = this.draft.image;
        const disabled = this.uploading || this.starting;
        const input = el('input', {type: 'file', accept: 'image/png,image/jpeg,image/webp', hidden: true,
            onchange: e => this.upload(e.target.files[0])});
        return el('div', {class: 'reference-drop',
            ondragover: e => {e.preventDefault(); e.stopPropagation();},
            ondrop: e => {e.preventDefault(); e.stopPropagation(); this.upload(e.dataTransfer.files[0]);}},
            input, image ? el('img', {src: inputURL(image), alt: msg("ccore.reference_for_this_ccore_prop"),
                style: 'display:block;max-width:100%;max-height:160px;object-fit:contain'}) : null,
            hint(this.uploading ? msg("ccore.uploading_reference") : msg("ccore.drop_one_image_here_or_choose_a_file")),
            el('div', {class: 'actions'}, button(image ? msg("ccore.replace_image") : msg("ccore.upload_image"), () => input.click(), {disabled}),
                button(msg("ccore.create_an_image"), () => {
                    this.remember();
                    this.shell.imageOrigin = {method: 'ccore-image'};
                    this.shell.openImages('Create Images');
                }, {disabled: disabled || Boolean(this.enhancing)}),
                image ? button(msg("ccore.remove_image"), () => {this.update('image', ''); this.render();}, {disabled}) : null));
    }

    async start() {
        if (this.starting || this.enhancing || this.uploading || this.run?.active || !this.canGenerate()) return;
        this.starting = true;
        const startedAt = Date.now();
        this.error = '';
        this.render();
        try {
            const id = crypto.randomUUID().replaceAll('-', '');
            const config = this.withImage ? {...this.draft, mode: 'image_text'} : this.draft;
            syncPropGraph(this.shell.node, config, this.withImage);
            const result = await request('ccore/runs', {...config, request_id: id, client_id: api.clientId || ''});
            this.saved = {...this.saved, id, startedAt};
            this.runStartedAt = startedAt;
            this.id = id;
            this.run = result;
            this.remember();
            this.page = 1;
            this.poll();
        } catch (error) {
            this.error = error.message;
        } finally {
            this.starting = false;
            this.render();
        }
    }

    poll(delay = 1100) {
        clearTimeout(this.timer);
        if (this.disposed) return;
        this.timer = setTimeout(async () => {
            try {
                const result = await request(runUrl(this.id));
                if (this.disposed) return;
                this.run = result;
                if (!result.active) this.cancelling = false;
                if (result.active) {
                    this.progress();
                    this.poll();
                } else {
                    this.render();
                }
            } catch (error) {
                if (this.disposed) return;
                if (this.phase) setText(this.phase, sourceMessage(error.message));
                this.poll(3500);
            }
        }, delay);
    }

    async cancel() {
        if (this.cancelling) return;
        this.cancelling = true;
        this.render();
        try {
            this.run = await request(runUrl(this.id) + '/cancel', {});
            if (!this.run.active) this.cancelling = false;
        } catch (error) {
            this.error = error.message;
            this.cancelling = false;
        }
        this.render();
    }

    progress() {
        if (!this.phase) return;
        const transfer = this.run?.download;
        setText(this.phase, this.cancelling ? msg("ccore.stopping_generation") : sourceMessage(this.run.phase));
        const percent = transfer?.total ? Math.min(100, Math.floor(transfer.bytes / transfer.total * 100)) : null;
        setText(this.transfer, percent === null ? msg("ccore.long_descriptions_can_take_several_minutes") :
            (transfer.phase === 'verifying SHA-256' ? msg("ccore.checking_the_downloaded_model") : msg("ccore.downloading", {percent: percent})));
        if (percent === null || transfer?.phase === 'verifying SHA-256') this.meter.removeAttribute('value');
        else this.meter.value = percent;
        this.stop.disabled = this.cancelling || this.run.phase === 'Saving prop and package';
    }

    go(page) {
        this.page = page;
        this.error = '';
        this.render();
        this.element.querySelector('h2')?.focus({preventScroll: true});
        this.shell.content.scrollTop = 0;
    }

    describe() {
        const name = el('input', {type: 'text', maxLength: 80, value: this.draft.name,
            oninput: e => this.update('name', e.target.value)});
        const working = Boolean(this.enhancing);
        const examples = el('select', {disabled: working, onchange: e => this.chooseExample(e.target.value)},
            el('option', {value: '', disabled: true}, msg("ccore.choose_an_example")),
            el('option', {value: 'custom'}, msg("ccore.custom")),
            this.capabilities.examples.map(({id, name, category}) =>
                el('option', {value: id}, msg("ccore.example_option", {category:msg("ccore.preset_"+id+"_category"), name:msg("ccore.preset_"+id+"_name")}))));
        examples.value = this.example || '';
        const enhance = button(msg("ccore.enhance_description"), () => this.transformDescription(), {
            disabled: working || !this.draft.prompt.trim(),
        });
        const translate = button(msg("ccore.translate_to_english"), () => this.transformDescription("translate"), {
            disabled: working || !this.draft.prompt.trim() || this.starting,
        });
        const prompt = el('textarea', {rows: 8, maxLength: 5000, value: this.draft.prompt, readOnly: working,
            placeholder: msg("ccore.a_small_brass_lantern_with_a_green_glass_shade_and_a_curved_handle"),
            oninput: e => {
                this.example = '';
                examples.value = '';
                this.update('prompt', e.target.value);
                enhance.disabled = !e.target.value.trim();
                translate.disabled = !e.target.value.trim() || this.starting;
                this.generateButton.disabled = !this.canGenerate() || this.starting;
            }});
        this.enhanceStatus = el('p', {role: 'status', class: 'muted'}, this.enhanceMessage || '');
        this.stopEnhanceButton = working ? button(msg("ccore.stop_description_task"), () => this.stopEnhancement(), {
            disabled: this.enhancing.cancelled,
        }) : null;
        const seed = el('input', {type: 'number', min: 0, max: 2147483647, step: 1, value: this.draft.seed,
            oninput: e => this.update('seed', e.target.valueAsNumber)});
        const budget = el('select', {onchange: e => this.update('max_tokens', Number(e.target.value))},
            this.capabilities.token_limits.map(value => el('option', {
                value, selected: value === this.draft.max_tokens
            }, msg("ccore.tokens", {value1: value.toLocaleString(), value2: budgetUses[value] ? ' · ' + budgetUses[value] : ''}))));
        const precision = el('fieldset', {class: 'ccore-precision', disabled: working || this.starting},
            el('legend', {}, msg("ccore.model_precision")),
            hint(msg("ccore.if_you_re_unsure_which_to_choose_start_with_standard")),
            this.capabilities.model_variants.map(value => {
                const [label, quantization, description] = precisionOptions[value];
                const defaultLabel = value === this.capabilities.default_model_variant ? msg("ccore.default_suffix") : "";
                return el('label', {class: 'check-row'},
                    el('input', {type: 'radio', name: 'ccore-precision', value,
                        checked: value === this.draft.model_variant,
                        onchange: () => this.update('model_variant', value)}),
                    el('span', {}, el('strong', {}, msg("ccore.precision_caption", {label, quantization, defaultLabel})),
                        el('small', {class: 'muted'}, description)));
            }),
            hint(msg("ccore.if_higher_precision_won_t_fit_foundry_checks_whether_standard_or_a_smaller_t", {value1: msg(this.withImage ? "ccore.same_image_description_seed" : "ccore.same_description_seed")})));
        const translationPrecision = el('fieldset', {class:'ccore-precision', disabled:working || this.starting},
            el('legend', {}, msg("ccore.translation_precision")),
            hint(msg("ccore.translation_precision_hint")),
            ...this.capabilities.translation.precisions.map(value => el('label', {class:'check-row'},
                el('input', {type:'radio', name:'ccore-translation-precision', value,
                    checked:value === this.draft.translation_precision,
                    onchange:()=>this.update('translation_precision',value)}),
                el('span', {}, el('strong', {}, msg(value === 'q4' ? "ccore.translation_q4" : "ccore.translation_q8")),
                    el('small', {class:'muted'}, msg(value === 'q4' ? "ccore.translation_q4_help" : "ccore.translation_q8_help"))))),
            hint(msg("ccore.translation_gpu_only")));
        return [
            this.withImage ? this.reference() : hint(msg("ccore.describe_one_stylized_prop_name_its_shape_materials_colors_and_the_details_t")),
            field(msg("ccore.prop_name"), name),
            field(msg("ccore.examples"), examples, msg("ccore.see_what_you_can_ask_ccore_to_make_choose_from_12_example_objects_to_load_a")),
            field(msg("ccore.description"), prompt, this.withImage ? msg("ccore.tell_ccore_what_to_keep_from_the_reference_and_what_to_change") : null),
            hint(msg("ccore.english_prompt_guidance")),
            translationPrecision,
            el('div', {class: 'actions'}, enhance,
                translate,
                el('span', {class: 'activity-feedback', 'data-busy': String(working)},
                    working ? workingStar(28) : null, el('span', {class: 'muted'}, enhancementModel)),
                working ? elapsedTime(this.enhancing.startedAt) : null,
                this.stopEnhanceButton,
                !working && this.originalDescription !== undefined
                    ? button(msg("ccore.restore_original"), () => this.restoreDescription()) : null),
            this.enhanceStatus,
            precision,
            el('details', {}, el('summary', {}, msg("ccore.advanced")), field(msg("ccore.seed"), seed),
                field(msg("ccore.generation_budget"), budget, msg("ccore.this_limits_how_much_ccore_can_generate_higher_budgets_reserve_more_vram_and"))),
            hint(this.withImage ? msg("ccore.image_text_needs_extra_gpu_memory_for_the_vision_projector_foundry_downloads") : msg("ccore.foundry_downloads_your_chosen_model_the_first_time_you_use_it")),
        ];
    }

    review() {
        if (this.run?.active) {
            this.phase = el('strong', {role: 'status'});
            this.transfer = hint('');
            this.meter = el('progress', {max: 100, 'aria-label': msg("ccore.ccore_generation_progress")});
            this.stop = button(msg("ccore.stop_generation"), () => this.cancel());
            const elapsed = elapsedTime(this.run.started_at ? this.run.started_at * 1000 : this.runStartedAt);
            this.progress();
            return [el('div', {class: 'wizard-busy'}, workingStar(),
                el('div', {class: 'stage-progress'}, sourceMessage(this.phase), elapsed, this.transfer, this.meter,
                    el('div', {class: 'actions'}, this.stop)))];
        }
        if (!this.run?.result) {
            return [el('p', {role: 'alert'}, this.run?.error || 'No finished prop was saved.')];
        }
        const {measurements} = this.run.result;
        const host = el('div', {class: 'wizard-mesh', 'aria-label': msg("ccore.ccore_prop_preview"), 'data-ccore-preview': ''},
            hint(msg("ccore.opening_the_saved_glb")));
        const status = el('p', {role: 'status'}, msg("ccore.loading_the_preview"));
        const reset = button(msg("ccore.reset_view"), () => {
            this.viewer?.viewer?.fitToViewer();
            this.viewer?.viewer?.forceRender();
        });
        const revision = this.revision;
        this.viewerReady = false;
        this.previewAction = null;
        requestAnimationFrame(async () => {
            if (this.disposed || revision !== this.revision) return;
            host.replaceChildren();
            try {
                const dispose = await mountMesh(host, fileUrl(this.id, 'model'), this.capabilities.viewer_module, 'prop.glb');
                if (this.disposed || revision !== this.revision) return dispose();
                this.viewer = dispose;
                this.viewer.viewer?.toggleGrid?.(false);
                this.viewer.viewer?.forceRender();
                this.viewerReady = true;
                host.dataset.loaded = 'prop.glb';
                setText(status, msg("ccore.drag_to_orbit_scroll_to_zoom"));
                if (this.previewAction) this.previewAction.disabled = false;
            } catch (error) {
                if (revision === this.revision && !this.disposed) setText(status, sourceMessage(error.message));
            }
        });
        return [el('h3', {}, this.run.config.name), host,
            el('div', {class: 'actions'}, reset, status),
            hint(msg("ccore.triangles", {value1: measurements.triangles.toLocaleString(), value2: measurements.animations ? msg("ccore.animation_count", {count:measurements.animations}) : msg("ccore.static_prop"), value3: precisionOptions[this.run.config.model_variant][1]}))];
    }

    downloads() {
        return [el('h3', {}, this.run.config.name),
            hint(msg("ccore.the_glb_is_the_asset_you_just_reviewed_the_zip_adds_a_readme_model_credits_a")),
            el('div', {class: 'actions'},
                el('a', {class: 'download-link', href: fileUrl(this.id, 'model', true), download: 'prop.glb'}, msg("ccore.download_glb")),
                el('a', {class: 'download-link', href: fileUrl(this.id, 'archive', true), download: 'ccore-prop.zip'}, msg("ccore.download_zip"))),
            hint(msg("ccore.a_copy_is_saved_in_foundry_history"))];
    }

    render() {
        if (this.disposed) return;
        this.revision = (this.revision || 0) + 1;
        this.viewer?.();
        this.viewer = null;
        this.phase = null;
        const rail = el('aside', {class: 'wizard-rail'}, el('span', {class: 'eyebrow'}, this.withImage ? msg("ccore.ccore_image_text") : msg("ccore.ccore_text_to_prop")),
            el('h3', {}, sourceMessage(ccoreTitle(this.withImage))),
            el('ol', {class: 'wizard-steps'}, titles.map((title, i) => el('li', {
                class: i === this.page ? 'current' : '', 'aria-current': i === this.page ? 'step' : null,
            }, el('span', {class: 'step-number'}, String(i + 1)), el('strong', {}, title)))),
            el('div', {class: 'wizard-rail-note'}, link(msg("ccore.powered_by_ccore"), credits)));
        const content = this.page === 0 ? this.describe() : this.page === 1 ? this.review() : this.downloads();
        const actions = [];
        if (this.page === 0) {
            this.generateButton = button(this.starting ? msg("ccore.starting") : msg("ccore.generate_prop"), () => this.start(), {
                class: 'primary', disabled: this.starting || Boolean(this.enhancing) || this.uploading || !this.canGenerate(),
            });
            actions.push(this.generateButton);
        } else if (this.page === 1 && !this.run?.active) {
            actions.push(button(msg("ccore.edit_description"), () => this.go(0)));
            const config = this.run?.config;
            const fallback = this.run?.fallbacks ?? [];
            const smaller = this.run?.smaller_budget;
            const options = !fallback.length && config && this.capabilities.token_limits.includes(smaller)
                ? [{model_variant: config.model_variant, max_tokens: smaller}]
                : fallback;
            for (const {model_variant, max_tokens} of options) {
                const [label] = precisionOptions[model_variant];
                actions.push(button(msg("ccore.retry_with_tokens", {label: label, value2: max_tokens.toLocaleString()}), () => {
                    if (this.starting) return;
                    this.update('model_variant', model_variant);
                    this.update('max_tokens', max_tokens);
                    this.start();
                }, {class: 'primary', disabled: this.starting}));
            }
            if (this.run?.result) {
                this.previewAction = button(msg("ccore.continue_to_downloads"), () => this.go(2),
                    {class: 'primary', disabled: !this.viewerReady});
                actions.push(this.previewAction);
            }
        } else if (this.page === 2) {
            actions.push(button(msg("ccore.back_to_preview"), () => this.go(1)), button(msg("ccore.create_another_prop"), () => this.go(0)));
        }
        actions.push(button(msg("ccore.choose_a_workflow"), () => this.shell.open('Choose a Workflow'), {class: 'quiet'}));
        const intro = this.page === 0 ? el('div', {class: 'workflow-intro'},
            hint(this.withImage ? msg("ccore.start_with_a_clear_photo_sketch_or_render_of_one_prop_ccore_uses_its_vision") :
                msg("ccore.ccore_turns_a_written_description_into_a_stylized_3d_prop_use_it_for_individ"))) : null;
        replaceContent(this.element, rail, el('section', {class: 'wizard-panel'},
            intro,
            el('header', {class: 'page-head'}, el('span', {class: 'eyebrow'}, msg("ccore.step_of_3", {value1: this.page + 1})),
                el('h2', {tabIndex: -1}, titles[this.page])),
            ...content, this.error ? el('p', {role: 'alert'}, this.error) : null,
            el('footer', {class: 'wizard-footer'}, el('div', {class: 'actions'}, actions))));
    }

    dispose() {
        this.disposed = true;
        void this.stopEnhancement();
        clearTimeout(this.timer);
        this.viewer?.();
    }
}
