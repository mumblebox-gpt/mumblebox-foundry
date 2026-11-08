import {el,hint,link} from "../dom.js";

// Add people here as their contributions are incorporated; retain specific source links.
const contributors=[{
    name:"Hal Rottenberg",handle:"halr9000",profile:"https://github.com/halr9000",
    contribution:"HairDeck dependency-build compatibility and Blender download improvements for the installer.",
    changes:[
        ["HairDeck installer fix","https://github.com/halr9000/mumblebox-foundry/commit/7c731364e92fbec4bec7bb65bed086c59c2210b7"],
        ["Blender download improvement","https://github.com/halr9000/mumblebox-foundry/commit/3be2d2393e323d4edad404704671e13a9d85566e"]
    ]
}];

export async function render(shell) {
    if(!shell.data)throw Error("Foundry information is unavailable. Reload the interface after the extension is ready.");
    return el("div",{},el("div",{class:"page-head"},el("div",{},el("span",{class:"eyebrow"},"THE PEOPLE & TOOLS BEHIND THE WORK"),
        el("h2",{},"About Mumblebox"))),
        el("p",{},"Mumblebox 3D Asset Foundry is a growing community toolbox of local workflows for creating images, 3D assets, hair and splats. The aim is to collect the best practical approaches we discover, test them through real use and make them easier to work with."),
        el("p",{},"You should not need to understand a node graph to get started. Guided wizards keep the main options simple, explain what each choice changes and provide useful defaults. Advanced controls stay available as you learn or need more control."),
        el("p",{},"Foundry grows through learning, experimentation and community contributions. Good workflow suggestions, improvements and pull requests are welcome. The researchers, model authors and workflow creators below deserve the credit for the tools that make this possible."),
        el("div",{class:"actions"},link("Mumblebox on GitHub",shell.data.github),link("Suggest a workflow","https://github.com/mumblebox-gpt/mumblebox-foundry/issues"),link("Pull requests","https://github.com/mumblebox-gpt/mumblebox-foundry/pulls"),el("span",{class:"badge"},"Interface v"+shell.data.version)),
        el("h3",{style:"margin:30px 0 18px"},"Models and workflow tools"),
        el("div",{class:"credit-list"},shell.data.credits.map(item=>el("article",{class:"credit"},
            el("h3",{},item.name),hint(item.creator),el("p",{class:"role"},item.stage),el("p",{},item.observation),
            item.version?hint("Installed workflow: "+item.version):null,link("Official project",item.source),
            item.note?hint(item.note):null))),
        el("section",{'aria-labelledby':"foundry-thank-you"},
            el("h3",{id:"foundry-thank-you",style:"margin:30px 0 18px"},"Thank You"),
            el("p",{},"To the people who share fixes, useful workflows, thoughtful feedback and their time: thank you for helping Foundry grow. This running acknowledgment records contributions as they become part of the toolbox."),
            el("div",{class:"credit-list"},contributors.map(person=>el("article",{class:"credit"},
                el("h3",{},person.name),link("@"+person.handle,person.profile),el("p",{},person.contribution),
                el("div",{class:"actions"},person.changes.map(([label,url])=>link(label,url))))))),
        el("div",{class:"note-panel"},hint("Package-specific resources, measurements and license notices are recorded in each export's README and metadata. Credits describe the current workflow; they do not grant additional rights to model weights or outputs.")));
}
