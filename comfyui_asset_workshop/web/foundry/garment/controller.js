import {api} from '/scripts/api.js';
import {elapsedTime, workingStar} from '../activity.js';
import {el, button, field, hint, link} from '../dom.js';
import {capturePhoto, inputURL, uploadReference} from '../images/references.js';
import {request} from '../services.js';
import {mountMesh} from '../wizard/preview.js';
import {syncGarmentGraph} from './graph.js';
import {GarmentEditor, operationName} from './editor.js';

const titles = ['Start your garment', 'Edit & compare', 'Prepare for Blender', 'Preview on a character', 'Export your garment'];
const mainSteps = [0, 1, 2, 4];
const modes = {
    text: ['Description', 'Describe one garment. Give its silhouette, length, sleeves and closures.'],
    image: ['Image', 'Use a clear photo or render of one garment with the whole shape visible.'],
    sketch: ['Sketch', 'Use a clear outline sketch. Keep seams and important edges easy to read.'],
    surprise: ['Surprise me', 'Generate a garment without a description or reference.'],
};

const defaults = {
    name: 'New garment', mode: 'text', prompt: '', image: '', seed: 42,

};
const base = id => 'garment/runs/' + id;
const url = (id, name, download = false) => '/mumblebox-foundry/v1/' + base(id) + '/file/' + name + (download ? '?download=1' : '');

export class GarmentWizard {
    constructor(shell, {resume = false, runId = null} = {}) {
        this.shell = shell;
        const saved = shell.node.properties.foundryGarment || {};
        this.draft = {...defaults, ...saved.draft};
        this.customGeneration = saved.customGeneration === true;
        this.budget = saved.budget || 20000;
        this.id = runId || saved.id;
        this.resume = resume || Boolean(runId);
        this.page = 0;
        this.element = el('div', {class: 'wizard', 'data-garment-wizard': ''});
    }

    async init() {
        this.capabilities = await request('garment/capabilities');
        this.generationPresets = this.capabilities.generation_presets;
        const {points, steps} = this.generationPresets.balanced;
        this.draft.points ??= points;
        this.draft.steps ??= steps;
        if (this.resume && this.id) {
            this.run = await request(base(this.id));
            const {points, steps} = this.run.config;
            this.customGeneration = this.customGeneration && points === this.draft.points && steps === this.draft.steps;
            this.draft = {...this.run.config};
            this.budget = this.run.mesh?.triangle_budget ?? this.budget;
            this.fit = this.run.drape?.settings;
            this.page = this.run.archive ? 4 : this.run.stage === 'generate' || this.run.stage === 'edit' ? 1
                : ['fit', 'drape'].includes(this.run.stage) ? 3 : 2;
        }
        syncGarmentGraph(this.shell.node, this.draft, this.budget);
        if (this.resume && this.run) this.remember();
        this.render();
        if (this.run?.active) this.poll();
        return this.element;
    }

    remember() {
        this.shell.node.properties.foundryGarment = {
            id: this.id, draft: {...this.draft}, budget: this.budget, customGeneration: this.customGeneration,
        };
    }

    update(key, value) {
        this.draft[key] = value;
        this.remember();
        if (this.generate) this.generate.disabled = !this.canGenerate();
    }

    canGenerate() {
        return !this.pending && !this.capabilities.modes[this.draft.mode] &&
            (this.draft.mode === 'surprise' || Boolean(this.draft.mode === 'text' ? this.draft.prompt.trim() : this.draft.image));
    }

    async act(operation) {
        if (this.pending) return;
        this.pending = true;
        this.error = '';
        this.render();
        try { await operation(); }
        catch (error) { this.error = error.message; }
        finally {
            this.pending = false;
            this.render();
        }
    }

    async start() {
        if (!this.canGenerate()) return;
        await this.act(async () => {
            if (this.id && (await request(base(this.id))).active) {
                throw Error('Resume or stop the running garment before starting another.');
            }
            syncGarmentGraph(this.shell.node, this.draft, this.budget);
            const id = crypto.randomUUID().replaceAll('-', '');
            this.run = await request('garment/runs', {...this.draft, request_id: id, client_id: api.clientId});
            this.id = id;
            this.remember();
            this.page = 1;
            this.poll();
        });
    }

    async applyEdit(edit, prompt, points) {
        await this.act(async () => {
            const id = crypto.randomUUID().replaceAll('-', '');
            this.run = await request(base(this.id) + '/edit', {request_id:id, edit, prompt, points, client_id:api.clientId});
            this.id = id;
            this.remember();
            this.poll();
        });
    }

    async selectVersion(id) {
        if (!id || this.id === id) return;
        await this.act(async () => {
            const run = await request(base(id));
            if (!run.result) throw Error('Choose a completed garment version.');
            this.run = run;
            this.id = id;
            this.showEditor = false;
            this.compare = Boolean(run.parent);
            this.fit = run.drape?.settings;
            this.approved = null;
            this.remember();
        });
    }

    async stage(action, data = {}) {
        await this.act(async () => {
            if (action === 'sew') syncGarmentGraph(this.shell.node, this.draft, this.budget);
            this.run = await request(base(this.id) + '/' + action, {client_id: api.clientId, ...data});
            if (this.run.active) this.poll();
        });
    }

    poll() {
        clearTimeout(this.timer);
        this.timer = setTimeout(async () => {
            if (this.disposed) return;
            try {
                this.run = await request(base(this.id));
                if (this.disposed) return;
                if (this.run.active) {
                    if (this.phase) this.phase.textContent = this.run.phase;
                    this.poll();
                } else {
                    if (this.run.archive) this.page = 4;
                    if (this.run.stage === 'drape' && this.run.status === 'complete') this.page = 3;
                    if (this.run.stage === 'edit') {
                        if (this.run.result) {
                            this.showEditor = false;
                            this.compare = true;
                            this.fit = null;
                            this.approved = null;
                        } else if (this.run.parent) {
                            this.error = this.run.error || 'The edit stopped. Your earlier version is still available.';
                            this.id = this.run.parent;
                            this.run = await request(base(this.id));
                            this.remember();
                        }
                    }
                    this.render();
                }
            } catch (error) {
                this.error = error.message;
                this.render();
            }
        }, 1000);
    }

    reference(key = 'image') {
        const back = key === 'back_image';
        const add = file => this.act(async () => this.update(key, (await uploadReference(file)).filename));
        const picker = el('input', {type: 'file', accept: 'image/png,image/jpeg,image/webp', hidden: true,
            onchange: e => { if (e.target.files[0]) add(e.target.files[0]); }});
        return el('div', {}, picker, el('div', {class: 'creator-drop',
            ondragover: e => e.preventDefault(), ondrop: e => {
                e.preventDefault();
                if (e.dataTransfer.files[0]) add(e.dataTransfer.files[0]);
            }},
            this.draft[key] ? el('img', {src: inputURL(this.draft[key]), alt: back ? 'Back garment reference' : 'Front garment reference', class: 'webcam-preview'}) : null,
            el('div', {class: 'actions'},
                button(back ? 'Upload back reference' : 'Upload front reference', () => picker.click(), {disabled: this.pending}),
                this.draft.mode === 'image' && navigator.mediaDevices
                    ? button('Take a photo', () => capturePhoto(this.shell, add), {disabled: this.pending}) : null,
                this.draft[key] ? button('Remove reference', () => {this.update(key, '');this.render();}) : null),
            hint('Drop one PNG, JPEG or WebP here.')));
    }

    number(key, low, high, edit = value => this.update(key, value)) {
        return el('input', {type: 'number', value: this.draft[key], min: low, max: high, step: 1,
            onchange: e => edit(e.target.valueAsNumber)});
    }

    generationSettings() {
        const presets = Object.entries(this.generationPresets);
        const preset = el('select', {},
            presets.map(([value, {label, points, steps}]) => el('option', {value},
                label + ' · ' + points.toLocaleString() + ' points · ' + steps + ' steps')),
            el('option', {value: 'custom'}, 'Custom'));
        const match = presets.find(([, {points, steps}]) => points === this.draft.points && steps === this.draft.steps);
        preset.value = this.customGeneration ? 'custom' : match?.[0] ?? 'custom';
        const customize = (key, value) => {
            this.customGeneration = true;
            preset.value = 'custom';
            this.update(key, value);
        };
        const points = this.number('points', 100, 8192, value => customize('points', value));
        const steps = this.number('steps', 2, 250, value => customize('steps', value));
        const advanced = el('details', {open: preset.value === 'custom'}, el('summary', {}, 'Advanced'),
            field('Seed', this.number('seed', 0, 2147483647), 'Change it for another design from the same input.'),
            field('Drape points', points, 'More points use more GPU memory.'),
            field('Sampling steps', steps, 'More steps take longer.'));
        preset.addEventListener('change', () => {
            this.customGeneration = preset.value === 'custom';
            if (this.customGeneration) {
                advanced.open = true;
            } else {
                const settings = this.generationPresets[preset.value];
                this.draft.points = settings.points;
                this.draft.steps = settings.steps;
                points.value = settings.points;
                steps.value = settings.steps;
            }
            this.remember();
        });
        return [field('Generation preset', preset,
            'Use Balanced to start. Choose Custom to set your own point count and steps.'), advanced];
    }

    describe() {
        const mode = this.draft.mode;
        return [
            hint('Design clothing from a description, image or sketch. Edit the sewing pattern or 3D shape, then export a sewn mesh, editable pattern and 3D drape reference for Blender. You can export without a character. Tailor the garment and check its movement in your 3D editor.'),
            field('Garment name', el('input', {value: this.draft.name, maxLength: 80, oninput: e => this.update('name', e.target.value)})),
            el('fieldset', {class: 'ccore-precision', disabled: this.pending}, el('legend', {}, 'Starting point'),
                Object.entries(modes).map(([value, [label, detail]]) => el('label', {class: 'check-row'},
                    el('input', {type: 'radio', name: 'garment-mode', value, checked: value === mode,
                        onchange: () => {this.update('mode', value);this.render();}}),
                    el('span', {}, el('strong', {}, label), el('small', {class: 'muted'}, detail))))),
            mode === 'text' ? field('Description', el('textarea', {rows: 4, maxLength: 500, value: this.draft.prompt,
                placeholder: this.capabilities.example, oninput: e => this.update('prompt', e.target.value)})) : null,
            ['image','sketch'].includes(mode) ? [this.reference(), el('details', {open:Boolean(this.draft.back_image)},
                el('summary', {}, 'Add a matching back view'), hint('Use the back of the same garment, framed like the front.'),
                this.reference('back_image'))] : null,
            mode === 'text' ? button('Try the waistcoat example', () => {
                this.update('prompt', this.capabilities.example);this.render();
            }) : null,
            ...this.generationSettings(),
            this.capabilities.modes[mode] ? el('p', {role: 'alert'}, this.capabilities.modes[mode]) :
                hint('The generator and sewing-pattern model take turns using the GPU. Keep enough free VRAM for both stages.'),
        ];
    }

    busy() {
        this.phase = el('strong', {}, this.run.phase);
        return el('div', {class: 'activity-feedback', 'data-busy': 'true', role: 'status'}, workingStar(),
            el('div', {}, this.phase, elapsedTime(this.run.started_at * 1000)),
            button('Stop this stage', () => this.stage('cancel'), {disabled: this.pending}));
    }

    preview(filename, label, id = this.id) {
        const host = el('div', {class: 'wizard-mesh', 'aria-label': label});
        const status = hint('Loading 3D preview…');
        const revision = this.revision;
        requestAnimationFrame(async () => {
            if (this.disposed || revision !== this.revision) return;
            try {
                const dispose = await mountMesh(host, url(id, filename), this.capabilities.viewer_module, filename);
                if (this.disposed || revision !== this.revision) {dispose();return;}
                this.viewers.push(dispose);
                host.dataset.loaded = 'true';
                status.textContent = 'Drag to rotate. Scroll to zoom.';
            } catch (error) { status.textContent = error.message; }
        });
        return el('section', {}, el('h3', {}, label), host, status);
    }

    review() {
        if (!this.run?.result) return [hint('Your 3D drape and sewing sheet will appear here.')];
        const {panels, stitches, points} = this.run.result;
        const versions = this.run.versions || [];
        const version = el('select', {onchange: e => this.selectVersion(e.target.value)},
            versions.map((item, index) => el('option', {value:item.id, selected:item.id === this.id},
                (index + 1) + ' · ' + operationName(item.edit) + ' · seed ' + item.seed)));
        const previous = this.run.parent;
        const pattern = (id, label) => el('img', {src: url(id, 'garment_pattern.png'), alt: label, class: 'garment-pattern-sheet'});
        const workspace = this.showEditor && this.editor?.source && this.editor.id === this.id ? this.editor.element : null;
        const compare = previous && this.compare;
        const visuals = compare ? el('div', {class:'garment-review-grid'},
            el('section', {}, this.preview('drape-particles.glb', 'Before this edit', previous), pattern(previous, 'Previous sewing pattern')),
            el('section', {}, this.preview('drape-particles.glb', 'Current version'), pattern(this.id, 'Current sewing pattern')))
            : el('div', {class:'garment-review-grid'},
                this.preview('drape-particles.glb', '3D particle drape'),
                el('section', {}, el('h3', {}, 'Sewing pattern'), pattern(this.id, 'Labeled sewing panels and stitching')));
        return [
            hint('Use the editing tools to paint changes to a pattern, silhouette or 3D guide. Each edit generates a new garment with its own sewing sheet and 3D drape to compare.'),
            hint(panels + ' panels · ' + stitches + ' stitches · ' + points.toLocaleString() + ' drape points'),
            versions.length > 1 ? field('Saved version', version, 'Choose the version you want to edit, drape or export.') : null,
            el('div', {class:'actions'},
                button(workspace ? 'Close edit tools' : 'Open edit tools', () => {
                    if (workspace) {this.showEditor = false;this.render();return;}
                    this.act(async () => {
                        this.editor ??= new GarmentEditor(this);
                        await this.editor.attach(this.id, this.run.config.prompt, this.run.config.seed);
                        this.showEditor = true;
                    });
                }, {disabled:this.pending, 'aria-expanded':String(Boolean(workspace))}),
                previous ? button(compare ? 'Show current only' : 'Compare with previous', () => {this.compare = !this.compare;this.render();},
                    {'aria-pressed':String(Boolean(compare))}) : null),
            workspace ? el('div', {class:'garment-workbench'}, workspace, visuals) : visuals,
            el('details', {}, el('summary', {}, '3D panel placement sheet'),
                el('img', {src: url(this.id, 'garment_3d_pattern.png'), alt: 'Author panel placement sheet', class: 'garment-pattern-sheet'})),
        ];
    }

    prepare() {
        const budget = el('input', {type:'number', value:this.budget, min:2000, max:100000, step:1000,
            onchange:e=>{this.budget=e.target.valueAsNumber;this.remember();}});
        const mesh = this.run.mesh;
        return [
            hint('Build a UV-mapped mesh from the sewing panels. The export includes this mesh, the editable pattern and the model’s 3D drape reference. Use these to tailor, rig and test the garment in Blender.'),
            field('Triangle limit', budget),
            el('div', {class:'actions'},
                button(mesh ? 'Rebuild sewn mesh' : 'Build sewn mesh', () => this.stage('sew', {budget:this.budget}),
                    {class:mesh ? 'quiet' : 'primary', disabled:this.pending})),
            mesh ? hint(mesh.triangles.toLocaleString() + ' triangles · Pattern UVs and fabric atlas included') : null,
            mesh ? el('section', {class:'garment-drape-controls'},
                el('h3', {}, 'Optional character preview'),
                hint('Try a rough rest-pose cloth simulation on a rigged character. Use it to spot clipping or loose placement before tailoring.'),
                button(this.run.drape || this.run.rig ? 'Review saved character preview' : 'Preview on a character',
                    () => this.go(3), {disabled:this.pending})) : el('details', {}, el('summary', {}, 'Pattern-only export'),
                button('Export pattern and drape only', () => this.go(4), {disabled:this.pending})),
        ];
    }

    fitControls() {
        const body = el('input', {type:'file', accept:'.glb'});
        const update = (key, value) => {this.fit = {...this.fit, [key]:value};};
        const number = (label, key, initial, min, max, step) => field(label, el('input', {
            type:'number', value:this.fit?.[key] ?? initial, min, max, step,
            onchange:e=>update(key,e.target.valueAsNumber)}));
        const fabric = el('select', {onchange:e=>update('fabric',e.target.value)},
            [['light','Light · soft, flowing cloth'], ['medium','Medium · everyday fabric'], ['heavy','Heavy · more structure']]
                .map(([value,label]) => el('option', {value, selected:value === (this.fit?.fabric || 'medium')}, label)));
        return el('section', {class:'garment-drape-controls'},
            field('Rigged character GLB', body, this.fit?.characterName ? 'Current target · ' + this.fit.characterName
                : this.fit?.character ? 'Using the character from the saved drape.' : 'Use a closed, skin-weighted body in its rest pose.'),
            field('Fabric', fabric, 'Changes how the material bends and settles.'),
            el('details', {}, el('summary', {}, 'Placement and simulation settings'),
                el('div', {class:'garment-edit-pair'},
                    number('Uniform scale', 'scale', 1, .05, 10, .01),
                    number('Side offset (m)', 'x', 0, -5, 5, .01),
                    number('Depth offset (m)', 'y', 0, -5, 5, .01),
                    number('Height offset (m)', 'z', 0, -5, 5, .01),
                    number('Clearance (mm)', 'clearance', 4, 0, 30, 1),
                    number('Settling frames', 'frames', 48, 16, 120, 1))),
            button(this.run.drape ? 'Run another preview' : 'Run cloth preview', () => this.act(async () => {
                const file = body.files[0];
                if (file) {
                    if (!/\.glb$/i.test(file.name) || file.size > 150 * 1024 ** 2) {
                        throw Error('Choose one rigged GLB smaller than 150 MB.');
                    }
                    const response = await fetch('/mumblebox-foundry/v1/' + base(this.id) + '/character', {
                        method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file});
                    const data = await response.json();
                    if (!response.ok) throw Error(data.error || 'The character could not be uploaded.');
                    this.fit = {...this.fit, character:data.character, characterName:file.name};
                }
                if (!this.fit?.character) throw Error('Choose a rigged character GLB before draping.');
                this.run = await request(base(this.id) + '/drape', {...this.fit, client_id:api.clientId});
                this.approved = null;
                this.fitView = 'draped-fit.glb';
                if (this.run.active) this.poll();
            }), {class:'primary', disabled:this.pending}));
    }

    reviewFit() {
        const {drape, rig} = this.run;
        const purpose = hint('This is a rough rest-pose preview. Check for loose areas, folds and clipping. Use Blender to tailor the fit, transfer or clean up skin weights, and test the poses you plan to use.');
        if (!drape) return rig
            ? [purpose, hint('This saved wearable was produced with the earlier fit workflow.'),
                this.preview('wearable.glb', 'Saved wearable'), this.fitControls()]
            : [purpose, this.fitControls()];
        const files = {'draped-fit.glb':'Settled with body and clipping', 'starting-fit.glb':'Before simulation',
            'draped-garment.glb':'Settled garment only', ...(rig ? {'wearable.glb':'Skinned wearable'} : {})};
        const shown = Object.hasOwn(files, this.fitView) ? this.fitView : 'draped-fit.glb';
        const selector = el('select', {onchange:e=>{this.fitView=e.target.value;this.render();}},
            Object.entries(files).map(([value,label])=>el('option', {value, selected:value === shown}, label)));
        const accept = button('Transfer test skin weights', () => this.stage('fit', {approve:drape.drape_id}),
            {disabled:this.pending || this.approved !== drape.drape_id});
        const review = el('label', {class:'check-row'},
            el('input', {type:'checkbox', checked:this.approved === drape.drape_id, onchange:e=>{
                this.approved = e.target.checked ? drape.drape_id : null;
                accept.disabled = this.approved !== drape.drape_id;
            }}), el('span', {}, 'I checked the drape for loose areas and clipping.'));
        return [
            purpose,
            hint('Blender Cloth · ' + drape.fabric + ' fabric · ' + drape.frames + ' settling frames'),
            el('p', {role:'status'}, 'Rest-pose clipping went from ' + drape.before.vertices.toLocaleString() + ' to ' +
                drape.after.vertices.toLocaleString() + ' vertices. Deepest remaining mark · ' + drape.after.depth_mm + ' mm.'),
            field('Preview', selector, 'Red marks show vertices inside the body. Also look for gaps where the fabric hangs away from it.'),
            this.preview(shown, files[shown]),
            el('details', {}, el('summary', {}, 'Adjust preview settings'), this.fitControls()),
            rig ? hint('Test skin weights saved. Sampled poses · ' + rig.pose_checks.map(pose => pose.name + ' ' + pose.penetrating + ' clipping').join(' · '))
                : el('details', {}, el('summary', {}, 'Experimental skin transfer'),
                    hint('Transfer weights from this character as a starting point. Refine the result and test poses in Blender.'), review, accept),
        ];
    }


    downloads() {
        const dl = (title, file) => el('a', {class: 'download-link', href: url(this.id, file, true)}, title);
        return [
            hint(this.run.mesh
                ? 'Import the sewn GLB into Blender as your starting mesh. Use the sewing pattern and 3D point drape as references while you adjust fit and prepare the garment for animation.'
                : 'This export contains the editable pattern and 3D point drape. Go back to build a sewn mesh for Blender.'),
            el('div', {class: 'actions'}, dl('Editable pattern (JSON)', 'garment_specification.json'),
                dl('Sewing sheet (SVG)', 'garment_pattern.svg'), dl('3D drape reference (PLY)', 'drape-particles.ply'),
                this.run.mesh ? dl('Sewn mesh (GLB)', 'sewn-garment.glb') : null,
                this.run.archive ? dl('Download ZIP', 'archive') : null),
            this.run.drape || this.run.rig ? el('details', {}, el('summary', {}, 'Optional character preview files'),
                hint('These files are a fit and rigging starting point. Review loose areas and clipping on your character.'),
                el('div', {class:'actions'},
                    this.run.drape ? dl('Settled GLB', 'draped-garment.glb') : null,
                    this.run.drape ? dl('Drape report', 'drape-report.json') : null,
                    this.run.rig ? dl('Test skin GLB', 'wearable.glb') : null,
                    this.run.rig ? dl('Test skin FBX', 'wearable.fbx') : null,
                    this.run.rig ? dl('Fit report', 'fit-report.json') : null)) : null,
            this.run.archive ? hint('Saved in Foundry History.') : null,
        ];
    }

    go(page) {
        if (page === 4) this.downloadFrom = this.page;
        this.page = page;
        this.error = '';
        this.render();
        this.element.querySelector('h2')?.focus({preventScroll:true});
        this.shell.content.scrollTop = 0;
    }

    render() {
        if (this.disposed) return;
        this.revision = (this.revision || 0) + 1;
        this.viewers?.forEach(dispose => dispose());
        this.viewers = [];
        const running = this.run?.active;
        const pages = ['describe', 'review', 'prepare', 'reviewFit', 'downloads'];
        const actions = [];
        this.generate = null;
        if (this.page === 0) {
            this.generate = button(this.pending ? 'Preparing…' : 'Generate garment', () => this.start(),
                {class: 'primary', disabled: !this.canGenerate()});
            actions.push(this.generate);
        } else if (!running) {
            actions.push(button(this.page === 1 ? 'Edit starting point' : 'Back', () => this.go(this.page === 4 ? this.downloadFrom ?? 2 : this.page - 1), {disabled: this.pending}));
            if (this.page === 1 && this.run.result) actions.push(button('Prepare for Blender', () => this.go(2), {class:'primary'}));
            if ((this.page === 2 || this.page === 3) && this.run.mesh) actions.push(button('Continue to export', () => this.go(4), {class:'primary', disabled:this.pending}));
            if (this.page === 4 && !this.run.archive) actions.push(button('Save ZIP to History', () => this.stage('package'),
                {class: 'primary', disabled: this.pending}));
        }
        actions.push(button('Choose a workflow', () => this.shell.open('Choose a Workflow'), {class: 'quiet'}));
        const content = running ? [this.busy()] : this[pages[this.page]]();
        this.element.replaceChildren(
            el('aside', {class: 'wizard-rail'}, el('span', {class: 'eyebrow'}, 'GARMENT PARTICLES / CLOTHING'),
                el('h3', {}, 'Create Clothing'),
                el('ol', {class: 'wizard-steps'}, mainSteps.map((page, index) => el('li', {
                    class: page === (this.page === 3 ? 2 : this.page) ? 'current' : '',
                    'aria-current': page === (this.page === 3 ? 2 : this.page) ? 'step' : null,
                }, el('span', {class: 'step-number'}, String(index + 1)), el('strong', {}, titles[page])))),
                el('div', {class: 'wizard-rail-note'}, link('Garment Particles by Kiyohiro Nakayama and collaborators', this.capabilities.source))),
            el('section', {class: 'wizard-panel'},
                el('header', {class: 'page-head'}, el('span', {class: 'eyebrow'},
                    this.page === 3 ? 'OPTIONAL PREVIEW' : 'STEP ' + (mainSteps.indexOf(this.page) + 1) + ' OF ' + mainSteps.length),
                    el('h2', {tabIndex: -1}, titles[this.page])),
                this.page === 0 ? el('div', {class: 'note-panel'},
                    el('strong', {}, 'Experimental'),
                    hint('This workflow is still in development. Review how the garment fits your character and expect to make adjustments before using it in a project.')) : null,
                ...content,
                (this.error || this.run?.error) ? el('p', {role: 'alert'}, this.error || this.run.error) : null,
                el('footer', {class: 'wizard-footer'}, el('div', {class: 'actions'}, actions))));
    }

    dispose() {
        this.disposed = true;
        clearTimeout(this.timer);
        this.viewers?.forEach(dispose => dispose());
    }
}

