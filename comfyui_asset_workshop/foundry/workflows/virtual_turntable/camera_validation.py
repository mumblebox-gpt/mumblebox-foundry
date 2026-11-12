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
