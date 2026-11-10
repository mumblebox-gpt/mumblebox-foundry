import {app} from '/scripts/app.js';
import {appMode, presentation} from '../app-mode.js';

const types = ['FoundryGarmentParticles', 'FoundryGarmentSewMesh', 'FoundryGarmentDrape', 'FoundryGarmentFit'];
const titles = ['Generate or edit a pattern', 'Sew and UV-map panels', 'Drape on character', 'Skin approved drape'];

export function syncGarmentGraph(owner, config = {}, budget = 20000) {
    const graph = app.graph;
    if (owner.graph !== graph) throw Error('Open the Foundry graph to use this garment workflow.');
    graph.beforeChange();
    try {
        const existing = types.map(type => graph._nodes.find(n => n.type === type && n.properties?.garmentOwner === owner.id));
        if (existing.every(Boolean)) {
            applySettings(existing, config, budget);
            return existing[0];
        }
        const nodes = types.map((type, index) => existing[index] || LiteGraph.createNode(type));
        if (nodes.some(node => !node)) throw Error('Reload ComfyUI to register the Garment Particles nodes.');
        const right = Math.max(0, ...graph._nodes.map(n => n.pos[0] + n.size[0])) + 440;
        const left = existing[0]?.pos[0] ?? right;
        nodes.forEach((node, index) => {
            if (existing[index]) return;
            node.title = 'Garment Particles · ' + titles[index];
            node.properties.garmentOwner = owner.id;
            node.pos = [left + index * 425, 180];
            node.size = [385, index === 0 ? 410 : 305];
            node.mode = 2; // The wizard submits only the selected garment stage.
            graph.add(node);
        });
        nodes[0].connect(0, nodes[1], nodes[1].findInputSlot('garment_run'));
        nodes[1].connect(0, nodes[2], nodes[2].findInputSlot('mesh_token'));
        nodes[2].connect(0, nodes[3], nodes[3].findInputSlot('mesh_token'));
        nodes[3].pos = [left + 3 * 425, 180];
        nodes[3].title = 'Garment Particles · ' + titles[3];
        nodes[0].title = 'Garment Particles · ' + titles[0];
        const present = graph._groups?.find(group => group.title === 'Garment Particles / Character clothing');
        if (present) present.size = [1715, 500];
        if (!present) {
            const group = new LiteGraph.LGraphGroup('Garment Particles / Character clothing');
            group.pos = [left - 25, 118];
            group.size = [1715, 500];
            group.color = '#617658';
            graph.add(group);
        }
        applySettings(nodes, config, budget);
        return nodes[0];
    } finally {
        graph.change?.();
        graph.setDirtyCanvas(true, true);
        graph.afterChange();
    }
}

function applySettings(nodes, config, budget) {
    const keys = ['name', 'mode', 'prompt', 'image', 'back_image', 'seed', 'points', 'steps'];
    for (const [node, values] of [[nodes[0], Object.fromEntries(keys.filter(key => key in config).map(key => [key, config[key]]))],
                                  [nodes[1], {budget}]]) {
        for (const [key, value] of Object.entries(values)) {
            const widget = node.widgets?.find(item => item.name === key);
            if (widget) widget.value = value;
        }
    }
}

export function showGarmentGraph(owner) {
    const saved = owner.properties.foundryGarment || {};
    const node = syncGarmentGraph(owner, saved.draft, saved.budget);
    if (appMode) presentation.graph();
    app.canvas.animateToBounds([node.pos[0] - 35, node.pos[1] - 65, 1745, 510], {duration: 180, zoom: .7});
}

