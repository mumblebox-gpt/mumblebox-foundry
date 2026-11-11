// One owner for Foundry language, message resolution and live text bindings.
let locale = "en";
import manifest from "./locales/manifest.json" with {type: "json"};

let catalogs = Object.fromEntries(manifest.languages.map(item => [item.id, {}]));
const manifestUrl = new URL("./locales/manifest.json", import.meta.url);
await Promise.all(manifest.languages.flatMap(language =>
    Object.entries(manifest.domains).map(async ([domain, directory]) => {
        const url = new URL(directory + "/" + language.id + ".json", manifestUrl);
        const {default: messages} = await import(url.href, {with: {type: "json"}});
        for (const [key, value] of Object.entries(messages)) catalogs[language.id][domain + "." + key] = value;
    })
));
const bindings = new Set();
const textBindings = new WeakMap();
const attributeBindings = new WeakMap();
const listeners = new Set();
const marker = Symbol("foundry-message");
const parameters = /\{([A-Za-z][A-Za-z0-9_]*)\}/g;

export const languages = manifest.languages;

export function configureCatalogs(data) {
    catalogs = data;
    sourceIndex = undefined;
}

export function currentLanguage() {
    return locale;
}

export function t(key, values = {}) {
    const source = catalogs[locale]?.[key] ?? catalogs.en?.[key] ?? key;
    return source.replace(parameters, (whole, name) => {
        if (!Object.hasOwn(values, name)) throw Error("Missing translation parameter " + name + " for " + key);
        const value = values[name];
        return String(isMessage(value) ? value : value ?? "");
    });
}

export function msg(key, values = {}) {
    return {
        [marker]: true, key, values,
        toString() { return t(key, values); },
        toJSON() { return catalogs.en?.[key]?.replace(parameters, (_, name) => String(isMessage(values[name]) ? values[name].toJSON() : values[name] ?? "")) ?? key; },
    };
}

export function isMessage(value) {
    return Boolean(value?.[marker]);
}

function update(binding) {
    const node = binding.node.deref();
    if (!node) {
        bindings.delete(binding);
        return;
    }
    if (binding.attribute) node.setAttribute(binding.attribute, String(binding.value));
    else node.data = String(binding.value);
}

export function bindAttribute(node, attribute, value) {
    const owned = attributeBindings.get(node) || new Map();
    const previous = owned.get(attribute);
    if (previous) bindings.delete(previous);
    node.setAttribute(attribute, String(value));
    if (isMessage(value)) {
        const binding = {node: new WeakRef(node), attribute, value};
        owned.set(attribute, binding);
        bindings.add(binding);
        attributeBindings.set(node, owned);
    } else {
        owned.delete(attribute);
    }
}

function bindText(node, value) {
    const previous = textBindings.get(node);
    if (previous) bindings.delete(previous);
    node.data = String(value);
    if (isMessage(value)) {
        const binding = {node: new WeakRef(node), value};
        bindings.add(binding);
        textBindings.set(node, binding);
    } else {
        textBindings.delete(node);
    }
    // Long-running progress updates may leave detached nodes awaiting GC.
    if (bindings.size % 256 === 0) {
        for (const binding of bindings) if (!binding.node.deref()) bindings.delete(binding);
    }
    return node;
}

export function textNode(value) {
    return bindText(document.createTextNode(""), value);
}

export function prependContent(node, ...values) {
    const fragment = document.createDocumentFragment();
    appendContent(fragment, ...values);
    node.prepend(fragment);
    return node;
}

export function appendContent(node, ...values) {
    for (const value of values.flat(Infinity)) {
        if (value === null || value === undefined) continue;
        node.append(value instanceof Node ? value : textNode(value));
    }
    return node;
}

export function replaceContent(node, ...values) {
    node.replaceChildren();
    return appendContent(node, ...values);
}

export function setText(node, value) {
    if (node.childNodes.length === 1 && node.firstChild.nodeType === 3) {
        bindText(node.firstChild, value ?? "");
    } else {
        node.replaceChildren(textNode(value ?? ""));
    }
}

export function onLanguageChange(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

export function setLanguage(value) {
    if (!languages.some(item => item.id === value)) throw Error("Unsupported Foundry language");
    locale = value;
    for (const binding of bindings) update(binding);
    for (const listener of listeners) listener(locale);
}

export function number(value, options = {}) {
    return new Intl.NumberFormat(locale, options).format(value);
}

export function dateTime(value, options = {}) {
    return new Intl.DateTimeFormat(locale, {dateStyle: "medium", timeStyle: "short", ...options}).format(value);
}


let sourceIndex;
function sourceMessages() {
    if (sourceIndex) return sourceIndex;
    const exact = new Map();
    const templates = [];
    for (const [key, english] of Object.entries(catalogs.en)) {
        if (key.startsWith("ccore.preset_")) continue;
        const names = [...english.matchAll(parameters)].map(match => match[1]);
        if (!names.length) {
            if (!exact.has(english)) exact.set(english, key);
            continue;
        }
        // Parameter-only compositions are valid explicit messages, not legacy matchers.
        if (!/[A-Za-z]/.test(english.replace(parameters, ""))) continue;
        const parts = english.split(parameters);
        let pattern = "";
        for (let index = 0; index < parts.length; index++) {
            const escaped = parts[index].replace(/[.*+?^{}()|[\]\\]/g, "\\$&").replaceAll("$", "\\$");
            pattern += index % 2 ? "(.*?)" : escaped;
        }
        templates.push({key, names, pattern: new RegExp("^" + pattern + "$", "s")});
    }
    sourceIndex = {exact, templates};
    return sourceIndex;
}

// Compatibility for persisted human messages. Call only at an explicit UI message site.
export function sourceMessage(value, wire) {
    if (isMessage(value)) return value;
    if (wire?.key) return msg(wire.key, wire.values);
    if (typeof value !== "string" || value.length > 8192) return value;
    const {exact, templates} = sourceMessages();
    if (exact.has(value)) return msg(exact.get(value));
    for (const template of templates) {
        const match = template.pattern.exec(value);
        if (match) return msg(template.key,
            Object.fromEntries(template.names.map((name, index) => [name, match[index + 1]])));
    }
    return value;
}

export function capabilityMessages(value) {
    if (!value || typeof value !== "object") return value;
    if (Array.isArray(value)) return value.map(capabilityMessages);
    const result = {};
    const labels = new Set(["label", "name", "description", "title", "hint", "help", "note", "license_summary", "license_note"]);
    const protectedFields = new Set(["prompt", "system", "default_prompt", "example", "defaults", "config", "references", "settings", "provenance"]);
    for (const [key, item] of Object.entries(value)) {
        result[key] = protectedFields.has(key) ? item :
            labels.has(key) && typeof item === "string" ? sourceMessage(item) :
            key === "help" && item && typeof item === "object" ? Object.fromEntries(Object.entries(item).map(([name, text]) => [name, typeof text === "string" ? sourceMessage(text) : text])) : capabilityMessages(item);
    }
    return result;
}


export function sourceText(value) {
    return isMessage(value) ? value.toJSON() : String(value);
}
