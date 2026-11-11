import {sourceMessage} from "./i18n.js";
import {msg, setText, bindAttribute, appendContent, prependContent, replaceContent} from "./i18n.js";
import {maintenanceBusy} from './maintenance-state.js';
import {el,button,link,hint,icon} from "./dom.js";
import {request} from "./services.js";
import {dialog} from "./dialogs.js";

export class UpdateChecks {
    constructor(shell) {
        this.shell=shell;
        this.listeners=new Set();
        this.banner=el("aside",{class:"update-notice",hidden:true,"aria-label":msg("common.foundry_update")});
        shell.content.before(this.banner);
        this.flag=button(msg("common.check_for_updates"),async()=>{
            if(this.result?.state==='available'){if(!maintenanceBusy(shell.status))this.details();return;}
            try{await this.check(true);}catch(error){this.result={state:'unavailable',message:error.message};this.notify();}
        },{class:'update-flag'});
        shell.updateSlot.append(this.flag);this.refreshFlag();
    }
    async startup() {
        if(this.shell.data?.preferences.auto_check_updates===false){this.result={...await request('updates/status').catch(()=>({})),state:'disabled'};this.refreshFlag();return;}
        try {await this.check(false);}catch(error){
            this.result={state:"unavailable",message:error.message};this.notify();
        }
    }
    async check(manual=true) {
        if(this.pending)return this.pending;
        this.checking=true;this.refreshFlag();
        this.pending=request("updates/check",{manual}).then(result=>{
            if(this.disposed)return result;
            this.result=result;this.refreshBanner();this.notify();return result;
        }).finally(()=>{this.pending=null;this.checking=false;this.refreshFlag();});
        return this.pending;
    }
    notify() {this.refreshFlag();for(const listener of this.listeners)listener();}
    refreshFlag(){
        if(!this.flag)return;const state=this.checking?'checking':this.result?.state||'unchecked';
        const labels={current:msg("common.up_to_date"),available:msg("common.update_available"),checking:msg("common.checking"),unavailable:msg("common.couldn_t_check"),unchecked:msg("common.check_for_updates"),disabled:msg("common.check_for_updates"),no_release:msg("common.no_release_yet")};
        const busy=state==='available'&&maintenanceBusy(this.shell.status);
        const key=[state,busy,this.result?.message].join('|');if(key===this.flagKey)return;this.flagKey=key;
        this.flag.dataset.state=state;replaceContent(this.flag,icon(state==='current'?'check':state==='available'?'download':'refresh',14),labels[state]||msg('common.check_for_updates'));
        this.flag.disabled=this.checking||busy;
        bindAttribute(this.flag, "title", busy?msg("common.wait_for_processing_and_downloads_to_finish_before_updating"):state==='available'?msg("common.view_the_update_and_installation_options"):state === "current" ? msg("common.current_release_notice") : sourceMessage(this.result?.message)||msg('common.check_releases'));
    }
    refreshBanner() {this.banner.hidden=true;this.refreshFlag();}
    details() {
        const result=this.result;if(!result?.release_url||maintenanceBusy(this.shell.status))return;
        const actions=el("div",{class:"actions"},link(msg("common.release_notes_on_github"),result.release_url));
        if(result.download_url)prependContent(actions, link(msg("common.download_update"),result.download_url));
        dialog(this.shell,msg("common.foundry", {latest: result.latest}),el("div",{},
            hint(msg("common.in_pinokio_choose_update_in_the_left_sidebar_to_install_and_restart_foundry")),
            actions,el("pre",{class:"release-notes"},result.notes||"See GitHub for release notes.")));
    }
    settings() {
        const shell=this.shell;
        const automatic=el("input",{type:"checkbox",checked:shell.data?.preferences.auto_check_updates!==false});
        const status=el("p",{role:"status","aria-live":"polite",class:"muted"});
        const notes=el("div",{class:"actions"});
        const draw=()=>{
            const data=this.result;
            setText(status, sourceMessage(data?.message)||msg("common.no_update_check"));
            if(data?.checked_at)setText(status, status.textContent + (msg("common.last_checked", {value1: new Date(data.checked_at*1000).toLocaleString()})));
            notes.replaceChildren();
            if(data?.state==="available")appendContent(notes, button(msg("common.view_update_and_download"),()=>this.details(),{disabled:maintenanceBusy(shell.status)}));
        };
        const check=button(msg("common.check_for_updates"),async()=>{
            check.disabled=true;setText(status, msg("common.checking_github_releases"));
            try{await this.check(true);draw();}catch(error){setText(status, sourceMessage(error.message));}
            finally{check.disabled=false;}
        });
        automatic.addEventListener("change",async()=>{
            automatic.disabled=true;
            try{shell.data.preferences=await request("preferences",{auto_check_updates:automatic.checked},{method:"PATCH"});}
            catch(error){automatic.checked=!automatic.checked;setText(status, sourceMessage(error.message));}
            finally{automatic.disabled=false;}
        });
        const element=el("section",{class:"settings-section update-settings"},el("h3",{},msg("common.updates")),
            hint(msg("common.installed_version", {version: shell.data.version})),
            el("label",{class:"choice"},automatic,msg("common.check_for_updates_on_startup")),
            hint(msg("common.checks_published_github_versions_on_startup_with_a_five_minute_cache_check_f")),
            el("div",{class:"actions"},check),status,notes);
        this.listeners.add(draw);draw();
        request("updates/status").then(result=>{if(element.isConnected&&!this.pending){this.result=result;draw();}}).catch(error=>{if(element.isConnected)setText(status, sourceMessage(error.message));});
        return {element,dispose:()=>this.listeners.delete(draw)};
    }
    dispose() {this.disposed=true;this.listeners.clear();this.banner.remove();this.flag.remove();}
}
