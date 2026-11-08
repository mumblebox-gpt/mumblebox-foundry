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
    if(url)panel.append(el("div",{class:"actions"},link("Open model access page",url),
        button("Open Hugging Face settings",()=>shell.settings({service:"hugging-face"}))));
    return panel;
}

// One instruction source serves the resource browser and the token settings.
export function civitaiInstructions() {
    return el("div",{class:"connection-help"},el("ol",{},
        el("li",{},"Sign in to ",link("Civitai account settings","https://civitai.com/user/account")," and find the API Keys section."),
        el("li",{},"Add an API key, name it Mumblebox Foundry, then copy the generated key."),
        el("li",{},"In Foundry, open Settings → Civitai and paste the key into Access token."),
        el("li",{},"Click Connect (or Replace token if already connected), then Test connection.")),
        hint("Keep your key private. Foundry stores it securely on this computer; it is not included in asset exports."),
        link("Civitai’s authentication guide","https://github.com/civitai/civitai-developer-docs/blob/main/site/guide/authentication.md"));
}

export function showCivitaiHelp(shell) {
    return dialog(shell,"How to connect Civitai",civitaiInstructions(),[
        {label:"Open Civitai settings",primary:true,run:async close=>{close();await shell.settings({service:"civitai"});}}
    ]);
}
