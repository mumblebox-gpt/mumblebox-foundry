import {el, button, hint, icon, link} from "../dom.js";
import {dialog} from "../dialogs.js";
import {workingStar} from "../activity.js";
import {dateTime, msg, onLanguageChange, setText, t} from "../i18n.js";
import {request} from "../services.js";

const repositories = [
    {name: "EL4CTEO / Blender Skills", url: "https://github.com/EL4CTEO/blender-skills", copy: "blender_skills"},
    {name: "1Pio / Blender Workbench", url: "https://github.com/1Pio/blender-workbench", copy: "workbench"},
];
const blenderDownload = "https://www.blender.org/download/";
const message = (key, values) => msg("agent_setup." + key, values);
const text = (key, values) => t("agent_setup." + key, values);
const hero = new URL("../../assets/foundry/connect-agent.webp", import.meta.url).href;

function connectionState(status) {
    if (status?.working && status.connected) return "working";
    if (status?.running_jobs) return "disconnected_job";
    if (status?.connected) return "connected";
    return "connect";
}

function setupPrompt(setup, selected) {
    const lines = [
        text("prompt_intro"), "",
        text("prompt_install", {path:setup.install_directory}),
        text("prompt_address", {url:setup.address}),
        text("prompt_versions", {version:setup.version, revision:setup.skill.skill_revision}),
        text("prompt_skill", {path:setup.skill_path}), "",
    ];
    if (setup.install_python) {
        const runtime = setup.install_python;
        lines.push(text("prompt_environment", {python:runtime.base_python, folder:runtime.environment, file:runtime.requirements}), "");
    }
    lines.push(text("prompt_register"), JSON.stringify(setup.configuration, null, 2), "", text("prompt_verify"));
    if (selected.size) {
        lines.push("", text("prompt_repos"));
        for (const repo of repositories) {
            if (selected.has(repo.copy)) lines.push("- " + repo.url + " - " + text(repo.copy + "_install"));
        }
        if (setup.blender) lines.push("", text("prompt_blender_path", {path:setup.blender}));
        lines.push("", text("prompt_blender", {url:blenderDownload}));
    }
    lines.push("", text("prompt_use"));
    return lines.join("\n");
}

export class AgentSetup {
    constructor(shell) {
        this.shell = shell;
        this.selected = new Set();
        this.headerLabel = el("span", {"aria-live":"polite"}, message("connect"));
        this.header = button([icon("plug",18),el("span",{class:"agent-dot","aria-hidden":"true"}),workingStar(22),this.headerLabel],
            () => this.open(), {class:"agent-connect primary", "aria-haspopup":"dialog", "data-state":"connect"});
    }

    update(status) {
        const state = connectionState(status);
        if (state === this.header.dataset.state) return;
        this.header.dataset.state = state;
        setText(this.headerLabel, message(state));
    }

    statusLine() {
        const line = el("p",{class:"agent-status-line","aria-live":"polite"});
        const statusLabel = el("strong");
        const last = el("small",{class:"muted"});
        line.append(el("span",{class:"agent-dot","aria-hidden":"true"}),statusLabel,last);
        let lastUsed;
        const update = (languageChanged = false) => {
            const status = this.shell.status?.agent_presence;
            const state = connectionState(status);
            if (line.dataset.state !== state) {
                line.dataset.state = state;
                setText(statusLabel,message(state === "connect" ? "ready" : state));
            }
            if (languageChanged || status?.last_used_at !== lastUsed) {
                lastUsed = status?.last_used_at;
                setText(last,lastUsed ? message("last_used",{time:dateTime(lastUsed*1000,{timeStyle:"short"})}) : "");
            }
        };
        const stopLanguage = onLanguageChange(() => update(true));
        this.shell.statusListeners.add(update);
        update();
        return {line, dispose:() => {this.shell.statusListeners.delete(update);stopLanguage();}};
    }

    integration() {
        const status = this.statusLine();
        const element = el("section",{class:"agent-integration"},
            el("div",{},el("h2",{},message("integration")),status.line),
            button([icon("plug",18),message("connect")],() => this.open(),{class:"primary","aria-haspopup":"dialog"}));
        return {element, dispose:status.dispose};
    }

    open() {
        const shell = this.shell;
        const status = this.statusLine();
        const preview = el("textarea",{readOnly:true,rows:6,"aria-label":message("view_prompt"),spellcheck:false});
        const disclosure = el("details",{class:"agent-prompt",hidden:true},el("summary",{},message("view_prompt")),preview);
        const feedback = el("p",{class:"muted agent-copy-feedback",role:"status"},message("loading"));
        let setup;

        const refresh = () => { if (setup) preview.value = setupPrompt(setup, this.selected); };
        const cards = repositories.map(repo => {
            const check = el("input",{type:"checkbox",checked:this.selected.has(repo.copy),onchange:() => {
                if (check.checked) this.selected.add(repo.copy); else this.selected.delete(repo.copy);
                setText(feedback,"");
                refresh();
            }});
            return el("article",{class:"agent-repo"},
                el("label",{},check,el("span",{},el("strong",{},repo.name),hint(message(repo.copy)))),
                link(message("github",{repo:repo.name}),repo.url));
        });
        const body = el("div",{class:"agent-setup"},
            el("div",{class:"agent-hero"},
                el("img",{src:hero,alt:"",width:768,height:512}),
                el("div",{},el("h3",{},message("head_start")),el("p",{},message("intro")),hint(message("skill_intro")))),
            status.line,
            el("p",{},message("how_to")),
            el("section",{class:"agent-repositories"},el("h3",{},message("recommended")),hint(message("thanks")),...cards,
                el("p",{class:"muted agent-blender"},message("blender_needed")," ",link(message("get_blender"),blenderDownload))),
            disclosure,feedback);

        const modal = dialog(shell,message("connect"),body,[{label:message("copy"),primary:true,run:async () => {
            if (!setup) return;
            try {
                await navigator.clipboard.writeText(preview.value);
                setText(feedback,message("copied"));
            } catch {
                disclosure.open = true;
                preview.focus();
                preview.select();
                setText(feedback,message("copy_manually"));
            }
        }}]);
        modal.surface.classList.add("agent-setup-dialog");
        const copy = modal.surface.querySelector(".dialog-actions button");
        copy.disabled = true;
        const abort = new AbortController();
        const stopLanguage = onLanguageChange(refresh);
        modal.surface.addEventListener("foundry-close",() => {
            abort.abort();
            stopLanguage();
            status.dispose();
        },{once:true});
        request("agent/setup",undefined,{signal:abort.signal}).then(data => {
            if (abort.signal.aborted) return;
            setup = data;
            refresh();
            disclosure.hidden = false;
            copy.disabled = false;
            setText(feedback,"");
        }).catch(() => {
            if (!abort.signal.aborted) setText(feedback,message("unavailable"));
        });
    }
}
