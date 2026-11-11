import {msg, setText, replaceContent} from "../i18n.js";
import {el, button, field, hint} from '../dom.js';
import {request} from '../services.js';
import {centerOf, editCanvas, projectGuide} from './edit-canvas.js';

const operations = {
    pattern: [msg("garment.sewing_pattern"), msg("garment.paint_or_erase_areas_on_the_flat_pattern_the_model_will_rebuild_the_garment")],
    silhouette: [msg("garment.silhouette"), msg("garment.set_a_view_and_brush_the_outline_you_want_the_garment_to_follow")],
    shape: [msg("garment.3d_points"), msg("garment.add_move_or_erase_points_change_the_view_to_work_around_the_garment")],
    completion: [msg("garment.complete_a_partial_garment"), msg("garment.erase_the_areas_you_want_the_model_to_fill_the_points_you_keep_guide_the_new")],
    mix: [msg("garment.mix_parts_from_two_garments"), msg("garment.keep_a_region_of_this_design_and_add_a_region_from_another_design_or_revisio")],
    blend: [msg("garment.blend_two_seeds"), msg("garment.explore_a_garment_between_two_noise_seeds_using_the_same_description_use_dif")],
};
export const operationName = operation => operations[operation]?.[0] || msg("garment.original_generation");
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
        const goal = is2D ? field(msg("garment.guide_behavior"), el('select', {onchange: e => {
            this.objectives[this.mode] = e.target.value;
            this.settings.iterations = undefined;
            this.settings.rate = undefined;
            this.render();
        }}, el('option', {value:'reconstruction', selected:objective === 'reconstruction'}, msg("garment.match_the_whole_guide")),
            el('option', {value:'completion', selected:objective === 'completion'}, msg("garment.fill_missing_areas"))),
        objective === 'completion' ? msg("garment.erase_the_area_you_want_the_model_to_invent_keep_the_parts_you_want_it_to_fo")
            : msg("garment.use_this_when_your_guide_describes_the_whole_design")) : null;
        const keyboard = hint(msg("garment.drag_on_the_guide_or_use_arrow_keys_to_position_the_brush_and_enter_to_apply"));
        keyboard.id = 'garment-edit-keys-' + this.id;
        const count = el('p', {class:'muted', role:'status'}, msg("garment.guide_points", {value1: this.guide.length.toLocaleString()}));
        const tools = ['paint', 'erase', 'move'].map(name => button(msg("garment." + name), event => {
            this.tool = name;
            tools.forEach((control, i) => control.setAttribute('aria-pressed', String(['paint','erase','move'][i] === name)));
        }, {'aria-pressed': String(this.tool === name)}));
        this.undo = button(msg("garment.undo"), () => {this.guide = this.history.pop();this.render();}, {disabled: !this.history.length});
        const browse = el('details', {}, el('summary', {}, msg("garment.advanced_guidance")),
            parameters(msg("garment.follow_edit"), 'strength', .7, .1, .95, .05, msg("garment.higher_values_follow_the_guide_for_more_of_the_generation")),
            parameters(msg("garment.guidance_steps"), 'steps', 100, 20, 1000, 10, msg("garment.more_steps_take_longer")),
            parameters(msg("garment.output_drape_points"), 'points', edit.run.config.points, 100, 8192, 1),
            parameters(msg("garment.edit_passes_per_step"), 'iterations', completion ? 8 : 2, 1, 10, 1),
            parameters(msg("garment.learning_rate"), 'rate', completion ? .015 : .05, .005, .1, .005));
        const editable = this.mode !== 'blend';
        const viewable = this.mode !== 'pattern' && editable;
        const pointView = coordinateMode(this.mode) === 3;
        const view = viewable ? el('div', {class:'garment-edit-pair'},
            ...[[msg("garment.horizontal_view"), 'azimuth', -180, 180],[msg("garment.vertical_view"), 'elevation', -85, 85]].map(([label, key, low, high]) =>
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
            el('option', {value:''}, msg("garment.choose_another_garment_or_revision")),
            versions.length ? el('optgroup', {label:msg("garment.this_design")}, versions.map(item =>
                option(item, msg("garment.version_seed", {name:operationName(item.edit), seed:item.seed})))) : null,
            designs.length ? el('optgroup', {label:msg("garment.recent_garment_designs")}, designs.map(item =>
                option(item, msg("garment.version_seed", {name:item.name, seed:item.seed})))) : null);
        const region = key => el('select', {onchange:e=>{this.regions[key]=e.target.value;}},
            el('option', {value:'upper', selected:this.regions[key] === 'upper'}, msg("garment.upper_half")),
            el('option', {value:'lower', selected:this.regions[key] === 'lower'}, msg("garment.lower_half")));
        const keep = region('keep'), take = region('take');
        const mix = this.mode === 'mix' ? el('div', {class:'garment-edit-mix'}, field(msg("garment.second_garment"), other),
            el('div', {class:'garment-edit-pair'}, field(msg("garment.keep_from_current"), keep), field(msg("garment.take_from_second"), take)),
            button(msg("garment.combine_regions"), () => this.mix(other.value, keep.value, take.value).catch(error => {
                this.error = error.message;this.render();
            })), !versions.length && !designs.length ? hint(msg("garment.create_another_garment_or_save_a_revision_to_mix_parts")) : null) : null;
        const canvas = editable ? editCanvas({points:this.guide, dimensions:coordinateMode(this.mode), ...this.view,
            center:this.center, tool:()=>this.tool, radius:()=>this.brush, history:points=>this.push(points), keyboard,
            update: points=>{this.guide=points;setText(count, msg("garment.guide_points", {value1: points.length.toLocaleString()}));}}) : null;
        const blend = !editable ? el('div', {class:'garment-edit-pair'},
            parameters(msg("garment.second_seed"), 'second_seed', 43, 0, 2147483647, 1),
            parameters(msg("garment.second_point_count"), 'second_points', edit.run.config.points, 100, 8192, 1),
            parameters(msg("garment.blend_toward_second_seed"), 'blend', .5, 0, 1, .05, msg("garment.0_is_the_first_seed_1_is_the_second"))) : null;
        const payload = () => {
            const operation = this.mode;
            if (!editable) return {operation, second_seed:this.settings.second_seed, second_points:this.settings.second_points, blend:this.settings.blend};
            return {operation, guide:this.guide.map(p => p.map(x => Math.round(x*1000)/1000)),
                ...this.view, center:this.center, objective, strength:this.settings.strength, steps:this.settings.steps,
                rate:this.settings.rate ?? (completion ? .015 : .05), iterations:this.settings.iterations ?? (completion ? 8 : 2)};
        };
        replaceContent(this.element, ...[field(msg("garment.edit_mode"), mode, operations[this.mode][1]), goal, view, mix,
            editable ? el('div', {class:'actions garment-edit-tools'}, ...tools, this.undo,
                button(msg("garment.reset_guide"), () => this.reset())) : null,
            canvas, editable ? field(msg("garment.brush_size"), el('input', {type:'range', min:5, max:42, value:this.brush,
                oninput:e=>{this.brush=e.target.valueAsNumber;}})) : null,
            editable ? count : null, editable ? keyboard : null, blend,
            field(msg("garment.optional_description"), el('textarea', {rows:2, maxLength:500, value:this.prompt,
                oninput:e=>{this.prompt=e.target.value;}}), msg("garment.describe_what_to_keep_or_change")),
            editable ? browse : null, this.error ? el('p', {role:'alert'}, this.error) : null,
            button(msg("garment.apply_edit_and_save_a_version"), () => edit.applyEdit(payload(), this.prompt, this.settings.points), {class:'primary'})].filter(Boolean));
    }
}

