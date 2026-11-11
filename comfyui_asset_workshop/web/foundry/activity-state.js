import {t, sourceMessage} from "./i18n.js";
// Pure presentation policy. A file on disk is not a resident model.
export const FIRST_USE_MESSAGE = "The model is downloading on first use. This may take some time but only happens once per model.";

export function utilization(used, total) {
    return Number.isFinite(used) && Number.isFinite(total) && total > 0
        ? Math.min(1, Math.max(0, used / total)) : null;
}

export function loadedState(status) {
    if(Array.isArray(status?.model_residency)){
        const rows=status.model_residency;
        const loaded=rows.filter(r=>r.state==='loaded');
        const offloaded=rows.filter(r=>r.state==='offloaded');
        const unknown=rows.filter(r=>r.state==='unknown');
        const names=[...loaded,...offloaded].map(r=>String(sourceMessage(r.name))+(r.device?' ('+r.device+')':''));
        const checking=unknown.map(r=>t('common.checking_model', {name:sourceMessage(r.name)}));
        const items=[...names,...checking];
        const state=loaded.length?'loaded':offloaded.length?'offloaded':unknown.length?'unknown':'empty';
        return {state,label:items.join(' · ')||t('common.no_models_loaded')};
    }
    if (!status || !Number.isFinite(status.loaded_models)) return {state:"unknown", label:t("common.model_state_unavailable")};
    const loaded = status.loaded_models > 0 || status.helper_loaded === true;
    return {state:loaded?"loaded":"empty", label:loaded?t("common.models_loaded"):t("common.no_models_loaded")};
}

export function activityState(status) {
    if (!status) return {busy:false, label:t("common.status_unavailable"), unknown:true};
    const manual = status.resource_download?.status === "running";
    const download = (manual?status.resource_download:status.download) || {};
    const preparing=status.workflow_activity?.find(r=>r.dependency);
    if(preparing?.dependency){
        const d=preparing.dependency;
        return {busy:true,label:d.phase==='downloading'?t("common.downloading_required_models"):t("common.preparing_required_models"),
            detail:d.phase==='downloading'?t('common.first_use_download'):sourceMessage(d.name||d.phase),
            fraction:utilization(d.bytes,d.total)};
    }
    if (["running", "downloading", "verifying"].includes(download.status))
        return {busy:true, label:download.status==="verifying"?t("common.verifying_model_files"):t("common.downloading_model"), detail:manual?t("common.downloading_selected_resource"):t("common.first_use_download"),
            fraction:utilization(download.bytes ?? download.downloaded ?? download.completed_bytes, download.total ?? download.total_bytes)};
    if (status.resource_cleanup?.status === "releasing") return {busy:true, label:t("common.unloading_models")};
    if (status.running || status.description_helper?.running) return {busy:true, label:status.description_helper?.running?sourceMessage(status.description_helper.phase):t("common.workflow_running")};
    if (download.status === "failed") return {busy:false, label:sourceMessage(download.error || "Model download failed"), error:true};
    if (download.status === "paused") return {busy:false, label:t("common.model_download_paused")};
    return {busy:false, label:t("common.ready")};
}
