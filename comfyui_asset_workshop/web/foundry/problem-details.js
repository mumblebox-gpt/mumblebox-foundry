import {isMessage, sourceMessage, sourceText} from "./i18n.js";

const workflows = new Set(["single-image", "turnaround"]);
const errorCodes = new Set(["FOUNDRY_OFFLINE", "ReferenceError", "TypeError", "RangeError", "SyntaxError"]);

function reportMessage(message) {
    // Only share messages that are already part of the app. Translated
    // templates may contain private values, so include their stable ID alone.
    if (typeof message === "string" && message.length <= 1024) {
        if (message === "setText is not defined") return message;
        const known = sourceMessage(message);
        if (isMessage(known)) {
            return Object.keys(known.values).length ? known.key : sourceText(known);
        }
    }
    return "Original message kept in Foundry.";
}

export function buildProblemDetails({version, workflow, step, code, message} = {}) {
    const safeVersion = typeof version === "string" && /^\d{1,5}\.\d{1,5}\.\d{1,5}(?:-preview\.\d{1,5})?$/.test(version)
        ? version : "Unknown";
    const safeCode = errorCodes.has(code) || (typeof code === "string" && /^FOUNDRY_HTTP_[45]\d{2}$/.test(code))
        ? code : "Unknown";
    const safeStep = Number.isInteger(step) && step >= 1 && step <= 5 ? step : "Unknown";
    // Fixed size fields and the catalog limit keep the report far below 32 KiB.
    return [
        "Foundry version: " + safeVersion,
        "Workflow: " + (workflows.has(workflow) ? workflow : "Unknown"),
        "Step: " + safeStep,
        "Error code: " + safeCode,
        "Error: " + reportMessage(message),
    ].join("\n");
}
