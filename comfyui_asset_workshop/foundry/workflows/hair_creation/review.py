"""English display metadata for actual HairDeck artifacts, shared by GUI and agents."""
from pathlib import PurePosixPath

IMAGE_LABELS = {
    'preview': ('result', 'HairDeck multi-view sheet'),
    'model_input': ('input', 'Model input crop'),
    'preprocess': ('input', 'HairDeck processing sheet'),
    'hair_mask': ('input', 'Detected hair'),
    'face_mask': ('input', 'Detected face'),
    'base_color': ('material', 'Base color and opacity'),
    'normal': ('material', 'Strand normal map'),
    'roughness': ('material', 'Roughness'),
    'metallic_roughness': ('material', 'glTF metallic and roughness'),
    'unity_metallic_smoothness': ('material', 'Unity metallic and smoothness'),
    'alpha': ('material', 'Opacity'),
    'uv_layout': ('material', 'UV layout for painting'),
}


def displays(files):
    """Never invent a preview; all paths originate in upstream's saved-file manifest."""
    result = []
    for entry in files:
        name = PurePosixPath(entry['filename'])
        if name.suffix.lower() != '.png':
            continue
        role = next((key for key in IMAGE_LABELS if name.stem == key or name.stem.startswith(key + '_0')), None)
        if role:
            group, label = IMAGE_LABELS[role]
            result.append(dict(role=role, group=group, label=label,
                               path=entry['subfolder'] + '/' + entry['filename']))
    return result
