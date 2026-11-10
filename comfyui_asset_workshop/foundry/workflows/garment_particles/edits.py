"""Bounded author-guided garment inputs."""
import math

from .contract import identifier, options

OPERATIONS = ('pattern', 'silhouette', 'shape', 'completion', 'mix', 'blend')


def bounded(value, low, high, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label} must be between {low} and {high}.')
    return float(value)


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be a whole number between {low} and {high}.')
    return value


def coordinates(value, size):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError('The garment guide has an invalid point.')
    return [round(bounded(item, -2000, 2000, 'Guide coordinate'), 3) for item in value]


def edit_options(data):
    if not isinstance(data, dict):
        raise ValueError('Choose one garment edit.')
    operation = data.get('operation')
    if operation not in OPERATIONS:
        raise ValueError('Choose an editing mode.')
    result = {'operation': operation}
    if operation == 'blend':
        result.update(second_seed=integer(data.get('second_seed'), 0, 2147483647, 'Second seed'),
                      blend=bounded(data.get('blend', .5), 0, 1, 'Blend amount'))
        if 'second_points' in data:
            result['second_points'] = integer(data['second_points'], 100, 8192, 'Second point count')
        return result
    guide = data.get('guide')
    if not isinstance(guide, list) or not 8 <= len(guide) <= 4096:
        raise ValueError('Use 8 to 4,096 guide points.')
    dim = 2 if operation in ('pattern', 'silhouette') else 3
    objective = 'completion' if operation in ('completion', 'mix') else 'reconstruction'
    if dim == 2:
        objective = data.get('objective', objective)
        if objective not in ('completion', 'reconstruction'):
            raise ValueError('Choose whether to match the guide or fill missing areas.')
        result['objective'] = objective
    result.update(guide=[coordinates(point, dim) for point in guide],
                  strength=bounded(data.get('strength', .7), .1, .95, 'Follow edit'),
                  rate=bounded(data.get('rate', .015 if objective == 'completion' else .05), .005, .1, 'Learning rate'),
                  iterations=integer(data.get('iterations', 8 if objective == 'completion' else 2), 1, 10, 'Edit passes'),
                  steps=integer(data.get('steps', 100), 20, 1000, 'Guidance steps'))
    if operation == 'silhouette':
        result.update(azimuth=bounded(data.get('azimuth', 0), -180, 180, 'Horizontal view'),
                      elevation=bounded(data.get('elevation', 0), -85, 85, 'Vertical view'),
                      center=coordinates(data.get('center', [0, 0, 0]), 3))
    return result


def edit_generation(data, previous):
    prompt = str(data.get('prompt', '')).strip()
    return options({**previous, **{key: data[key] for key in ('seed', 'points', 'steps') if key in data},
                    'mode': 'text' if prompt else 'surprise', 'prompt': prompt,
                    'image': '', 'back_image': ''})


def root_id(run):
    return identifier(run.get('root', run['id']))

