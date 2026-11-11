import {capabilityMessages, sourceMessage} from "./i18n.js";
import {msg} from "./i18n.js";
const PREFIX = "/mumblebox-foundry/v1";
export async function request(path, data, options = {}) {
    let response;
    try { response = await fetch(path.startsWith("/") ? path : PREFIX + "/" + path, {
        method: data === undefined ? "GET" : "POST",
        ...options,
        headers: {"Content-Type":"application/json", ...(options.headers || {})},
        ...(data === undefined ? {} : {body:JSON.stringify(data)}),
    }); } catch (cause) {
        const error=new Error(msg("common.foundry_has_lost_its_connection_to_the_local_service_restart_foundry_in_pino"),{cause});
        error.code="FOUNDRY_OFFLINE";throw error;
    }
    let result;
    try { result = await response.json(); }
    catch { throw Error(msg("common.the_foundry_service_is_unavailable_check_that_the_installed_extension_is_loa")); }
    if (!response.ok) {
        const error = new Error(String(sourceMessage(result.error || result.message || msg("common.request_failed"), result.error_i18n)));
        error.i18n = result.error_i18n;
        throw error;
    }
    return path.endsWith("capabilities") ? capabilityMessages(result) : result;
}
export const fileUrl = (id, file) => PREFIX + "/library/" + encodeURIComponent(id) + "/files/" + encodeURIComponent(file);
export function pollResources(onStatus, onError) {
    let disposed = false, timer, controller, failures=0;
    const run = async () => {
        if(disposed)return;
        controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        let delay=1000;
        try {
            const data = await request("/asset-workshop/status", undefined, {signal:controller.signal});
            failures=0;
            if (!disposed) onStatus(data);
        } catch (error) { delay=Math.min(10000,1000*2**++failures);if (!disposed) onError(error); }
        finally { clearTimeout(timeout); if (!disposed) timer = setTimeout(run, delay); }
    };
    run();
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); };
}
