"""Bridge masked COLMAP images and solved cameras to native Pixal3D conditioning."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import linear_sum_assignment

from ..virtual_turntable.colmap_geometry import image_records, read_camera
from ..virtual_turntable.colmap_openmvs import Reconstruct
from ..virtual_turntable.processes import release_models
CATEGORY = 'Foundry/Orbit to Mesh'

TARGETS = {
    "2": (0, 135),
    "4": (0, 90, 180, 270),
    "6": (0, 60, 120, 180, 240, 300),
    "8 (experimental)": (0, 45, 90, 135, 180, 225, 270, 315),
}


class SolvePixalCameras:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "frame_set": ("V360_FRAMESET",),
            "camera_calibration": (["Auto fit lens", "Keep chosen lens"],),
            "initial_fov": ("FLOAT", {"default": 20.0, "min": 2.0, "max": 120.0}),
            "max_features": ("INT", {"default": 10000, "min": 1024, "max": 40000}),
            "gpu_features": ("BOOLEAN", {"default": True}),
            "cpu_threads": ("INT", {"default": 8, "min": 1, "max": 64}),
            "timeout_minutes": ("INT", {"default": 20, "min": 1, "max": 180}),
        }}

    RETURN_TYPES = ("V360_PIXAL_CAMERAS",)
    RETURN_NAMES = ("registered_frames_and_cameras",)
    FUNCTION = "solve"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def solve(self, frame_set, camera_calibration, initial_fov, max_features,
              gpu_features, cpu_threads, timeout_minutes):
        solved = Reconstruct().reconstruct(
            # An undistorted generated video has square pixels. Solving fx and fy
            # independently can fit synthetic motion by stretching the subject.
            frame_set=frame_set, camera_model="SIMPLE_PINHOLE", shared_camera=True,
            initial_focal_factor=1 / (2 * math.tan(math.radians(initial_fov) / 2)),
            gpu_features=gpu_features, gpu_index=0, max_features=max_features,
            depth_downscale=1, max_resolution=max(frame_set["width"], frame_set["height"]),
            neighbor_views=5, refine_mesh=False, refine_on_gpu=False,
            texture_size=1024, cpu_threads=cpu_threads, timeout_minutes=timeout_minutes,
            advanced_overrides="{}", camera_calibration=camera_calibration,
            initial_fov=initial_fov, camera_only=True)
        manifest = Path(solved["camera_text"]).parent / "foundry-cameras.json"
        manifest.write_text(json.dumps(solved), encoding="utf-8")
        return {"ui": {"text": [str(manifest)]}, "result": (solved,)}


def unit(v):
    length = np.linalg.norm(v)
    if length < 1e-8:
        raise ValueError("Camera solve has a degenerate orbit axis")
    return v / length


def records(solved):
    folder = Path(solved["camera_text"])
    source_indices = solved["frame_set"]["source_indices"]
    views = []
    for record in sorted(image_records(folder), key=lambda row: row[9]):
        name = record[9]
        pose, translation, lens, width, height = read_camera(folder, name)
        fx, fy, cx, cy = lens
        if not np.isfinite(lens).all() or fx <= 0 or not math.isclose(fx, fy, rel_tol=0.001):
            raise ValueError(f"Camera {name} does not have valid square-pixel intrinsics")
        rgb, mask = (Path(solved[key]) / name for key in ("images", "masks"))
        with Image.open(mask) as image:
            if image.size != (width, height):
                raise ValueError(f"Camera and mask dimensions differ for {name}")
            box = image.convert("L").point(lambda v: 255 if v >= 128 else 0).getbbox()
        if not box:
            continue
        left, top, right, bottom = box
        direction = unit(pose.T @ np.array([((left + right) / 2 - cx) / fx,
                                            ((top + bottom) / 2 - cy) / fy, 1.0]))
        source_frame = source_indices[int(Path(name).stem.split("_")[-1])]
        views.append({"file": name, "source_frame": source_frame, "rgb": rgb, "mask": mask,
                      "rotation": pose, "center": -pose.T @ translation, "ray": direction,
                      "width": width, "height": height, "lens": lens, "bbox": box})
    return sorted(views, key=lambda view: view["source_frame"])


def normalized_poses(views, anchor):
    """Map COLMAP +X right/+Y down/+Z forward to a centered Z-up OpenGL camera rig."""
    rays = np.stack([v["ray"] for v in views])
    centers = np.stack([v["center"] for v in views])
    projection = np.eye(3) - rays[:, :, None] * rays[:, None, :]
    center, _, rank, _ = np.linalg.lstsq(projection.sum(0),
                                         np.einsum("nij,nj->i", projection, centers),
                                         rcond=None)
    if rank != 3 or not np.isfinite(center).all():
        raise ValueError("Camera solve did not establish a 3D subject center")
    depth = float(anchor["rotation"][2] @ (center - anchor["center"]))
    if depth <= 0:
        raise ValueError("The solved subject center is behind the front camera")
    fx, fy, _, _ = anchor["lens"]
    left, top, right, bottom = anchor["bbox"]
    span = max((right - left) * depth / fx, (bottom - top) * depth / fy)
    if not math.isfinite(span) or span <= 1e-8:
        raise ValueError("Front mask cannot establish subject scale")

    up = unit(-np.mean([v["rotation"][1] for v in views], axis=0))
    front = anchor["center"] - center
    forward = -unit(front - up * np.dot(front, up))
    basis = np.column_stack((unit(np.cross(forward, up)), forward, up))
    for view in views:
        pose = np.eye(4)
        pose[:3, :3] = basis.T @ view["rotation"].T @ np.diag([1, -1, -1])
        pose[:3, 3] = basis.T @ (view["center"] - center) / span
        x, y, _ = pose[:3, 3]
        view["transform_matrix"] = pose
        view["angle"] = 0.0 if view is anchor else math.degrees(math.atan2(x, -y)) % 360
    return center


def angular_error(actual, target):
    return abs((actual - target + 180) % 360 - 180)


def select_views(views, preset, exclude, front_frame, max_angle_error, sharpness_window=0.):
    if not views:
        raise ValueError("No registered views have usable masks")
    anchor = next((v for v in views if v["source_frame"] == front_frame), None) if front_frame >= 0 else views[0]
    if anchor is None:
        raise ValueError(f"Front source frame {front_frame} has no solved camera")
    normalized_poses(views, anchor)
    candidates = [v for v in views if v is not anchor and v["source_frame"] not in exclude]
    targets = TARGETS[preset]
    if len(candidates) < len(targets) - 1:
        raise ValueError("Too few registered cameras for this preset. Select a smaller preset.")
    errors = np.array([[angular_error(v["angle"], target) for v in candidates]
                       for target in targets[1:]])
    costs = errors.copy()
    if sharpness_window:
        scores = np.array([masked_sharpness(view) for view in candidates])
        scores = (scores - scores.min()) / max(1e-8, scores.max() - scores.min())
        near_target = (errors <= errors.min(axis=1, keepdims=True) + sharpness_window)
        costs -= sharpness_window * scores[None, :] * near_target * (errors <= max_angle_error)
    rows, columns = linear_sum_assignment(costs)
    picked = [(0, anchor, 0.0), *[(targets[i+1], candidates[j], float(errors[i, j]))
                                  for i, j in zip(rows, columns)]]
    if any(error > max_angle_error for target, view, error in picked
           if view["source_frame"] not in exclude):
        raise ValueError("The solved orbit does not cover every target. Review the orbit or choose fewer views.")
    selected = [(target, view, error) for target, view, error in picked
                if view["source_frame"] not in exclude]
    if len(selected) < 2:
        raise ValueError("Keep at least two solved views. Clear exclusions or choose a larger preset.")
    return selected


def rectified_image(view, side=1024):
    """Square, centered, equal-pixel-focal pinhole; preserve the solved rays."""
    fx, fy, cx, cy = view["lens"]
    w, h = view["width"], view["height"]
    focal = side / (2 * max(cx/fx, (w-cx)/fx, cy/fy, (h-cy)/fy))
    ax, ay = fx/focal, fy/focal
    affine = (ax, 0, cx - ax*side/2, 0, ay, cy - ay*side/2)
    with Image.open(view["rgb"]) as rgb, Image.open(view["mask"]) as mask:
        if rgb.size != mask.size or rgb.size != (w, h):
            raise ValueError(f"RGB, mask and camera dimensions differ for {view['file']}")
        image = rgb.convert("RGB").transform((side, side), Image.Transform.AFFINE, affine,
                                             resample=Image.Resampling.BICUBIC)
        alpha = mask.convert("L").transform((side, side), Image.Transform.AFFINE, affine,
                                           resample=Image.Resampling.BILINEAR)
    image.putalpha(alpha)
    return image, 2 * math.atan(side / (2*focal))


def masked_sharpness(view):
    with Image.open(view["rgb"]) as image, Image.open(view["mask"]) as mask:
        gray = np.asarray(image.convert("L"), dtype=np.float32)
        subject = np.asarray(mask.convert("L")) > 128
    interior = (subject[1:-1, 1:-1] & subject[1:-1, :-2] &
                subject[1:-1, 2:] & subject[:-2, 1:-1] & subject[2:, 1:-1])
    laplacian = gray[1:-1, :-2] + gray[1:-1, 2:] + gray[:-2, 1:-1] + gray[2:, 1:-1] - 4 * gray[1:-1, 1:-1]
    return float(laplacian[interior].var()) if interior.any() else 0.


class LoadCameras:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"manifest": ("STRING",)}}

    RETURN_TYPES = ("V360_PIXAL_CAMERAS",)
    FUNCTION = "load"
    CATEGORY = CATEGORY

    def load(self, manifest):
        from folder_paths import get_output_directory
        from ...artifacts import owned_path

        root = Path(get_output_directory())
        value = json.loads(owned_path(root, manifest).read_text(encoding="utf-8"))
        for key in ("camera_text", "images", "masks"):
            owned_path(root, value[key])
        return (value,)


class PixalViews:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "cameras": ("V360_PIXAL_CAMERAS",),
            "preset": (list(TARGETS), {"default": "4"}),
            "front_frame": ("INT", {"default": -1, "min": -1, "max": 17999,
                          "tooltip": "-1 uses the first registered frame from the front-anchored orbit."}),
            "max_angle_error": ("FLOAT", {"default": 35.0, "min": 5.0, "max": 60.0}),
            "sharpness_window": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 20.0}),
        }}

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("transforms_json", "labeled_contact_sheet")
    FUNCTION = "prepare"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def prepare(self, cameras, preset, front_frame, max_angle_error, sharpness_window):
        import torch

        picked = select_views(records(cameras), preset, set(), front_frame, max_angle_error, sharpness_window)
        identity = [(target, view["source_frame"]) for target, view, _ in picked]
        digest = hashlib.sha256(json.dumps([identity, preset, front_frame, max_angle_error, sharpness_window]).encode()).hexdigest()[:12]
        directory = Path(cameras["camera_text"]).parent / ("pixal-views-" + digest)
        directory.mkdir(exist_ok=True)
        sheet = Image.new("RGB", (4*256, math.ceil(len(picked)/4)*274), "#262e2d")
        draw = ImageDraw.Draw(sheet)
        frames = []
        for index, (target, view, error) in enumerate(picked):
            image, fov = rectified_image(view)
            image.save(directory / view["file"])
            pose = view["transform_matrix"].tolist()
            frames.append({"file_path": view["file"], "source_frame": view["source_frame"],
                           "target_degrees": target, "solved_degrees": view["angle"],
                           "target_error_degrees": error, "camera_angle_x": fov, "transform_matrix": pose})
            x, y = (index % 4)*256, (index // 4)*274
            tile = image.resize((256, 248))
            sheet.paste(tile, (x, y), tile.getchannel("A"))
            heading = "FRONT  " if index == 0 else ""
            draw.text((x+6, y+252), f"{heading}Frame {view['source_frame']} | {view['angle']:.1f} deg", fill="white")
        manifest = {"mesh_scale": 1.0, "registered_views": cameras["registered"],
                    "preset": preset, "frames": frames}
        path = directory / "transforms.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"ui": {"text": [str(path)]}, "result": (
            str(path), torch.from_numpy(np.asarray(sheet).copy())[None].float()/255)}


class PosedPixalConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip_vision_model": ("CLIP_VISION",),
                             "manifest": ("STRING", {"forceInput": True}),
                             "exclude_source_frames": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("positive", "negative")
    FUNCTION = "condition"
    CATEGORY = CATEGORY

    def condition(self, clip_vision_model, manifest, exclude_source_frames):
        import torch
        from comfy_extras.nodes_trellis2 import _build_pixal3d_conditioning

        release_models()
        from folder_paths import get_output_directory
        from ...artifacts import owned_path

        root = Path(get_output_directory())
        path = owned_path(root, manifest)
        excluded = {int(value) for value in exclude_source_frames.split(",") if value.strip()}
        frames = json.loads(path.read_text(encoding="utf-8"))["frames"]
        selected = [frame for frame in frames if frame["source_frame"] not in excluded]
        if len(selected) < 2 or selected[0] != frames[0] or not excluded.issubset({frame["source_frame"] for frame in frames}):
            raise ValueError("Keep the front view and at least one other view.")
        images = []
        for frame in selected:
            with Image.open(owned_path(path.parent, path.parent / frame["file_path"])) as image:
                rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255
            images.append(rgba[..., :3] * rgba[..., 3:4])
        frames = selected
        condition = _build_pixal3d_conditioning(
            clip_vision_model, torch.from_numpy(np.stack(images)),
            torch.tensor([f["transform_matrix"] for f in frames], dtype=torch.float32),
            torch.tensor([f["camera_angle_x"] for f in frames], dtype=torch.float32),
            torch.ones(1), num_views=len(frames))
        return tuple(condition.result)

NODE_CLASS_MAPPINGS = {
    "FoundryOrbitSolveCameras": SolvePixalCameras,
    "FoundryOrbitLoadCameras": LoadCameras,
    "FoundryOrbitSelectViews": PixalViews,
    "FoundryOrbitPixalConditioning": PosedPixalConditioning,
}
