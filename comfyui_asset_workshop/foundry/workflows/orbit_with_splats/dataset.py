"""Prepare Brush views in the same grounded Y-up frame as the textured mesh."""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import least_squares, linear_sum_assignment
from scipy.spatial.transform import Rotation

# Inverse of ComfyUI Pixal3D's projection grid rotation.
Y_UP_FROM_PIXAL_POSE = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
COLMAP_CAMERA_AXES = np.diag([1, -1, -1])


def pick_views(views, limit, sharpness):
    """Assign unique frames to regularly spaced angles, favoring local detail."""
    count = min(limit, len(views))
    if count < 12:
        raise ValueError("At least 12 solved foreground views are needed for splat training.")
    angles = np.array([view["angle"] for view in views])
    scores = np.log1p([sharpness(view) for view in views])
    scores = np.clip((scores - np.percentile(scores, 15)) /
                     max(np.percentile(scores, 90) - np.percentile(scores, 15), 1e-6), 0, 1)
    targets = np.arange(count) * (360 / count)
    distance = abs((angles[None, :] - targets[:, None] + 180) % 360 - 180)
    weight = min(7., 180 / count)
    _, indices = linear_sum_assignment(distance + weight * (1 - scores))
    chosen = [views[i] for i in sorted(indices)]
    ordered = np.sort(angles[indices])
    gap = float(np.max(np.diff(np.r_[ordered, ordered[0] + 360])))
    if gap > 90:
        raise ValueError(f"Brush views leave a {gap:.0f} degree camera gap. Review the orbit and camera solve.")
    return chosen, gap


def shared_frame(views, mesh, grounding):
    """Fit uniform scale/translation against the masks, keeping solved rotation."""
    vertices = mesh.vertices.detach().cpu().numpy().reshape(-1, 3)
    if len(vertices) < 4 or not np.isfinite(vertices).all():
        raise ValueError("Alignment needs a finite mesh.")
    ground = np.asarray(grounding["matrix_y_up"], dtype=float)
    if ground.shape != (4, 4) or not np.isfinite(ground).all():
        raise ValueError("Expected a finite 4×4 mesh grounding matrix.")
    span = np.ptp(vertices, axis=0).max()
    if span <= 0:
        raise ValueError("Alignment needs a mesh with nonzero size.")
    # Keep extrema in the sample so thin features at the edges still count.
    chosen = np.random.default_rng(42).choice(len(vertices), min(4500, len(vertices)), replace=False)
    points = vertices[np.r_[chosen, vertices.argmin(axis=0), vertices.argmax(axis=0)]]
    check = views[::max(1, len(views) // 16)]
    poses = [view["transform_matrix"] for view in check]
    cam_centers = np.stack([Y_UP_FROM_PIXAL_POSE @ pose[:3, 3] for pose in poses])
    rotations = np.stack([(Y_UP_FROM_PIXAL_POSE @ pose[:3, :3] @ COLMAP_CAMERA_AXES).T for pose in poses])
    lens = np.stack([view["lens"] for view in check])
    boxes = np.array([view["bbox"] for view in check], dtype=float)
    width, height = (np.maximum(1, boxes[:, [2, 3]] - boxes[:, :2])).T
    denominator = np.stack((width, height, width, height), axis=1)

    def residual(parameters):
        scale = math.exp(parameters[0])
        centers = cam_centers * scale + parameters[1:]
        camera = np.einsum("vij,vnj->vni", rotations, points[None, :, :] - centers[:, None, :])
        depth = camera[..., 2]
        projected = camera[..., :2] / np.maximum(depth[..., None], 1e-5)
        projected = projected * lens[:, None, :2] + lens[:, None, 2:]
        bounds = np.concatenate((projected.min(axis=1), projected.max(axis=1)), axis=1)
        return ((bounds - boxes) / denominator).ravel()

    bound = max(0.4, float(span) * 0.55)
    fit = least_squares(residual, np.zeros(4), bounds=(
        [-0.7, -bound, -bound, -bound], [0.7, bound, bound, bound]),
        loss="soft_l1", f_scale=.06, max_nfev=35)
    return ground, math.exp(fit.x[0]), fit.x[1:], {
        "scale": math.exp(fit.x[0]), "translation_y_up": fit.x[1:].tolist(),
        "median_edge_error_fraction": float(np.median(np.abs(fit.fun))),
        "p90_edge_error_fraction": float(np.quantile(np.abs(fit.fun), .9)),
        "views_used": len(check),
    }


def prepare_dataset(root, cameras, mesh, grounding, front_frame, preset, ops):
    views = ops.records(cameras)
    if not views:
        raise ValueError("No registered frames with foreground masks.")
    front = views[0] if front_frame < 0 else next(
        (view for view in views if view["source_frame"] == front_frame), None)
    if front is None:
        raise ValueError("Use the same registered front frame for Pixal3D and the splat.")
    center = ops.normalized_poses(views, front)
    basis = (front["rotation"].T @ COLMAP_CAMERA_AXES) @ front["transform_matrix"][:3, :3].T
    world_offset = front["center"] - center
    normalized_offset = np.linalg.norm(front["transform_matrix"][:3, 3])
    source_span = np.linalg.norm(world_offset) / normalized_offset
    if not math.isfinite(source_span) or source_span <= 0:
        raise ValueError("Could not recover the Pixal3D world scale.")
    chosen, gap = pick_views(views, preset["views"], ops.masked_sharpness)
    ground, scale, offset, fit = shared_frame(chosen, mesh, grounding)

    # The linear part includes scale. Rotations use its unit-length equivalent.
    axes = ground[:3, :3] @ Y_UP_FROM_PIXAL_POSE @ basis.T
    conversion = scale / source_span
    translation = ground[:3, :3] @ offset + ground[:3, 3]

    images = root / "dataset" / "images"
    sparse = root / "dataset" / "sparse" / "0"
    images.mkdir(parents=True)
    sparse.mkdir(parents=True)
    camera_lines, image_lines, source_records = [], [], []
    sample_indices = set(np.linspace(0, len(chosen) - 1, min(12, len(chosen))).round().astype(int))
    tiles = Image.new("RGB", (960, 220 * math.ceil(len(sample_indices) / 4)), "#18201e")
    draw = ImageDraw.Draw(tiles)
    preview_index = 0
    for index, view in enumerate(chosen):
        ident = index + 1
        width, height = view["width"], view["height"]
        fx, fy, cx, cy = view["lens"]
        w2c = view["rotation"] @ axes.T
        c = conversion * axes @ (view["center"] - center) + translation
        qx, qy, qz, qw = Rotation.from_matrix(w2c).as_quat()
        tx, ty, tz = -w2c @ c
        camera_lines.append(f"{ident} PINHOLE {width} {height} {fx} {fy} {cx} {cy}")
        image_lines.extend([f"{ident} {qw} {qx} {qy} {qz} {tx} {ty} {tz} {ident} {view['file']}", ""])
        with Image.open(view["rgb"]) as color, Image.open(view["mask"]) as alpha:
            image = color.convert("RGBA")
            image.putalpha(alpha.convert("L"))
        image.save(images / view["file"])
        source_records.append({"file": view["file"], "source_frame": view["source_frame"],
                               "timestamp_seconds": view["timestamp_seconds"], "degrees": round(view["angle"], 2)})
        if index in sample_indices:
            image.thumbnail((230, 194))
            x, y = (preview_index % 4) * 240, (preview_index // 4) * 220
            tiles.paste(image, (x + (240 - image.width) // 2, y), image)
            draw.text((x + 8, y + 197), f"Frame {view['source_frame']}  /  {view['angle']:.0f} deg", fill="white")
            preview_index += 1

    point_lines = []
    for line in (Path(cameras["camera_text"]) / "points3D.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        point = line.split()
        xyz = conversion * axes @ (np.array(point[1:4], dtype=float) - center) + translation
        point_lines.append(" ".join([point[0], *map(str, xyz), *point[4:8]]))
    if len(point_lines) < 12:
        raise ValueError("The masked camera solve produced too few sparse points to seed Brush.")
    for name, lines in (("cameras.txt", camera_lines), ("images.txt", image_lines), ("points3D.txt", point_lines)):
        (sparse / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    matrix = np.eye(4)
    matrix[:3, :3] = conversion * axes
    matrix[:3, 3] = translation - matrix[:3, :3] @ center
    report = {"coordinates": "GLB Y-up; common mesh export ground transform",
              "colmap_to_output": matrix.tolist(), "grounding": grounding, "silhouette_fit": fit,
              "preset": preset, "largest_estimated_camera_gap_degrees": round(gap, 2),
              "source_frames": source_records, "sparse_seed_points": len(point_lines)}
    (root / "alignment.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    tiles.save(root / "training-views.jpg", quality=88)
    return tiles, report
