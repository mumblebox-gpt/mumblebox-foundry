"""Coordinate contract between AliceVision OBJ exports and a reference camera.

AliceVision exports OBJ with Y/Z negated. Its SfM pose rotation is camera-to-world.
All arrays here use row vectors; retain the inverse rather than guessing export axes.
"""
import numpy as np


def prepare_frame(vertices, rotation):
    vertices = np.asarray(vertices, dtype=np.float64)
    r = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    if not np.allclose(r.T @ r, np.eye(3), atol=1e-5) or np.linalg.det(r) < .999:
        raise ValueError("Reference camera must have a proper orthonormal rotation")
    d = np.diag([1., -1., -1.])
    basis = d @ r @ d
    center = (vertices.min(0) + vertices.max(0)) * .5
    oriented = (vertices - center) @ basis
    span = np.ptp(oriented, axis=0).max()
    if not np.isfinite(oriented).all() or span <= 1e-12:
        raise ValueError("Mesh has no finite extent")
    frame = {"basis": basis.tolist(), "center": center.tolist(), "scale": float(.96 / span)}
    return oriented * frame["scale"], frame


def restore_frame(vertices, frame):
    return (np.asarray(vertices) / frame["scale"]) @ np.asarray(frame["basis"]).T + frame["center"]


def project_obj(vertices, rotation, camera_center, focal_pixels, width, height):
    d = np.array([1., -1., -1.])
    camera = (np.asarray(vertices) * d - camera_center) @ np.asarray(rotation).reshape(3, 3)
    if np.any(camera[:, 2] <= 0):
        raise ValueError("Mesh is behind the selected camera; check coordinate convention")
    return camera[:, :2] / camera[:, 2:] * focal_pixels + [width / 2, height / 2]
