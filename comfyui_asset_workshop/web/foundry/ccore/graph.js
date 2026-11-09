import {app} from '/scripts/app.js';
import {appMode, presentation} from '../app-mode.js';

export const ccoreDraftKey = image => image ? 'foundryCcoreImage' : 'foundryCcore';
export const ccoreTitle = image => image ? 'Create a Prop from Image + Text' : 'Create a Prop from Text';
const type = 'FoundryCCOREProp';

export function syncPropGraph(owner, options = {}, image = false) {
    if (owner.graph !== app.graph) throw Error('Open the Foundry graph before generating a CCORE prop.');
    const graph = app.graph;
    graph.beforeChange();
    try {
        let node = graph._nodes.find(item => item.type === type && item.properties?.ccoreOwner === owner.id && Boolean(item.properties.ccoreImage) === image);
        if (!node) {
            node = LiteGraph.createNode(type);
            if (!node) throw Error('The CCORE node is missing. Restart the local Foundry installation.');
            node.properties.ccoreOwner = owner.id;
            if (image) node.properties.ccoreImage = true;
            const right = Math.max(0, ...graph._nodes.map(item => item.pos[0] + item.size[0]));
            node.pos = [right + 600, 160];
            node.size = [425, 345];
            node.title = image ? 'CCORE · Generate from image and text' : 'CCORE · Generate and export prop';
            node.mode = 2; // Foundry queues the selected workflow independently.
            graph.add(node);
            const group = new LiteGraph.LGraphGroup('CCORE / ' + ccoreTitle(image));
            group.pos = [node.pos[0] - 30, node.pos[1] - 65];
            group.size = [485, 440];
            group.color = '#617658';
            graph.add(group);
        }
        const values = {...options, mode: image ? 'image_text' : 'text', image: image ? options.image || '' : ''};
        for (const key of ['name', 'prompt', 'seed', 'max_tokens', 'model_variant', 'mode', 'image']) {
            if (!(key in values)) continue;
            const widget = node.widgets?.find(item => item.name === key);
            if (widget) widget.value = values[key];
        }
        const seedMode = node.widgets?.find(widget => widget.name === 'control_after_generate');
        if (seedMode) seedMode.value = 'fixed';
        graph.change?.();
        graph.setDirtyCanvas(true, true);
        return node;
    } finally {
        graph.afterChange();
    }
}

export function showPropGraph(owner, image = false) {
    const node = syncPropGraph(owner, owner.properties[ccoreDraftKey(image)]?.draft, image);
    if (appMode) presentation.graph();
    app.canvas.animateToBounds([node.pos[0] - 35, node.pos[1] - 65, 500, 410], {duration: 180, zoom: .8});
}
