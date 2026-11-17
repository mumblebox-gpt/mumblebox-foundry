/** Render inspection images from the existing scene without moving its camera. */
export async function nativeThree(spec) {
    if (!spec) throw Error("The installed viewer does not expose the required 3D tools.");
    const module = await import(spec.url);
    return Object.fromEntries(Object.entries(spec.exports).map(([name, alias]) => [name, module[alias]]));
}

export function inspectionCamera(viewport, view, aspect, three) {
    const current = viewport.camera;
    if (view === "current") {
        current.updateMatrixWorld();
        return current.clone();
    }
    const viewer = viewport.viewer;
    const bounds = viewer.modelManager.getCurrentBounds();
    const target = bounds.getCenter(current.position.clone());
    const modelSize = bounds.getSize(target.clone()).length();
    const region = view === "part" || viewport.linkRegion ? viewport.selectedRegion() : null;
    if (region) target.fromArray(region.center).applyMatrix4(viewport.meshTransform);
    const radius = region ? region.radius * viewport.meshTransform.getMaxScaleOnAxis() : modelSize * 0.5;
    const distance = Math.max(radius * 4.8 / Math.min(aspect, 1), 0.001);
    const yaw = viewport.state.orientation * Math.PI / 2
        + ({side: Math.PI / 2, back: Math.PI, oblique: Math.PI / 4, part: Math.PI / 4}[view] || 0);
    const span = radius * 1.15 / Math.min(aspect, 1);
    const camera = region || ["front", "side", "back"].includes(view)
        ? new three.OrthographicCamera(-span * aspect, span * aspect, span, -span, 0.0001, distance + modelSize * 4)
        : new three.PerspectiveCamera(34, aspect, 0.0001, distance + modelSize * 4);
    camera.position.copy(target).addScaledVector(target.clone().set(Math.sin(yaw), 0, Math.cos(yaw)), distance);
    camera.lookAt(target);
    camera.updateMatrixWorld(true);
    if (region) {
        const inverse = camera.matrixWorldInverse;
        let halfWidth=0,halfHeight=0;
        for (const corner of region.corners) {
            const point=target.clone().fromArray(corner).applyMatrix4(viewport.meshTransform).applyMatrix4(inverse);
            const origin=target.clone().applyMatrix4(inverse);
            halfWidth=Math.max(halfWidth,Math.abs(point.x-origin.x));
            halfHeight=Math.max(halfHeight,Math.abs(point.y-origin.y));
        }
        const fit=Math.max(halfHeight,halfWidth/aspect,0.001)*1.1;
        camera.left=-fit*aspect;
        camera.right=fit*aspect;
        camera.top=fit;
        camera.bottom=-fit;
        camera.updateProjectionMatrix();
    }
    return camera;
}

export function renderObservation(viewer, camera, width, height, three) {
    const renderer = viewer.renderer ?? viewer.sceneManager?.renderer;
    const scene = viewer.scene ?? viewer.sceneManager?.scene;
    if (!renderer || !scene || !three.WebGLRenderTarget)
        throw Error("The installed 3D viewer cannot capture an independent view.");
    const previous = renderer.getRenderTarget();
    const target = new three.WebGLRenderTarget(width, height);
    target.texture.colorSpace = renderer.outputColorSpace;
    const bytes = new Uint8Array(width * height * 4);
    try {
        renderer.setRenderTarget(target);
        renderer.clear();
        renderer.render(scene, camera);
        renderer.readRenderTargetPixels(target, 0, 0, width, height, bytes);
    } finally {
        renderer.setRenderTarget(previous);
        target.dispose();
    }
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    const pixels = context.createImageData(width, height);
    const stride = width * 4;
    for (let row = 0; row < height; row++) {
        const from = (height - row - 1) * stride;
        pixels.data.set(bytes.subarray(from, from + stride), row * stride);
    }
    context.putImageData(pixels, 0, 0);
    return canvas;
}
