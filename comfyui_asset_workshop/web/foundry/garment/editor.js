import {el, button, field, hint} from '../dom.js';
import {request} from '../services.js';
import {centerOf, editCanvas, projectGuide} from './edit-canvas.js';

const operations = {
    pattern: ['Sewing pattern', 'Paint or erase areas on the flat pattern. The model will rebuild the garment from the edited guide.'],
    silhouette: ['Silhouette', 'Set a view and brush the outline you want the garment to follow.'],
    shape: ['3D points', 'Add, move or erase points. Change the view to work around the garment.'],
    completion: ['Complete a partial garment', 'Erase the areas you want the model to fill. The points you keep guide the new garment.'],
    mix: ['Mix parts from two garments', 'Keep a region of this design and add a region from another design or revision.'],
    blend: ['Blend two seeds', 'Explore a garment between two noise seeds using the same description. Use different point counts to vary the density.'],
};
export const operationName = operation => operations[operation]?.[0] || 'Original generation';
const coordinateMode = operation => operation === 'pattern' || operation === 'silhouette' ? 2 : 3;
const viewDefaults = {azimuth: 0, elevation: 0};

export class GarmentEditor {
    constructor(wizard) {
        this.wizard = wizard;
        this.data = new Map();
        this.drafts = new Map();
        this.mode = 'pattern';
        this.tool = 'paint';
        this.objectives = {};
        this.brush = 16;
        this.view = {...viewDefaults};
        this.history = [];
        this.regions = {other:'', keep:'upper', take:'lower'};
        this.settings = {strength: .7, steps: 100, second_seed: 43, blend: .5};
        this.element = el('section', {class: 'garment-editor'});
    }

    async fetch(id) {
        if (!this.data.has(id)) {
            const payload = await request('garment/runs/' + id + '/guide');
            this.data.set(id, payload.points);
        }
        return this.data.get(id);
    }

    async attach(id, prompt, seed) {
        if (id === this.id && this.source) return;
        this.id = id;
        this.source = null;
        this.mixSources = null;
        this.regions = {other:'', keep:'upper', take:'lower'};
        this.prompt = prompt;
        this.settings.second_seed = (seed + 1) % 2147483648;
        this.settings.second_points = this.wizard.run.config.points;
        this.settings.points = this.wizard.run.config.points;
        const source = await this.fetch(id);
        if (this.id !== id || this.wizard.disposed) return;
        const stride = Math.max(1, Math.ceil(source.length / 2600));
        this.source = source.filter((_, index) => index % stride === 0);
        this.center = centerOf(this.source.map(p => p.slice(2, 5)));
        this.drafts.clear();
        this.reset();
        if (this.mode === 'mix') void this.loadMixSources();
    }

    async loadMixSources() {
        if (this.mixSources) return;
        const id = this.id;
        this.mixSources = [];
        try {
            const sources = await request('garment/runs/' + id + '/mix-sources');
            if (this.id !== id) return;
            this.mixSources = sources;
        } catch (error) {
            if (this.id !== id) return;
            this.error = error.message;
            this.mixSources = null;
        }
        if (this.mode === 'mix') this.render();
    }

    draftKey() {
        return this.mode === 'silhouette' ? [this.mode, this.view.azimuth, this.view.elevation].join('/') : this.mode;
    }

    changeDraft(change) {
        this.drafts.set(this.draftKey(), {guide:this.guide, history:this.history});
        change();
        const draft = this.drafts.get(this.draftKey());
        if (!draft) {
            this.reset();
            return;
        }
        this.guide = draft.guide;
        this.history = draft.history;
        this.error = '';
        this.render();
    }

    reset() {
        const position = this.source.map(p => p.slice(2, 5));
        this.guide = this.mode === 'pattern' ? this.source.map(p => p.slice(0, 2))
            : this.mode === 'silhouette' ? projectGuide(position, this.view.azimuth, this.view.elevation, this.center).map(p => p.slice(0, 2))
            : position;
        this.history = [];
        this.error = '';
        this.render();
    }

    push(points) {
        this.history.push(points);
        if (this.history.length > 24) this.history.shift();
        if (this.undo) this.undo.disabled = false;
    }

    async mix(other, keep, take) {
        if (!other || other === this.id) {this.error = 'Choose a second version.';this.render();return;}
        const id = this.id;
        const second = await this.fetch(other);
        if (this.id !== id || this.mode !== 'mix' || this.wizard.disposed) return;
        const second3d = second.map(p => p.slice(2, 5));
        const targetCenter = centerOf(second3d);
        const centerShift = this.center.map((value, axis) => value - targetCenter[axis]);
        const side = (p, value) => value === 'upper' ? p[1] >= this.center[1] : p[1] < this.center[1];
        const aligned = second3d.map(p => p.map((value, axis) => value + centerShift[axis]));
        const first = this.source.map(p => p.slice(2, 5)).filter(p => side(p, keep));
        const picked = aligned.filter(p => side(p, take));
        this.push(this.guide);
        const merged = [...first, ...picked];
        const stride = Math.max(1, Math.ceil(merged.length / 4096));
        this.guide = merged.filter((_, i) => i % stride === 0);
        this.error = '';
        this.render();
    }

    render() {
        const edit = this.wizard;
        if (!this.source || edit.disposed) return;
        const mode = el('select', {onchange: event => {
            this.changeDraft(() => {
                this.mode = event.target.value;
                this.settings.iterations = undefined;
                this.settings.rate = undefined;
            });
            if (this.mode === 'mix') void this.loadMixSources();
        }}, Object.entries(operations).map(([value, [label]]) => el('option', {value, selected: value === this.mode}, label)));
        const numeric = (label, value, min, max, step, update, description) => field(label,
            el('input', {type:'number', value, min, max, step, onchange: e => update(e.target.valueAsNumber)}), description);
        const parameters = (label, key, value, min, max, step, description) =>
            numeric(label, this.settings[key] ?? value, min, max, step, number => {this.settings[key] = number;}, description);
        const is2D = coordinateMode(this.mode) === 2;
        const objective = this.objectives[this.mode] ?? 'reconstruction';
        const completion = this.mode === 'completion' || this.mode === 'mix' || objective === 'completion';
        const goal = is2D ? field('Guide behavior', el('select', {onchange: e => {
            this.objectives[this.mode] = e.target.value;
            this.settings.iterations = undefined;
            this.settings.rate = undefined;
            this.render();
        }}, el('option', {value:'reconstruction', selected:objective === 'reconstruction'}, 'Match the whole guide'),
            el('option', {value:'completion', selected:objective === 'completion'}, 'Fill missing areas')),
        objective === 'completion' ? 'Erase the area you want the model to invent. Keep the parts you want it to follow.'
            : 'Use this when your guide describes the whole design.') : null;
        const keyboard = hint('Drag on the guide, or use arrow keys to position the brush and Enter to apply it. Shift plus an arrow moves nearby points with the Move tool.');
        keyboard.id = 'garment-edit-keys-' + this.id;
        const count = el('p', {class:'muted', role:'status'}, this.guide.length.toLocaleString() + ' guide points');
        const tools = ['paint', 'erase', 'move'].map(name => button(name[0].toUpperCase() + name.slice(1), event => {
            this.tool = name;
            tools.forEach((control, i) => control.setAttribute('aria-pressed', String(['paint','erase','move'][i] === name)));
        }, {'aria-pressed': String(this.tool === name)}));
        this.undo = button('Undo', () => {this.guide = this.history.pop();this.render();}, {disabled: !this.history.length});
        const browse = el('details', {}, el('summary', {}, 'Advanced guidance'),
            parameters('Follow edit', 'strength', .7, .1, .95, .05, 'Higher values follow the guide for more of the generation.'),
            parameters('Guidance steps', 'steps', 100, 20, 1000, 10, 'More steps take longer.'),
            parameters('Output drape points', 'points', edit.run.config.points, 100, 8192, 1),
            parameters('Edit passes per step', 'iterations', completion ? 8 : 2, 1, 10, 1),
            parameters('Learning rate', 'rate', completion ? .015 : .05, .005, .1, .005));
        const editable = this.mode !== 'blend';
        const viewable = this.mode !== 'pattern' && editable;
        const pointView = coordinateMode(this.mode) === 3;
        const view = viewable ? el('div', {class:'garment-edit-pair'},
            ...[['Horizontal view', 'azimuth', -180, 180],['Vertical view', 'elevation', -85, 85]].map(([label, key, low, high]) =>
                numeric(label, this.view[key], low, high, 5, value => {
                    const angle = Math.max(low, Math.min(high, value || 0));
                    if (pointView) {
                        this.view[key] = angle;
                        this.render();
                    } else {
                        this.changeDraft(() => {this.view[key] = angle;});
                    }
                }))) : null;
        const versions = (edit.run.versions || []).filter(item => item.id !== this.id);
        const designs = this.mixSources ?? [];
        const option = (item, label) => el('option', {value:item.id, selected:item.id === this.regions.other}, label);
        const other = el('select', {onchange:e=>{this.regions.other=e.target.value;}},
            el('option', {value:''}, 'Choose another garment or revision'),
            versions.length ? el('optgroup', {label:'This design'}, versions.map(item =>
                option(item, operationName(item.edit) + ' · seed ' + item.seed))) : null,
            designs.length ? el('optgroup', {label:'Recent garment designs'}, designs.map(item =>
                option(item, item.name + ' · seed ' + item.seed))) : null);
        const region = key => el('select', {onchange:e=>{this.regions[key]=e.target.value;}},
            el('option', {value:'upper', selected:this.regions[key] === 'upper'}, 'Upper half'),
            el('option', {value:'lower', selected:this.regions[key] === 'lower'}, 'Lower half'));
        const keep = region('keep'), take = region('take');
        const mix = this.mode === 'mix' ? el('div', {class:'garment-edit-mix'}, field('Second garment', other),
            el('div', {class:'garment-edit-pair'}, field('Keep from current', keep), field('Take from second', take)),
            button('Combine regions', () => this.mix(other.value, keep.value, take.value).catch(error => {
                this.error = error.message;this.render();
            })), !versions.length && !designs.length ? hint('Create another garment or save a revision to mix parts.') : null) : null;
        const canvas = editable ? editCanvas({points:this.guide, dimensions:coordinateMode(this.mode), ...this.view,
            center:this.center, tool:()=>this.tool, radius:()=>this.brush, history:points=>this.push(points), keyboard,
            update: points=>{this.guide=points;count.textContent=points.length.toLocaleString()+' guide points';}}) : null;
        const blend = !editable ? el('div', {class:'garment-edit-pair'},
            parameters('Second seed', 'second_seed', 43, 0, 2147483647, 1),
            parameters('Second point count', 'second_points', edit.run.config.points, 100, 8192, 1),
            parameters('Blend toward second seed', 'blend', .5, 0, 1, .05, '0 is the first seed. 1 is the second.')) : null;
        const payload = () => {
            const operation = this.mode;
            if (!editable) return {operation, second_seed:this.settings.second_seed, second_points:this.settings.second_points, blend:this.settings.blend};
            return {operation, guide:this.guide.map(p => p.map(x => Math.round(x*1000)/1000)),
                ...this.view, center:this.center, objective, strength:this.settings.strength, steps:this.settings.steps,
                rate:this.settings.rate ?? (completion ? .015 : .05), iterations:this.settings.iterations ?? (completion ? 8 : 2)};
        };
        this.element.replaceChildren(...[field('Edit mode', mode, operations[this.mode][1]), goal, view, mix,
            editable ? el('div', {class:'actions garment-edit-tools'}, ...tools, this.undo,
                button('Reset guide', () => this.reset())) : null,
            canvas, editable ? field('Brush size', el('input', {type:'range', min:5, max:42, value:this.brush,
                oninput:e=>{this.brush=e.target.valueAsNumber;}})) : null,
            editable ? count : null, editable ? keyboard : null, blend,
            field('Optional description', el('textarea', {rows:2, maxLength:500, value:this.prompt,
                oninput:e=>{this.prompt=e.target.value;}}), 'Describe what to keep or change.'),
            editable ? browse : null, this.error ? el('p', {role:'alert'}, this.error) : null,
            button('Apply edit and save a version', () => edit.applyEdit(payload(), this.prompt, this.settings.points), {class:'primary'})].filter(Boolean));
    }
}

