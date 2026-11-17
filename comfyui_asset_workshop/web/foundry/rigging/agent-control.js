import {appendContent,setText} from "../i18n.js";
import {button,el} from "../dom.js";
import {rigText as t} from "./entry.js";

/** Owns the user's camera preference and the acknowledgement shown for Stop. */
export class AgentControls {
    constructor(send) {
        this.send = send;
        this.status = el("span", {role:"status","aria-live":"polite"});
        this.activity = el("span", {class:"rig-agent-activity"});
        this.toggle = button(t("agent_stop"), event => {
            if (event.isTrusted) void this.change();
        }, {class:"rig-agent-toggle"});
        this.follow = el("input", {type:"checkbox"});
        this.followLabel = el("label", {}, this.follow, t("agent_follow"));
        this.element = el("div", {class:"rig-agent-control"});
        appendContent(this.element, this.toggle, this.status, this.followLabel, this.activity);
        this.motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
        this.onMotionPreference = () => {
            if (this.motionPreference.matches) this.follow.checked = false;
            this.refresh();
        };
        this.motionPreference.addEventListener("change", this.onMotionPreference);
        this.refresh();
    }

    update(state) {
        if (!state || state.epoch < (this.state?.epoch ?? -1)) return;
        if(state.epoch>(this.state?.epoch??-1)&&
            ((!state.enabled&&this.unconfirmed==="agent_stop_unconfirmed")||
            (state.enabled&&this.unconfirmed==="agent_resume_unconfirmed"))) this.unconfirmed=null;
        this.state = state;
        if (!state.enabled) {
            this.follow.checked = false;
            setText(this.activity, "");
        }
        this.refresh();
    }

    refresh() {
        const stopped = this.state?.enabled === false;
        this.toggle.disabled = !!this.pending;
        this.follow.disabled = stopped || !!this.pending || !!this.unconfirmed || this.motionPreference.matches;
        setText(this.toggle, t(stopped ? "agent_resume" : "agent_stop"));
        const status = this.pending || this.unconfirmed || (stopped ? "agent_stopped" : null);
        setText(this.status, status ? t(status) : "");
    }

    async change() {
        if (this.pending) return;
        const resume = this.state?.enabled === false && !this.unconfirmed;
        this.pending = resume ? "agent_resume_requested" : "agent_stop_requested";
        if (!resume) this.follow.checked = false;
        this.refresh();
        try {
            const offer = resume ? await this.send("prepare_resume") : null;
            const state = await this.send(resume ? "resume" : "stop", offer?.capability);
            this.unconfirmed = null;
            this.update(state);
        } catch {
            this.unconfirmed = resume ? "agent_resume_unconfirmed" : "agent_stop_unconfirmed";
        } finally {
            this.pending = null;
            this.refresh();
        }
    }

    humanCameraInput() {
        this.follow.checked = false;
    }

    showActivity(key, values={}) {
        if (this.state?.enabled === false || this.pending || this.unconfirmed) return;
        setText(this.activity, t(key, values));
    }

    get following() {
        return this.follow.checked && !this.follow.disabled && !this.motionPreference.matches;
    }

    dispose() {
        this.motionPreference.removeEventListener("change", this.onMotionPreference);
    }
}
