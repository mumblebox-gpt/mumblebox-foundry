import {appendContent, bindAttribute, isMessage, msg} from "./i18n.js";
export function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value === undefined || value === null) continue;
        if (isMessage(value)) {
            bindAttribute(node, key, value);
            if (key === "aria-label") node.dataset.i18nControl = value.key;
        }
        else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
        else if (key === "class") node.className = value;
        else if (key in node) node[key] = value;
        else node.setAttribute(key, value);
    }
    appendContent(node, ...children);
    return node;
}
export const button = (label, action, attrs = {}) => el("button", {type:"button", onclick:action, ...attrs}, label);
export const link = (label, href) => el("a", {href, target:"_blank", rel:"noopener noreferrer"}, label);
export const hint = text => el("p", {class:"muted"}, text);
export const field = (label, control, description) => el("label", {class:"field"}, el("span", {}, label), control, description ? hint(description) : null);
export const bytes = value => Number.isFinite(value) ? (value / 1024 ** 3).toFixed(1) + " GB" : msg("common.unavailable");

const paths = {
    globe:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3c5 5 5 13 0 18M12 3c-5 5-5 13 0 18',
    glasses:'M3 12l2-6h2M21 12l-2-6h-2M10 13h4M10 14a4 4 0 1 1-8 0 4 4 0 0 1 8 0m12 0a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
    chevron:'m6 9 6 6 6-6',
    check:'m5 12 4 4 10-10',
    refresh:'M20 7V3l-3 3a8 8 0 1 0 3 6M20 3h-5',
    trash:'M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7',
    plug:'M8 3v5m8-5v5M6 8h12v4a6 6 0 0 1-6 6v4M6 8v4a6 6 0 0 0 6 6',
    info:'M12 11v6m0-10h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
    map:'M4 3v18m0-16h15l-3 5 3 5H4',
    cube:"M12 3 3 8v9l9 5 9-5V8l-9-5ZM3 8l9 5 9-5M12 13v9",
    arrow:"M4 12h16m-6-6 6 6-6 6",
    gear:"M10 2h4l.5 3 1.5.8 2.8-1.1 2 3.4-2.3 2 .1 1.9 2.4 2-2 3.5-2.9-1-1.6.9-.5 3.1h-4l-.5-3.1-1.6-.9-2.9 1-2-3.5 2.4-2 .1-1.9-2.3-2 2-3.4 2.8 1.1L9.5 5 10 2ZM12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z",
    image:"M3 3h18v18H3zM3 17l6-6 5 5 3-3 4 4M16 7h.01",
    video:'M3 5h18v14H3zM10 9l5 3-5 3z',
    history:"M3 10a9 9 0 1 1 1 7M3 3v7h7M12 7v5l3 2",
    download:"M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
    sun:"M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2",
    contrast:"M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z",
};
export function icon(name, size=24) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    for (const [k,v] of Object.entries({viewBox:"0 0 24 24",width:size,height:size,fill:"none",stroke:"currentColor","stroke-width":1.5,"stroke-linecap":"round","stroke-linejoin":"round","aria-hidden":"true"})) svg.setAttribute(k,v);
    svg.classList.add("ui-icon");
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", paths[name] || paths.cube); svg.append(path);
    if(name==="contrast") {
        const half=document.createElementNS(svg.namespaceURI,"path");
        half.setAttribute("d","M12 3a9 9 0 0 1 0 18Z");half.setAttribute("fill","currentColor");svg.append(half);
    }
    return svg;
}
