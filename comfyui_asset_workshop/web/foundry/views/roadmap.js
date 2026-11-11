import {msg, setText, sourceMessage} from "../i18n.js";
import {el,button,link} from "../dom.js";
import {roadmap} from "../roadmap-data.js";

export function render() {
    const sections = roadmap.map(group => el("section", {
        class: "roadmap-section", "aria-label": group.title,
    },
        el("header", {class: "roadmap-section-head"},
            el("h3", {}, group.title),
            el("span", {class: "roadmap-count"}, String(group.items.length))),
        el("p", {class: "muted roadmap-summary"}, group.summary),
        el("ul", {class: "roadmap-items"}, group.items.map(item => el("li", {},
            el("div", {class: "roadmap-item-head"},
                el("h4", {}, item.title),
                el("span", {class: "roadmap-state", "data-state": item.status || "Planned"}, sourceMessage(item.status || "Planned"))),
            el("p", {}, item.description),
            item.source ? link(sourceMessage(item.sourceLabel || "Source"), item.source) : null,
        ))),
    ));
    const count = el("span", {class: "muted", role: "status", "aria-live": "polite"});
    const filters = el("div", {class: "roadmap-filters", role: "group", "aria-label": msg("common.filter_roadmap_by_type")});
    const choices = [{id: "all", title: msg("common.all")}, ...roadmap];
    function select(id) {
        sections.forEach((section, index) => { section.hidden = id !== "all" && roadmap[index].id !== id; });
        [...filters.children].forEach((control, index) => control.setAttribute("aria-pressed", String(choices[index].id === id)));
        const shown = roadmap.filter(group => id === "all" || group.id === id);
        setText(count, msg("common.items", {value1: shown.reduce((sum, group) => sum + group.items.length, 0)}));
    }
    for (const choice of choices) filters.append(button(choice.title, () => select(choice.id), {"aria-pressed": "false"}));
    select("all");
    return el("div", {class: "roadmap"},
        el("header", {class: "roadmap-head"},
            el("div", {}, el("h2", {}, msg("common.roadmap")), el("p", {class: "muted"}, msg("common.planned_improvements_and_research_for_the_foundry_scope_and_order_may_change"))), count),
        filters,
        el("div", {class: "roadmap-sections"}, sections),
    );
}
