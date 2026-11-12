"""COLMAP's documented world-to-camera convention; no AliceVision axis rules."""
import numpy as np
from scipy.spatial.transform import Rotation


def image_records(text_folder):
    lines = iter((text_folder / 'images.txt').read_text().splitlines())
    for line in lines:
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split(maxsplit=9)
        next(lines, None)  # The second line holds 2D/3D correspondences, possibly empty.
        yield fields


def read_camera(text_folder, image_name):
    cameras = {}
    for line in (text_folder / 'cameras.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        p = line.split()
        cameras[int(p[0])] = (p[1], int(p[2]), int(p[3]), np.array(p[4:], dtype=float))
    for p in image_records(text_folder):
        if p[9] != image_name:
            continue
        q = np.array(p[1:5], dtype=float)
        rotation = Rotation.from_quat(q[[1, 2, 3, 0]]).as_matrix()
        translation = np.array(p[5:8], dtype=float)
        model, width, height, params = cameras[int(p[8])]
        if model == 'PINHOLE':
            fx, fy, cx, cy = params
        elif model == 'SIMPLE_PINHOLE':
            fx, cx, cy = params
            fy = fx
        else:
            raise ValueError('Use the undistorted PINHOLE model for refinement')
        return rotation, translation, np.array([fx, fy, cx, cy]), width, height
    raise ValueError(f'{image_name} has no registered camera; choose a registered reference frame')


def prepare(vertices, rotation):
    v = np.asarray(vertices, dtype=float)
    basis = rotation.T @ np.diag([1., -1., -1.])
    center = (v.min(0) + v.max(0)) * .5
    oriented = (v - center) @ basis
    span = np.ptp(oriented, axis=0).max()
    if not np.isfinite(oriented).all() or span <= 0:
        raise ValueError('Invalid reconstruction extent')
    transform = dict(basis=basis.tolist(), center=center.tolist(), scale=float(.96 / span))
    return oriented * transform['scale'], transform


def project(vertices, rotation, translation, intrinsics):
    camera = np.asarray(vertices) @ rotation.T + translation
    if np.any(camera[:, 2] <= 0):
        raise ValueError('Mesh extends behind the reference camera; inspect reconstruction')
    return camera[:, :2] / camera[:, 2:] * intrinsics[:2] + intrinsics[2:]


def presentation_transform(vertices, basis, orient=True, ground=True):
    """Rigid export transform only: preserve distances and native working coordinates."""
    basis = np.asarray(basis, dtype=float) if orient else np.eye(3)
    if not np.allclose(basis.T @ basis, np.eye(3), atol=1e-6) or not np.isclose(np.linalg.det(basis), 1):
        raise ValueError('Export orientation must be a proper rotation')
    matrix = np.eye(4)
    matrix[:3, :3] = basis.T
    if ground:
        oriented = np.asarray(vertices) @ basis
        low, high = oriented.min(0), oriented.max(0)
        matrix[:3, 3] = [-(low[0]+high[0])/2, -low[1], -(low[2]+high[2])/2]
    return matrix
