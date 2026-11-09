import {app} from '/scripts/app.js';
import {appMode, presentation} from '../app-mode.js';

const title = 'CCORE / Create a Prop from Text';
const type = 'FoundryCCOREProp';

export function syncPropGraph(owner, options = {}) {
    if (owner.graph !== app.graph) throw Error('Open the Foundry graph before generating a CCORE prop.');
    const graph = app.graph;
    graph.beforeChange();
    try {
        let node = graph._nodes.find(item => item.type === type && item.properties?.ccoreOwner === owner.id);
        if (!node) {
            node = LiteGraph.createNode(type);
            if (!node) throw Error('The CCORE node is missing. Restart the local Foundry installation.');
            node.properties.ccoreOwner = owner.id;
            const right = Math.max(0, ...graph._nodes.map(item => item.pos[0] + item.size[0]));
            node.pos = [right + 600, 160];
            node.size = [425, 295];
            node.title = 'CCORE · Generate and export prop';
            node.mode = 2; // Foundry queues the selected workflow independently.
            graph.add(node);
            const group = new LiteGraph.LGraphGroup(title);
            group.pos = [node.pos[0] - 30, node.pos[1] - 65];
            group.size = [485, 400];
            group.color = '#617658';
            graph.add(group);
        }
        for (const key of ['name', 'prompt', 'seed', 'max_tokens']) {
            if (!(key in options)) continue;
            const widget = node.widgets?.find(item => item.name === key);
            if (widget) widget.value = options[key];
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

export function showPropGraph(owner) {
    const node = syncPropGraph(owner, owner.properties.foundryCcore?.draft);
    if (appMode) presentation.graph();
    app.canvas.animateToBounds([node.pos[0] - 35, node.pos[1] - 65, 500, 410], {duration: 180, zoom: .8});
}
