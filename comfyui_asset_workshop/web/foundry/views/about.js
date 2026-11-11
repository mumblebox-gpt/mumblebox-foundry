import {sourceMessage} from "../i18n.js";
import {msg} from "../i18n.js";
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
    if(!shell.data)throw Error(msg("common.foundry_information_is_unavailable_reload_the_interface_after_the_extension"));
    return el("div",{},el("div",{class:"page-head"},el("div",{},el("span",{class:"eyebrow"},msg("common.the_people_tools_behind_the_work")),
        el("h2",{},msg("common.about_mumblebox")))),
        el("p",{},msg("common.mumblebox_3d_asset_foundry_is_a_growing_community_toolbox_of_local_workflows")),
        el("p",{},msg("common.you_should_not_need_to_understand_a_node_graph_to_get_started_guided_wizards")),
        el("section",{class:"note-panel","aria-labelledby":"foundry-agent-workflows"},
            el("h3",{id:"foundry-agent-workflows"},msg("common.give_your_coding_agent_a_head_start")),
            el("p",{},msg("common.connect_your_coding_agent_to_foundry_through_the_model_context_protocol_mcp")),
            el("p",{},msg("common.start_with_a_reference_image_or_a_mesh_the_agent_can_take_into_blender_or_an")),
            el("div",{class:"actions"},link(msg("common.set_up_foundry_mcp"),"https://github.com/mumblebox-gpt/mumblebox-foundry/blob/HEAD/docs/AGENT-SETUP.md"))),
        el("p",{},msg("common.foundry_grows_through_learning_experimentation_and_community_contributions_g")),
        el("div",{class:"actions"},link(msg("common.mumblebox_on_github"),shell.data.github),link(msg("common.suggest_a_workflow"),"https://github.com/mumblebox-gpt/mumblebox-foundry/issues"),link(msg("common.pull_requests"),"https://github.com/mumblebox-gpt/mumblebox-foundry/pulls"),el("span",{class:"badge"},msg("common.interface_v", {version: shell.data.version}))),
        el("h3",{style:"margin:30px 0 18px"},msg("common.models_and_workflow_tools")),
        el("div",{class:"credit-list"},shell.data.credits.map(item=>el("article",{class:"credit"},
            el("h3",{},item.name),hint(item.creator),el("p",{class:"role"},sourceMessage(item.stage)),el("p",{},item.observation),
            item.version?hint(msg("common.installed_workflow", {version: item.version})):null,link(msg("common.official_project"),item.source),
            item.note?hint(item.note):null))),
        el("section",{'aria-labelledby':"foundry-thank-you"},
            el("h3",{id:"foundry-thank-you",style:"margin:30px 0 18px"},msg("common.thank_you")),
            el("p",{},msg("common.to_the_people_who_share_fixes_useful_workflows_thoughtful_feedback_and_their")),
            el("div",{class:"credit-list"},contributors.map(person=>el("article",{class:"credit"},
                el("h3",{},person.name),link("@"+person.handle,person.profile),el("p",{},person.contribution),
                el("div",{class:"actions"},person.changes.map(([label,url])=>link(label,url))))))),
        el("div",{class:"note-panel"},hint(msg("common.package_specific_resources_measurements_and_license_notices_are_recorded_in"))));
}
