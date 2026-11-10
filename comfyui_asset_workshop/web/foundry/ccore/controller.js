import {api} from '/scripts/api.js';
import {el, button, field, hint, link} from '../dom.js';
import {elapsedTime, workingStar} from '../activity.js';
import {inputURL, uploadReference} from '../images/references.js';
import {pollResources, request} from '../services.js';
import {mountMesh} from '../wizard/preview.js';
import {ccoreDraftKey, ccoreTitle, syncPropGraph} from './graph.js';
import {propExamples} from './examples.js';

const titles = ['Describe your prop', 'Review your prop', 'Download your asset'];
const credits = 'https://huggingface.co/ccore/Qwen3.5-4B-GLB-3D-Coder';
const defaults = {name: 'New prop', prompt: '', seed: 42, max_tokens: 65536};
const budgetUses = {16384: 'Simple props', 32768: 'More detail', 65536: 'Most room (default)'};
const precisionOptions = {
    q4_k_m: ['Standard', 'Q4_K_M', 'Uses less GPU memory and leaves more room for longer generations.'],
    q8_0: ['Higher precision', 'Q8_0', 'Keeps more of the model’s original precision and uses more GPU memory.'],
};
// CCORE enhancement uses the default Q8 weights from description_helper.py.
const enhancementModel = 'Qwen3.5-9B-Heretic Q8_0';
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
        if (this.id) {
            this.run = await request(runUrl(this.id));
            this.draft = {...this.run.config};
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
        const example = propExamples.find(item => item.id === id);
        if (!example && id !== 'custom') return;
        this.example = id;
        this.originalDescription = undefined;
        this.enhanceMessage = '';
        this.error = '';
        this.draft.name = example?.name ?? defaults.name;
        this.draft.prompt = example?.prompt ?? '';
        this.remember();
        this.render();
        this.element.querySelector('textarea')?.focus();
    }

    async enhance() {
        if (this.enhancing || !this.draft.prompt.trim()) return;
        const original = this.draft.prompt;
        const operation = {id: crypto.randomUUID().replaceAll('-', ''), cancelled: false, startedAt: Date.now()};
        this.enhancing = operation;
        this.error = '';
        this.enhanceMessage = 'Preparing the local description assistant…';
        this.render();
        const stopPolling = pollResources(status => {
            const helper = status.description_helper;
            if (operation.cancelled || helper?.asset !== operation.id || !helper.running) return;
            const download = status.download;
            const progress = helper.downloading && download?.total
                ? ' · ' + Math.min(100, Math.floor(100 * download.bytes / download.total)) + '%' : '';
            this.showEnhanceMessage((helper.phase || 'Enhancing your description…') + progress);
        }, () => {});
        try {
            const result = await request('ccore/enhance', {request_id: operation.id, prompt: original});
            if (this.disposed) return;
            if (operation.cancelled || result.cancelled) {
                this.enhanceMessage = 'Enhancement stopped. You can keep editing.';
            } else if (this.draft.prompt === original) {
                this.originalDescription = original;
                this.example = '';
                this.update('prompt', result.text);
                this.enhanceMessage = 'Description enhanced. Review or edit it before generating.';
            }
        } catch (error) {
            if (!this.disposed) {
                this.enhanceMessage = operation.cancelled ? 'Enhancement stopped.' : '';
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
        if (this.enhanceStatus) this.enhanceStatus.textContent = message;
    }

    async stopEnhancement() {
        const operation = this.enhancing;
        if (!operation || operation.cancelled) return;
        operation.cancelled = true;
        if (!this.disposed) {
            this.showEnhanceMessage('Stopping enhancement…');
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
        this.enhanceMessage = 'Original description restored.';
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
            input, image ? el('img', {src: inputURL(image), alt: 'Reference for this CCORE prop',
                style: 'display:block;max-width:100%;max-height:160px;object-fit:contain'}) : null,
            hint(this.uploading ? 'Uploading reference…' : 'Drop one image here, or choose a file.'),
            el('div', {class: 'actions'}, button(image ? 'Replace image' : 'Upload image', () => input.click(), {disabled}),
                button('Create an image', () => {
                    this.remember();
                    this.shell.imageOrigin = {method: 'ccore-image'};
                    this.shell.openImages('Create Images');
                }, {disabled: disabled || Boolean(this.enhancing)}),
                image ? button('Remove image', () => {this.update('image', ''); this.render();}, {disabled}) : null));
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
                if (this.phase) this.phase.textContent = error.message;
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
        this.phase.textContent = this.cancelling ? 'Stopping generation…' : this.run.phase;
        const percent = transfer?.total ? Math.min(100, Math.floor(transfer.bytes / transfer.total * 100)) : null;
        this.transfer.textContent = percent === null ? 'Long descriptions can take several minutes.' :
            (transfer.phase === 'verifying SHA-256' ? 'Checking the downloaded model…' : 'Downloading ' + percent + '%');
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
            el('option', {value: '', disabled: true}, 'Choose an example'),
            el('option', {value: 'custom'}, 'Custom'),
            propExamples.map(({id, name, category}) =>
                el('option', {value: id}, category + ' · ' + name)));
        examples.value = this.example || '';
        const enhance = button('Enhance description', () => this.enhance(), {
            disabled: working || !this.draft.prompt.trim(),
        });
        const prompt = el('textarea', {rows: 8, maxLength: 5000, value: this.draft.prompt, readOnly: working,
            placeholder: 'A small brass lantern with a green glass shade and a curved handle…',
            oninput: e => {
                this.example = '';
                examples.value = '';
                this.update('prompt', e.target.value);
                enhance.disabled = !e.target.value.trim();
                this.generateButton.disabled = !this.canGenerate() || this.starting;
            }});
        this.enhanceStatus = el('p', {role: 'status', class: 'muted'}, this.enhanceMessage || '');
        this.stopEnhanceButton = working ? button('Stop enhancement', () => this.stopEnhancement(), {
            disabled: this.enhancing.cancelled,
        }) : null;
        const seed = el('input', {type: 'number', min: 0, max: 2147483647, step: 1, value: this.draft.seed,
            oninput: e => this.update('seed', e.target.valueAsNumber)});
        const budget = el('select', {onchange: e => this.update('max_tokens', Number(e.target.value))},
            this.capabilities.token_limits.map(value => el('option', {
                value, selected: value === this.draft.max_tokens
            }, value.toLocaleString() + ' tokens' + (budgetUses[value] ? ' · ' + budgetUses[value] : ''))));
        const precision = el('fieldset', {class: 'ccore-precision', disabled: working || this.starting},
            el('legend', {}, 'Model precision'),
            hint('If you’re unsure which to choose, start with Standard.'),
            this.capabilities.model_variants.map(value => {
                const [label, quantization, description] = precisionOptions[value];
                const defaultLabel = value === this.capabilities.default_model_variant ? ' (default)' : '';
                return el('label', {class: 'check-row'},
                    el('input', {type: 'radio', name: 'ccore-precision', value,
                        checked: value === this.draft.model_variant,
                        onchange: () => this.update('model_variant', value)}),
                    el('span', {}, el('strong', {}, label + ' · ' + quantization + defaultLabel),
                        el('small', {class: 'muted'}, description)));
            }),
            hint('If Higher precision won’t fit, Foundry checks whether Standard or a smaller token budget fits. You choose what to try. ' +
                (this.withImage ? 'Your image, description and seed stay the same.' : 'Your description and seed stay the same.')));
        return [
            this.withImage ? this.reference() : hint('Describe one stylized prop. Name its shape, materials, colors and the details that matter.'),
            field('Prop name', name),
            field('Examples', examples, 'See what you can ask CCORE to make. Choose from 12 example objects to load a complete, editable description. Choose Custom to start from scratch.'),
            field('Description', prompt, this.withImage ? 'Tell CCORE what to keep from the reference and what to change.' : null),
            el('div', {class: 'actions'}, enhance,
                el('span', {class: 'activity-feedback', 'data-busy': String(working)},
                    working ? workingStar(28) : null, el('span', {class: 'muted'}, enhancementModel)),
                working ? elapsedTime(this.enhancing.startedAt) : null,
                this.stopEnhanceButton,
                !working && this.originalDescription !== undefined
                    ? button('Restore original', () => this.restoreDescription()) : null),
            this.enhanceStatus,
            precision,
            el('details', {}, el('summary', {}, 'Advanced'), field('Seed', seed),
                field('Generation budget', budget, 'This limits how much CCORE can generate. Higher budgets reserve more VRAM and give detailed props more room. If CCORE hits the limit, the prop may be incomplete.')),
            hint(this.withImage ? 'Image + Text needs extra GPU memory for the vision projector. Foundry downloads the selected model and projector when first needed.' : 'Foundry downloads your chosen model the first time you use it.'),
        ];
    }

    review() {
        if (this.run?.active) {
            this.phase = el('strong', {role: 'status'});
            this.transfer = hint('');
            this.meter = el('progress', {max: 100, 'aria-label': 'CCORE generation progress'});
            this.stop = button('Stop generation', () => this.cancel());
            const elapsed = elapsedTime(this.run.started_at ? this.run.started_at * 1000 : this.runStartedAt);
            this.progress();
            return [el('div', {class: 'wizard-busy'}, workingStar(),
                el('div', {class: 'stage-progress'}, this.phase, elapsed, this.transfer, this.meter,
                    el('div', {class: 'actions'}, this.stop)))];
        }
        if (!this.run?.result) {
            return [el('p', {role: 'alert'}, this.run?.error || 'No finished prop was saved.')];
        }
        const {measurements} = this.run.result;
        const host = el('div', {class: 'wizard-mesh', 'aria-label': 'CCORE prop preview', 'data-ccore-preview': ''},
            hint('Opening the saved GLB…'));
        const status = el('p', {role: 'status'}, 'Loading the preview…');
        const reset = button('Reset view', () => {
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
                status.textContent = 'Drag to orbit. Scroll to zoom.';
                if (this.previewAction) this.previewAction.disabled = false;
            } catch (error) {
                if (revision === this.revision && !this.disposed) status.textContent = error.message;
            }
        });
        return [el('h3', {}, this.run.config.name), host,
            el('div', {class: 'actions'}, reset, status),
            hint(measurements.triangles.toLocaleString() + ' triangles · ' +
                (measurements.animations ? measurements.animations + ' animation clips' : 'Static prop') + ' · ' +
                precisionOptions[this.run.config.model_variant][1])];
    }

    downloads() {
        return [el('h3', {}, this.run.config.name),
            hint('The GLB is the asset you just reviewed. The ZIP adds a README, model credits and a file catalog.'),
            el('div', {class: 'actions'},
                el('a', {class: 'download-link', href: fileUrl(this.id, 'model', true), download: 'prop.glb'}, 'Download GLB'),
                el('a', {class: 'download-link', href: fileUrl(this.id, 'archive', true), download: 'ccore-prop.zip'}, 'Download ZIP')),
            hint('A copy is saved in Foundry History.')];
    }

    render() {
        if (this.disposed) return;
        this.revision = (this.revision || 0) + 1;
        this.viewer?.();
        this.viewer = null;
        this.phase = null;
        const rail = el('aside', {class: 'wizard-rail'}, el('span', {class: 'eyebrow'}, this.withImage ? 'CCORE / IMAGE + TEXT' : 'CCORE / TEXT TO PROP'),
            el('h3', {}, ccoreTitle(this.withImage)),
            el('ol', {class: 'wizard-steps'}, titles.map((title, i) => el('li', {
                class: i === this.page ? 'current' : '', 'aria-current': i === this.page ? 'step' : null,
            }, el('span', {class: 'step-number'}, String(i + 1)), el('strong', {}, title)))),
            el('div', {class: 'wizard-rail-note'}, link('Powered by CCORE', credits)));
        const content = this.page === 0 ? this.describe() : this.page === 1 ? this.review() : this.downloads();
        const actions = [];
        if (this.page === 0) {
            this.generateButton = button(this.starting ? 'Starting…' : 'Generate prop', () => this.start(), {
                class: 'primary', disabled: this.starting || Boolean(this.enhancing) || this.uploading || !this.canGenerate(),
            });
            actions.push(this.generateButton);
        } else if (this.page === 1 && !this.run?.active) {
            actions.push(button('Edit description', () => this.go(0)));
            const config = this.run?.config;
            const fallback = this.run?.fallbacks ?? [];
            const smaller = this.run?.smaller_budget;
            const options = !fallback.length && config && this.capabilities.token_limits.includes(smaller)
                ? [{model_variant: config.model_variant, max_tokens: smaller}]
                : fallback;
            for (const {model_variant, max_tokens} of options) {
                const [label] = precisionOptions[model_variant];
                actions.push(button('Retry with ' + label + ' · ' + max_tokens.toLocaleString() + ' tokens', () => {
                    if (this.starting) return;
                    this.update('model_variant', model_variant);
                    this.update('max_tokens', max_tokens);
                    this.start();
                }, {class: 'primary', disabled: this.starting}));
            }
            if (this.run?.result) {
                this.previewAction = button('Continue to downloads', () => this.go(2),
                    {class: 'primary', disabled: !this.viewerReady});
                actions.push(this.previewAction);
            }
        } else if (this.page === 2) {
            actions.push(button('Back to preview', () => this.go(1)), button('Create another prop', () => this.go(0)));
        }
        actions.push(button('Choose a workflow', () => this.shell.open('Choose a Workflow'), {class: 'quiet'}));
        const intro = this.page === 0 ? el('div', {class: 'workflow-intro'},
            hint(this.withImage ? 'Start with a clear photo, sketch or render of one prop. CCORE uses its vision projector and your description to build a stylized 3D asset you can review and export as GLB.' :
                'CCORE turns a written description into a stylized 3D prop. Use it for individual objects like tools, crates, or furniture. Preview the result in 3D and export it as a GLB.')) : null;
        this.element.replaceChildren(rail, el('section', {class: 'wizard-panel'},
            intro,
            el('header', {class: 'page-head'}, el('span', {class: 'eyebrow'}, 'STEP ' + (this.page + 1) + ' OF 3'),
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
