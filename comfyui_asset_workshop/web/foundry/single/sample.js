import {msg} from "../i18n.js";

const sampleUrl = new URL("../assets/examples/ray-gun-reference.webp", import.meta.url);
const maxBytes = 20 * 1024 ** 2;

export async function loadSampleReference({signal} = {}) {
    try {
        const response = await fetch(sampleUrl, {signal});
        signal?.throwIfAborted();
        if (!response.ok || Number(response.headers.get("content-length")) > maxBytes) {
            throw Error("Sample response unavailable");
        }
        const blob = await response.blob();
        if (blob.type !== "image/webp" || blob.size < 20 || blob.size > maxBytes) {
            throw Error("Invalid sample image");
        }
        const header = new DataView(await blob.slice(0, 12).arrayBuffer());
        signal?.throwIfAborted();
        if (header.getUint32(0) !== 0x52494646 || header.getUint32(8) !== 0x57454250 ||
                header.getUint32(4, true) + 8 !== blob.size) {
            throw Error("Invalid WebP container");
        }
        return new File([blob], "ray-gun-reference.webp", {type: blob.type});
    } catch (cause) {
        signal?.throwIfAborted();
        throw Error(String(msg("mesh.sample_image_unavailable")), {cause});
    }
}
