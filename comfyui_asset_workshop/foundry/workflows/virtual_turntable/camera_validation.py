"""Numerical camera checks for the native Meshroom boundary before dense depth."""
import math


def inspect_cameras(data, minimum_fov=2.0, maximum_fov=120.0):
    if not (0 < minimum_fov < maximum_fov < 180):
        raise ValueError('Camera check limits must satisfy 0 < minimum FOV < maximum FOV < 180.')
    errors = []
    cameras = []
    valid_intrinsics = set()
    for intrinsic in data.get('intrinsics', []):
        camera_id = str(intrinsic.get('intrinsicId', 'unknown'))
        try:
            focal = float(intrinsic['focalLength'])
            sensor = float(intrinsic['sensorWidth'])
            if not (math.isfinite(focal) and focal > 0 and math.isfinite(sensor) and sensor > 0):
                raise ValueError('non-finite or non-positive focal length/sensor width')
            fov = math.degrees(2 * math.atan(sensor / (2 * focal)))
            for value in intrinsic.get('distortionParams', []) + intrinsic.get('principalPoint', []):
                if not math.isfinite(float(value)):
                    raise ValueError('non-finite distortion or principal point')
            cameras.append({'intrinsic_id': camera_id, 'focal_length_mm': focal,
                            'horizontal_fov_degrees': round(fov, 6)})
            valid_intrinsics.add(camera_id)
            if fov < minimum_fov - 1e-6 or fov > maximum_fov + 1e-6:
                errors.append(f'Camera {camera_id}: estimated horizontal FOV {fov:.3f} degrees is outside '
                              f'the selected {minimum_fov:g}-{maximum_fov:g} degree check range.')
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f'Camera {camera_id} has invalid calibration: {exc}.')
    pose_ids = set()
    for pose in data.get('poses', []):
        try:
            transform = pose['pose']['transform']
            values = transform['rotation'] + transform['center']
            if len(values) != 12 or not all(math.isfinite(float(value)) for value in values):
                raise ValueError('invalid rotation or camera center')
            pose_ids.add(str(pose['poseId']))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f'Invalid camera pose: {exc}.')
    views = data.get('views', [])
    calibrated = sum(str(view.get('poseId')) in pose_ids and
                     str(view.get('intrinsicId')) in valid_intrinsics for view in views)
    if calibrated < 3:
        errors.append(f'Only {calibrated} views have a valid camera pose and calibration; at least 3 are required.')
    return {'passed': not errors, 'errors': errors, 'cameras': cameras,
            'calibrated_views': calibrated, 'input_views': len(views),
            'fov_check_range_degrees': [minimum_fov, maximum_fov],
            'limitation': 'Passing these numerical checks does not prove camera accuracy, rigid views or usable mesh quality.'}

def orbit_coverage(frame_set, camera_centers):
    """Measure the gap around the fitted camera plane, in solver coordinates."""
    import numpy as np

    matched = [(index, camera_centers[f"frame_{index:05d}.png"])
               for index in range(frame_set["count"]) if f"frame_{index:05d}.png" in camera_centers]
    result = {"input_frames": frame_set["count"], "registered_frames": len(matched)}
    if len(matched) < 3:
        return result
    centers = np.array([center for _, center in matched], dtype=float)
    if centers.shape != (len(matched), 3) or not np.isfinite(centers).all():
        return result
    centered = centers - centers.mean(axis=0)
    _, scales, axes = np.linalg.svd(centered, full_matrices=False)
    if scales[0] <= 1e-12 or scales[1] <= scales[0] * .02:
        return result
    xy = centered @ axes[:2].T
    # Fit the circle center. The sample mean can sit off-center if some
    # sectors are missing or the clip slows down near one angle.
    fitted, _, rank, _ = np.linalg.lstsq(
        np.column_stack((2 * xy, np.ones(len(xy)))), (xy ** 2).sum(axis=1), rcond=None)
    if rank < 3:
        return result
    directions = xy - fitted[:2]
    angles = np.sort(np.arctan2(directions[:, 1], directions[:, 0]))
    gap = np.degrees(np.diff(np.r_[angles, angles[0] + 2 * np.pi]).max())
    timing = frame_set.get("source_video", {}).get("timestamps_seconds")
    result.update(
        largest_gap_degrees=round(float(gap), 1),
        registered_source_frames=[frame_set["source_indices"][i] for i, _ in matched],
    )
    if timing:
        result["registered_timestamps_seconds"] = [timing[i] for i, _ in matched]
    return result


def alicevision_centers(data):
    poses = {str(pose["poseId"]): pose["pose"]["transform"]["center"] for pose in data["poses"]}
    return {view["path"].replace("\\", "/").rsplit("/", 1)[-1]: poses[str(view["poseId"])]
            for view in data["views"] if str(view["poseId"]) in poses}
