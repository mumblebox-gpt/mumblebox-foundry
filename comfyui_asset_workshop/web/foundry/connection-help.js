import {msg, appendContent} from "./i18n.js";
import {problemPanel} from './problem-panel.js';
import {el,button,hint,link} from "./dom.js";
import {dialog} from "./dialogs.js";

// Parse only a Hugging Face repository identifier, never arbitrary HTML or URLs.
// Legacy saved errors contain the same identifier but no clickable access URL.
export function modelAccessUrl(message) {
    const match=String(message).match(/Hugging Face denied access to ([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)\//);
    return match?`https://huggingface.co/${encodeURIComponent(match[1])}/${encodeURIComponent(match[2])}`:null;
}

export function modelAccessError(shell,message) {
    const panel=problemPanel(message);
    const url=modelAccessUrl(message);
    if(url)appendContent(panel, el("div",{class:"actions"},link(msg("common.open_model_access_page"),url),
        button(msg("common.open_hugging_face_settings"),()=>shell.settings({service:"hugging-face"}))));
    return panel;
}

// One instruction source serves the resource browser and the token settings.
export function civitaiInstructions() {
    return el("div",{class:"connection-help"},el("ol",{},
        el("li",{},msg("common.sign_in_to"),link(msg("common.civitai_account_settings"),"https://civitai.com/user/account"),msg("common.and_find_the_api_keys_section")),
        el("li",{},msg("common.add_an_api_key_name_it_mumblebox_foundry_then_copy_the_generated_key")),
        el("li",{},msg("common.in_foundry_open_settings_civitai_and_paste_the_key_into_access_token")),
        el("li",{},msg("common.click_connect_or_replace_token_if_already_connected_then_test_connection"))),
        hint(msg("common.keep_your_key_private_foundry_stores_it_securely_on_this_computer_it_is_not")),
        link(msg("common.civitai_s_authentication_guide"),"https://github.com/civitai/civitai-developer-docs/blob/main/site/guide/authentication.md"));
}

export function showCivitaiHelp(shell) {
    return dialog(shell,msg("common.how_to_connect_civitai"),civitaiInstructions(),[
        {label:msg("common.open_civitai_settings"),primary:true,run:async close=>{close();await shell.settings({service:"civitai"});}}
    ]);
}
