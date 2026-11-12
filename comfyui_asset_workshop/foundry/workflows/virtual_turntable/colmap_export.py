"""Branch B presentation exports; reconstruction coordinates remain unchanged."""
import json
from pathlib import Path
import numpy as np
import trimesh
from comfy_api.latest import Types
from .references import CATEGORY
from .colmap_geometry import presentation_transform


def export_asset(scene, context, destination):
    scene = scene.copy()
    settings = context.get('presentation', dict(orientation='Reference camera up', ground=True,
                                               material='Matte', metallic=0., roughness=.8))
    vertices = np.vstack([g.vertices for g in scene.geometry.values()])
    matrix = presentation_transform(vertices, context['transform']['basis'],
                                    settings['orientation'] == 'Reference camera up', settings['ground'])
    scene.apply_transform(matrix)
    for geometry in scene.geometry.values():
        material = getattr(geometry.visual, 'material', None)
        if material is None:
            continue
        material = material.to_pbr() if hasattr(material, 'to_pbr') else material.copy()
        # glTF defaults missing metallicFactor to 1, unsuitable for most photo textures.
        if material.baseColorTexture is not None:
            material.baseColorFactor = [1., 1., 1., 1.]
        material.metallicFactor = settings['metallic']
        material.roughnessFactor = settings['roughness']
        material.doubleSided = False
        geometry.visual.material = material
    scene.export(str(destination), file_type='glb')
    receipt = dict(settings=settings, world_to_export=matrix.tolist(), bounds=scene.bounds.tolist(),
                   physical_scale='Unknown; reconstruction units preserved',
                   note='Y-up GLB; camera-aligned orientation is a presentation assumption, not gravity calibration. Native OBJ retains reconstruction coordinates.')
    Path(destination).with_suffix('.export.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return receipt


class ExportSettings:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'context': ('V360_REFINEMENT',),
            'orientation': (['Reference camera up', 'Native reconstruction axes'], {'tooltip': 'Use the selected reference camera to orient the asset upright; a tilted reference can still give a tilted asset.'}),
            'ground': ('BOOLEAN', {'default': True, 'tooltip': 'Center X/Z and place the lowest vertex at Y=0 in exported GLB files. Native working meshes stay unchanged.'}),
            'material': (['Matte', 'Satin', 'Glossy', 'Metal', 'Custom'], {'default': 'Satin'}),
            'custom_metallic': ('FLOAT', {'default': 0., 'min': 0., 'max': 1., 'step': .05}),
            'custom_roughness': ('FLOAT', {'default': .8, 'min': 0., 'max': 1., 'step': .05}),
        }}
    RETURN_TYPES = ('V360_REFINEMENT',)
    FUNCTION = 'settings'
    CATEGORY = CATEGORY

    def settings(self, context, orientation, ground, material, custom_metallic, custom_roughness):
        metallic, roughness = {'Matte': (0., .9), 'Satin': (0., .55), 'Glossy': (0., .15),
                               'Metal': (1., .3), 'Custom': (custom_metallic, custom_roughness)}[material]
        return ({**context, 'presentation': dict(orientation=orientation, ground=ground, material=material,
                                                metallic=metallic, roughness=roughness)},)


class PresentGeometry:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'model': ('FILE_3D',), 'context': ('V360_REFINEMENT',)}}
    RETURN_TYPES = ('FILE_3D',)
    FUNCTION = 'present'
    CATEGORY = CATEGORY

    def present(self, model, context):
        path = Path(model.get_source())
        scene = trimesh.load(str(path), force='scene', process=False)
        target = path.with_name(path.stem + '-upright.glb')
        export_asset(scene, context, target)
        return (Types.File3D(str(target)),)
