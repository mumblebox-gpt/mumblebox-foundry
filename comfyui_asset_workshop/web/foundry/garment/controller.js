import {sourceMessage} from "../i18n.js";
import {msg, setText, replaceContent} from "../i18n.js";
import {api} from '/scripts/api.js';
import {elapsedTime, workingStar} from '../activity.js';
import {el, button, field, hint, link} from '../dom.js';
import {capturePhoto, inputURL, uploadReference} from '../images/references.js';
import {request} from '../services.js';
import {mountMesh} from '../wizard/preview.js';
import {syncGarmentGraph} from './graph.js';
import {GarmentEditor, operationName} from './editor.js';

const titles = [msg("garment.start_your_garment"), msg("garment.edit_compare"), msg("garment.prepare_for_blender"), msg("garment.preview_on_a_character"), msg("garment.export_your_garment")];
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
                throw Error(msg("garment.resume_or_stop_the_running_garment_before_starting_another"));
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
            if (!run.result) throw Error(msg("garment.choose_a_completed_garment_version"));
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
                    if (this.phase) setText(this.phase, sourceMessage(this.run.phase));
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
            this.draft[key] ? el('img', {src: inputURL(this.draft[key]), alt: back ? msg("garment.back_garment_reference") : msg("garment.front_garment_reference"), class: 'webcam-preview'}) : null,
            el('div', {class: 'actions'},
                button(back ? msg("garment.upload_back_reference") : msg("garment.upload_front_reference"), () => picker.click(), {disabled: this.pending}),
                this.draft.mode === 'image' && navigator.mediaDevices
                    ? button(msg("garment.take_a_photo"), () => capturePhoto(this.shell, add), {disabled: this.pending}) : null,
                this.draft[key] ? button(msg("garment.remove_reference"), () => {this.update(key, '');this.render();}) : null),
            hint(msg("garment.drop_one_png_jpeg_or_webp_here"))));
    }

    number(key, low, high, edit = value => this.update(key, value)) {
        return el('input', {type: 'number', value: this.draft[key], min: low, max: high, step: 1,
            onchange: e => edit(e.target.valueAsNumber)});
    }

    generationSettings() {
        const presets = Object.entries(this.generationPresets);
        const preset = el('select', {},
            presets.map(([value, {label, points, steps}]) => el('option', {value},
                msg("garment.points_steps", {label: label, value2: points.toLocaleString(), steps: steps}))),
            el('option', {value: 'custom'}, msg("garment.custom")));
        const match = presets.find(([, {points, steps}]) => points === this.draft.points && steps === this.draft.steps);
        preset.value = this.customGeneration ? 'custom' : match?.[0] ?? 'custom';
        const customize = (key, value) => {
            this.customGeneration = true;
            preset.value = 'custom';
            this.update(key, value);
        };
        const points = this.number('points', 100, 8192, value => customize('points', value));
        const steps = this.number('steps', 2, 250, value => customize('steps', value));
        const advanced = el('details', {open: preset.value === 'custom'}, el('summary', {}, msg("garment.advanced")),
            field(msg("garment.seed"), this.number('seed', 0, 2147483647), msg("garment.change_it_for_another_design_from_the_same_input")),
            field(msg("garment.drape_points"), points, msg("garment.more_points_use_more_gpu_memory")),
            field(msg("garment.sampling_steps"), steps, msg("garment.more_steps_take_longer")));
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
        return [field(msg("garment.generation_preset"), preset,
            msg("garment.use_balanced_to_start_choose_custom_to_set_your_own_point_count_and_steps")), advanced];
    }

    describe() {
        const mode = this.draft.mode;
        return [
            hint(msg("garment.design_clothing_from_a_description_image_or_sketch_edit_the_sewing_pattern_o")),
            field(msg("garment.garment_name"), el('input', {value: this.draft.name, maxLength: 80, oninput: e => this.update('name', e.target.value)})),
            el('fieldset', {class: 'ccore-precision', disabled: this.pending}, el('legend', {}, msg("garment.starting_point")),
                Object.entries(modes).map(([value, [label, detail]]) => el('label', {class: 'check-row'},
                    el('input', {type: 'radio', name: 'garment-mode', value, checked: value === mode,
                        onchange: () => {this.update('mode', value);this.render();}}),
                    el('span', {}, el('strong', {}, label), el('small', {class: 'muted'}, detail))))),
            mode === 'text' ? field(msg("garment.description"), el('textarea', {rows: 4, maxLength: 500, value: this.draft.prompt,
                placeholder: this.capabilities.example, oninput: e => this.update('prompt', e.target.value)})) : null,
            ['image','sketch'].includes(mode) ? [this.reference(), el('details', {open:Boolean(this.draft.back_image)},
                el('summary', {}, msg("garment.add_a_matching_back_view")), hint(msg("garment.use_the_back_of_the_same_garment_framed_like_the_front")),
                this.reference('back_image'))] : null,
            mode === 'text' ? button(msg("garment.try_the_waistcoat_example"), () => {
                this.update('prompt', this.capabilities.example);this.render();
            }) : null,
            ...this.generationSettings(),
            this.capabilities.modes[mode] ? el('p', {role: 'alert'}, this.capabilities.modes[mode]) :
                hint(msg("garment.the_generator_and_sewing_pattern_model_take_turns_using_the_gpu_keep_enough")),
        ];
    }

    busy() {
        this.phase = el('strong', {}, sourceMessage(this.run.phase));
        return el('div', {class: 'activity-feedback', 'data-busy': 'true', role: 'status'}, workingStar(),
            el('div', {}, sourceMessage(this.phase), elapsedTime(this.run.started_at * 1000)),
            button(msg("garment.stop_this_stage"), () => this.stage('cancel'), {disabled: this.pending}));
    }

    preview(filename, label, id = this.id) {
        const host = el('div', {class: 'wizard-mesh', 'aria-label': label});
        const status = hint(msg("garment.loading_3d_preview"));
        const revision = this.revision;
        requestAnimationFrame(async () => {
            if (this.disposed || revision !== this.revision) return;
            try {
                const dispose = await mountMesh(host, url(id, filename), this.capabilities.viewer_module, filename);
                if (this.disposed || revision !== this.revision) {dispose();return;}
                this.viewers.push(dispose);
                host.dataset.loaded = 'true';
                setText(status, msg("garment.drag_to_rotate_scroll_to_zoom"));
            } catch (error) { setText(status, sourceMessage(error.message)); }
        });
        return el('section', {}, el('h3', {}, label), host, status);
    }

    review() {
        if (!this.run?.result) return [hint(msg("garment.your_3d_drape_and_sewing_sheet_will_appear_here"))];
        const {panels, stitches, points} = this.run.result;
        const versions = this.run.versions || [];
        const version = el('select', {onchange: e => this.selectVersion(e.target.value)},
            versions.map((item, index) => el('option', {value:item.id, selected:item.id === this.id},
                msg("garment.seed_2", {value1: index + 1, value2: operationName(item.edit), seed: item.seed}))));
        const previous = this.run.parent;
        const pattern = (id, label) => el('img', {src: url(id, 'garment_pattern.png'), alt: label, class: 'garment-pattern-sheet'});
        const workspace = this.showEditor && this.editor?.source && this.editor.id === this.id ? this.editor.element : null;
        const compare = previous && this.compare;
        const visuals = compare ? el('div', {class:'garment-review-grid'},
            el('section', {}, this.preview('drape-particles.glb', 'Before this edit', previous), pattern(previous, msg("garment.previous_sewing_pattern"))),
            el('section', {}, this.preview('drape-particles.glb', 'Current version'), pattern(this.id, msg("garment.current_sewing_pattern"))))
            : el('div', {class:'garment-review-grid'},
                this.preview('drape-particles.glb', '3D particle drape'),
                el('section', {}, el('h3', {}, msg("garment.sewing_pattern")), pattern(this.id, msg("garment.labeled_sewing_panels_and_stitching"))));
        return [
            hint(msg("garment.use_the_editing_tools_to_paint_changes_to_a_pattern_silhouette_or_3d_guide_e")),
            hint(msg("garment.panels_stitches_drape_points", {panels: panels, stitches: stitches, value3: points.toLocaleString()})),
            versions.length > 1 ? field(msg("garment.saved_version"), version, msg("garment.choose_the_version_you_want_to_edit_drape_or_export")) : null,
            el('div', {class:'actions'},
                button(workspace ? msg("garment.close_edit_tools") : msg("garment.open_edit_tools"), () => {
                    if (workspace) {this.showEditor = false;this.render();return;}
                    this.act(async () => {
                        this.editor ??= new GarmentEditor(this);
                        await this.editor.attach(this.id, this.run.config.prompt, this.run.config.seed);
                        this.showEditor = true;
                    });
                }, {disabled:this.pending, 'aria-expanded':String(Boolean(workspace))}),
                previous ? button(compare ? msg("garment.show_current_only") : msg("garment.compare_with_previous"), () => {this.compare = !this.compare;this.render();},
                    {'aria-pressed':String(Boolean(compare))}) : null),
            workspace ? el('div', {class:'garment-workbench'}, workspace, visuals) : visuals,
            el('details', {}, el('summary', {}, msg("garment.3d_panel_placement_sheet")),
                el('img', {src: url(this.id, 'garment_3d_pattern.png'), alt: msg("garment.author_panel_placement_sheet"), class: 'garment-pattern-sheet'})),
        ];
    }

    prepare() {
        const budget = el('input', {type:'number', value:this.budget, min:2000, max:100000, step:1000,
            onchange:e=>{this.budget=e.target.valueAsNumber;this.remember();}});
        const mesh = this.run.mesh;
        return [
            hint(msg("garment.build_a_uv_mapped_mesh_from_the_sewing_panels_the_export_includes_this_mesh")),
            field(msg("garment.triangle_limit"), budget),
            el('div', {class:'actions'},
                button(mesh ? msg("garment.rebuild_sewn_mesh") : msg("garment.build_sewn_mesh"), () => this.stage('sew', {budget:this.budget}),
                    {class:mesh ? 'quiet' : 'primary', disabled:this.pending})),
            mesh ? hint(msg("garment.triangles_pattern_uvs_and_fabric_atlas_included", {value1: mesh.triangles.toLocaleString()})) : null,
            mesh ? el('section', {class:'garment-drape-controls'},
                el('h3', {}, msg("garment.optional_character_preview")),
                hint(msg("garment.try_a_rough_rest_pose_cloth_simulation_on_a_rigged_character_use_it_to_spot")),
                button(this.run.drape || this.run.rig ? msg("garment.review_saved_character_preview") : msg("garment.preview_on_a_character"),
                    () => this.go(3), {disabled:this.pending})) : el('details', {}, el('summary', {}, msg("garment.pattern_only_export")),
                button(msg("garment.export_pattern_and_drape_only"), () => this.go(4), {disabled:this.pending})),
        ];
    }

    fitControls() {
        const body = el('input', {type:'file', accept:'.glb'});
        const update = (key, value) => {this.fit = {...this.fit, [key]:value};};
        const number = (label, key, initial, min, max, step) => field(label, el('input', {
            type:'number', value:this.fit?.[key] ?? initial, min, max, step,
            onchange:e=>update(key,e.target.valueAsNumber)}));
        const fabric = el('select', {onchange:e=>update('fabric',e.target.value)},
            [['light',msg("garment.light_soft_flowing_cloth")], ['medium',msg("garment.medium_everyday_fabric")], ['heavy',msg("garment.heavy_more_structure")]]
                .map(([value,label]) => el('option', {value, selected:value === (this.fit?.fabric || 'medium')}, label)));
        return el('section', {class:'garment-drape-controls'},
            field(msg("garment.rigged_character_glb"), body, this.fit?.characterName ? 'Current target · ' + this.fit.characterName
                : this.fit?.character ? msg("garment.using_the_character_from_the_saved_drape") : msg("garment.use_a_closed_skin_weighted_body_in_its_rest_pose")),
            field(msg("garment.fabric"), fabric, msg("garment.changes_how_the_material_bends_and_settles")),
            el('details', {}, el('summary', {}, msg("garment.placement_and_simulation_settings")),
                el('div', {class:'garment-edit-pair'},
                    number(msg("garment.uniform_scale"), 'scale', 1, .05, 10, .01),
                    number(msg("garment.side_offset_m"), 'x', 0, -5, 5, .01),
                    number(msg("garment.depth_offset_m"), 'y', 0, -5, 5, .01),
                    number(msg("garment.height_offset_m"), 'z', 0, -5, 5, .01),
                    number(msg("garment.clearance_mm"), 'clearance', 4, 0, 30, 1),
                    number(msg("garment.settling_frames"), 'frames', 48, 16, 120, 1))),
            button(this.run.drape ? msg("garment.run_another_preview") : msg("garment.run_cloth_preview"), () => this.act(async () => {
                const file = body.files[0];
                if (file) {
                    if (!/\.glb$/i.test(file.name) || file.size > 150 * 1024 ** 2) {
                        throw Error(msg("garment.choose_one_rigged_glb_smaller_than_150_mb"));
                    }
                    const response = await fetch('/mumblebox-foundry/v1/' + base(this.id) + '/character', {
                        method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file});
                    const data = await response.json();
                    if (!response.ok) throw Error(data.error || 'The character could not be uploaded.');
                    this.fit = {...this.fit, character:data.character, characterName:file.name};
                }
                if (!this.fit?.character) throw Error(msg("garment.choose_a_rigged_character_glb_before_draping"));
                this.run = await request(base(this.id) + '/drape', {...this.fit, client_id:api.clientId});
                this.approved = null;
                this.fitView = 'draped-fit.glb';
                if (this.run.active) this.poll();
            }), {class:'primary', disabled:this.pending}));
    }

    reviewFit() {
        const {drape, rig} = this.run;
        const purpose = hint(msg("garment.this_is_a_rough_rest_pose_preview_check_for_loose_areas_folds_and_clipping_u"));
        if (!drape) return rig
            ? [purpose, hint(msg("garment.this_saved_wearable_was_produced_with_the_earlier_fit_workflow")),
                this.preview('wearable.glb', 'Saved wearable'), this.fitControls()]
            : [purpose, this.fitControls()];
        const files = {'draped-fit.glb':'Settled with body and clipping', 'starting-fit.glb':'Before simulation',
            'draped-garment.glb':'Settled garment only', ...(rig ? {'wearable.glb':'Skinned wearable'} : {})};
        const shown = Object.hasOwn(files, this.fitView) ? this.fitView : 'draped-fit.glb';
        const selector = el('select', {onchange:e=>{this.fitView=e.target.value;this.render();}},
            Object.entries(files).map(([value,label])=>el('option', {value, selected:value === shown}, label)));
        const accept = button(msg("garment.transfer_test_skin_weights"), () => this.stage('fit', {approve:drape.drape_id}),
            {disabled:this.pending || this.approved !== drape.drape_id});
        const review = el('label', {class:'check-row'},
            el('input', {type:'checkbox', checked:this.approved === drape.drape_id, onchange:e=>{
                this.approved = e.target.checked ? drape.drape_id : null;
                accept.disabled = this.approved !== drape.drape_id;
            }}), el('span', {}, msg("garment.i_checked_the_drape_for_loose_areas_and_clipping")));
        return [
            purpose,
            hint(msg("garment.blender_cloth_fabric_settling_frames", {fabric: drape.fabric, frames: drape.frames})),
            el('p', {role:'status'}, msg("garment.rest_pose_clipping_went_from_to_vertices_deepest_remaining_mark_mm", {value1: drape.before.vertices.toLocaleString(), value2: drape.after.vertices.toLocaleString(), value3: drape.after.depth_mm})),
            field(msg("garment.preview"), selector, msg("garment.red_marks_show_vertices_inside_the_body_also_look_for_gaps_where_the_fabric")),
            this.preview(shown, files[shown]),
            el('details', {}, el('summary', {}, msg("garment.adjust_preview_settings")), this.fitControls()),
            rig ? hint(msg("garment.test_skin_weights_saved_sampled_poses", {value1: rig.pose_checks.map(pose => pose.name + ' ' + pose.penetrating + ' clipping').join(' · ')}))
                : el('details', {}, el('summary', {}, msg("garment.experimental_skin_transfer")),
                    hint(msg("garment.transfer_weights_from_this_character_as_a_starting_point_refine_the_result_a")), review, accept),
        ];
    }


    downloads() {
        const dl = (title, file) => el('a', {class: 'download-link', href: url(this.id, file, true)}, title);
        return [
            hint(this.run.mesh
                ? msg("garment.import_the_sewn_glb_into_blender_as_your_starting_mesh_use_the_sewing_patter")
                : msg("garment.this_export_contains_the_editable_pattern_and_3d_point_drape_go_back_to_buil")),
            el('div', {class: 'actions'}, dl('Editable pattern (JSON)', 'garment_specification.json'),
                dl('Sewing sheet (SVG)', 'garment_pattern.svg'), dl('3D drape reference (PLY)', 'drape-particles.ply'),
                this.run.mesh ? dl('Sewn mesh (GLB)', 'sewn-garment.glb') : null,
                this.run.archive ? dl('Download ZIP', 'archive') : null),
            this.run.drape || this.run.rig ? el('details', {}, el('summary', {}, msg("garment.optional_character_preview_files")),
                hint(msg("garment.these_files_are_a_fit_and_rigging_starting_point_review_loose_areas_and_clip")),
                el('div', {class:'actions'},
                    this.run.drape ? dl('Settled GLB', 'draped-garment.glb') : null,
                    this.run.drape ? dl('Drape report', 'drape-report.json') : null,
                    this.run.rig ? dl('Test skin GLB', 'wearable.glb') : null,
                    this.run.rig ? dl('Test skin FBX', 'wearable.fbx') : null,
                    this.run.rig ? dl('Fit report', 'fit-report.json') : null)) : null,
            this.run.archive ? hint(msg("garment.saved_in_foundry_history")) : null,
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
            this.generate = button(this.pending ? msg("garment.preparing") : msg("garment.generate_garment"), () => this.start(),
                {class: 'primary', disabled: !this.canGenerate()});
            actions.push(this.generate);
        } else if (!running) {
            actions.push(button(this.page === 1 ? msg("garment.edit_starting_point") : msg("garment.back"), () => this.go(this.page === 4 ? this.downloadFrom ?? 2 : this.page - 1), {disabled: this.pending}));
            if (this.page === 1 && this.run.result) actions.push(button(msg("garment.prepare_for_blender"), () => this.go(2), {class:'primary'}));
            if ((this.page === 2 || this.page === 3) && this.run.mesh) actions.push(button(msg("garment.continue_to_export"), () => this.go(4), {class:'primary', disabled:this.pending}));
            if (this.page === 4 && !this.run.archive) actions.push(button(msg("garment.save_zip_to_history"), () => this.stage('package'),
                {class: 'primary', disabled: this.pending}));
        }
        actions.push(button(msg("garment.choose_a_workflow"), () => this.shell.open('Choose a Workflow'), {class: 'quiet'}));
        const content = running ? [this.busy()] : this[pages[this.page]]();
        replaceContent(this.element, el('aside', {class: 'wizard-rail'}, el('span', {class: 'eyebrow'}, msg("garment.garment_particles_clothing")),
                el('h3', {}, msg("garment.create_clothing")),
                el('ol', {class: 'wizard-steps'}, mainSteps.map((page, index) => el('li', {
                    class: page === (this.page === 3 ? 2 : this.page) ? 'current' : '',
                    'aria-current': page === (this.page === 3 ? 2 : this.page) ? 'step' : null,
                }, el('span', {class: 'step-number'}, String(index + 1)), el('strong', {}, titles[page])))),
                el('div', {class: 'wizard-rail-note'}, link(msg("garment.garment_particles_by_kiyohiro_nakayama_and_collaborators"), this.capabilities.source))), el('section', {class: 'wizard-panel'},
                el('header', {class: 'page-head'}, el('span', {class: 'eyebrow'},
                    this.page === 3 ? msg("garment.optional_preview") : msg("garment.step_of", {value1: mainSteps.indexOf(this.page) + 1, value2: mainSteps.length})),
                    el('h2', {tabIndex: -1}, titles[this.page])),
                this.page === 0 ? el('div', {class: 'note-panel'},
                    el('strong', {}, msg("garment.experimental")),
                    hint(msg("garment.this_workflow_is_still_in_development_review_how_the_garment_fits_your_chara"))) : null,
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

