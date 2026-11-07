import {el,hint,link} from "../dom.js";
export async function render(shell) {
    if(!shell.data)throw Error("Foundry information is unavailable. Reload the interface after the extension is ready.");
    return el("div",{},el("div",{class:"page-head"},el("div",{},el("span",{class:"eyebrow"},"THE PEOPLE & TOOLS BEHIND THE WORK"),
        el("h2",{},"About Mumblebox"))),
        el("p",{},"Mumblebox 3D Asset Foundry brings image creation, 3D generation and asset preparation into a collection of local workflows. Guided steps explain the choices, with useful defaults and advanced controls when you need them. Create detailed masters and export versions for games, further editing or printing."),
        el("p",{},"Foundry is a toolbox built around the work of these researchers and open-source contributors. Their models and tools make these workflows possible; our contribution is connecting them with useful defaults, clear choices and saved results."),
        el("div",{class:"actions"},link("Mumblebox on GitHub",shell.data.github),el("span",{class:"badge"},"Interface v"+shell.data.version)),
        el("h3",{style:"margin:30px 0 18px"},"Models and workflow tools"),
        el("div",{class:"credit-list"},shell.data.credits.map(item=>el("article",{class:"credit"},
            el("h3",{},item.name),hint(item.creator),el("p",{class:"role"},item.stage),el("p",{},item.observation),
            item.version?hint("Installed workflow: "+item.version):null,link("Official project",item.source),
            item.note?hint(item.note):null))),
        el("div",{class:"note-panel"},hint("Package-specific resources, measurements and license notices are recorded in each export's README and metadata. Credits describe the current workflow; they do not grant additional rights to model weights or outputs.")));
}
