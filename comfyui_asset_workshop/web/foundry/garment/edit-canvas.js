/** Desktop paint and point controls for the author's projected guide coordinates. */
import {el} from '../dom.js';

const dot = (a, b) => a.reduce((sum, x, i) => sum + x * b[i], 0);
const axes = (azimuth, elevation) => {
    const az = azimuth * Math.PI / 180;
    const el = elevation * Math.PI / 180;
    return [[Math.cos(az), 0, -Math.sin(az)],
        [-Math.sin(az) * Math.sin(el), Math.cos(el), -Math.cos(az) * Math.sin(el)],
        [Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)]];
};

export function projectGuide(points, azimuth, elevation, center) {
    const basis = axes(azimuth, elevation);
    return points.map(point => basis.map(row => dot(row, point.map((value, i) => value - center[i]))));
}

export const centerOf = points => [0, 1, 2].map(i =>
    (Math.min(...points.map(p => p[i])) + Math.max(...points.map(p => p[i]))) / 2);

export function editCanvas({points, dimensions, azimuth, elevation, center, tool, radius, update, history, keyboard}) {
    const width = 560, height = 360;
    const canvas = el('canvas', {width, height, class: 'garment-guide-canvas', tabIndex: 0,
        'aria-label': dimensions === 3 ? '3D point guide, projected from the selected view' : '2D garment guide',
        'aria-describedby': keyboard.id});
    const context = canvas.getContext('2d');
    let cursor = [width / 2, height / 2], last = cursor, pressed = false, frame;
    let current = points;
    const basis = axes(azimuth, elevation);
    const project = value => dimensions === 2 ? value :
        basis.map(row => dot(row, value.map((coordinate, i) => coordinate - center[i])));
    const reference = current.map(project);
    const minX = Math.min(...reference.map(p => p[0])), maxX = Math.max(...reference.map(p => p[0]));
    const minY = Math.min(...reference.map(p => p[1])), maxY = Math.max(...reference.map(p => p[1]));
    const span = Math.max((maxX - minX) / width, (maxY - minY) / height, .05) * 1.18;
    const origin = [(minX + maxX) / 2, (minY + maxY) / 2];
    const pixels = point => [width / 2 + (point[0] - origin[0]) / span, height / 2 - (point[1] - origin[1]) / span];
    const unproject = ([x, y], depth = 0) => {
        const plane = [origin[0] + (x - width / 2) * span, origin[1] - (y - height / 2) * span];
        if (dimensions === 2) return plane;
        return center.map((value, i) => value + basis[0][i] * plane[0] + basis[1][i] * plane[1] + basis[2][i] * depth);
    };
    function draw() {
        context.clearRect(0, 0, width, height);
        const style = getComputedStyle(canvas);
        context.fillStyle = style.getPropertyValue('--muted').trim() || '#8db1a0';
        context.globalAlpha = .23;
        for (let x = 20; x < width; x += 20) {
            for (let y = 20; y < height; y += 20) context.fillRect(x, y, 1, 1);
        }
        context.globalAlpha = .86;
        context.fillStyle = style.color;
        for (const point of current) {
            const [x, y] = pixels(project(point));
            context.fillRect(x - 1.3, y - 1.3, 2.6, 2.6);
        }
        context.globalAlpha = 1;
        context.strokeStyle = style.color;
        context.beginPath();
        context.arc(cursor[0], cursor[1], radius(), 0, 2 * Math.PI);
        context.stroke();
    }
    function repaint() {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(draw);
    }
    function stroke() {
        const selected = tool();
        const r = radius();
        const screen = current.map(point => pixels(project(point)));
        const distance = ([x, y]) => (x - cursor[0]) ** 2 + (y - cursor[1]) ** 2;
        if (selected === 'erase') {
            const next = current.filter((_, i) => distance(screen[i]) > r * r);
            if (next.length >= 8) current = next;
        } else if (selected === 'move') {
            const dx = (cursor[0] - last[0]) * span, dy = -(cursor[1] - last[1]) * span;
            current = current.map((p, i) => distance(screen[i]) > r * r ? p : dimensions === 2
                ? [p[0] + dx, p[1] + dy]
                : p.map((coordinate, axis) => coordinate + basis[0][axis] * dx + basis[1][axis] * dy));
        } else if (current.length < 4096) {
            let nearest = 0;
            for (let i = 1; i < screen.length; i++) if (distance(screen[i]) < distance(screen[nearest])) nearest = i;
            const depth = dimensions === 3 ? project(current[nearest])[2] : 0;
            const added = [];
            for (let x = -r; x <= r; x += 6) {
                for (let y = -r; y <= r; y += 6) {
                    if (x * x + y * y > r * r) continue;
                    const xy = [cursor[0] + x, cursor[1] + y];
                    if (screen.some(([sx, sy]) => (sx - xy[0]) ** 2 + (sy - xy[1]) ** 2 < 10)) continue;
                    added.push(unproject(xy, depth));
                }
            }
            current = current.concat(added).slice(0, 4096);
        }
        update(current);
        last = cursor;
    }
    const location = event => {
        const rect = canvas.getBoundingClientRect();
        return [(event.clientX - rect.x) * width / rect.width, (event.clientY - rect.y) * height / rect.height];
    };
    canvas.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        canvas.focus({preventScroll: true});
        canvas.setPointerCapture(event.pointerId);
        history(current);
        pressed = true;
        last = cursor = location(event);
        stroke();
        repaint();
    });
    canvas.addEventListener('pointermove', event => {
        cursor = location(event);
        if (pressed) stroke();
        repaint();
    });
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        canvas.addEventListener(event, () => {pressed = false;});
    }
    canvas.addEventListener('keydown', event => {
        const arrows = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
        const delta = arrows[event.key];
        if (delta) {
            event.preventDefault();
            last = cursor;
            cursor = cursor.map((value, i) => Math.max(0, Math.min(i ? height : width, value + delta[i] * 9)));
            if (event.shiftKey && tool() === 'move') {history(current);stroke();}
        } else if (event.key === ' ' || event.key === 'Enter') {
            event.preventDefault();
            history(current);
            stroke();
        }
        repaint();
    });
    repaint();
    return canvas;
}

