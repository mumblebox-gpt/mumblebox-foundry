"""Frozen Foundry concept wording and separately versioned enhancement roles."""
import json
from pathlib import Path
from .contracts import view_records

SOURCE = Path(__file__).resolve().parents[1] / 'sources' / 'turnaround-prompts.json'
# The author's connection diagram and published native T8/Fisher examples use
# original=image1, coarse guide=image2 with this exact counterintuitive wording.
# Keep the slot order and trigger together; see docs/enhancement-handoff-findings.md.
TRIGGER = 'Change the camera angle from <image2> to <image1>.'


def concept(spec):
    frozen=json.loads(SOURCE.read_text(encoding='utf-8'))
    category=spec['category']
    prompt=(frozen['CHARACTER_PROMPT'] if category=='characters' else
            frozen['OBJECT_PROMPT'].format(subject=frozen['SUBJECTS'][category])+' '+frozen['CATEGORY_DETAILS'][category])
    description=' '.join(x.strip() for x in (spec['asset_description'],spec['special_instructions']) if x.strip())
    if description:
        prompt += ('\n\nReference instructions: <image1> is the primary overall asset. '
                   'Additional references apply only to the described part or view; keep other primary details unchanged.\n'
                   '<image1>: '+description)
    return prompt


def enhancement(spec, view_id):
    override=spec.get('view_overrides',{}).get(view_id,{})
    view=next(v for v in view_records(spec) if v['id']==view_id)
    a=view['azimuth_deg']%360
    if view_id=='top':
        pair=('front','back')
    else:
        pair=('back' if 90<a<270 else 'front', 'right' if 0<=a<180 else 'left')
    refs=[dict(key='appearance', description='Overall asset identity, palette and materials; not the target camera.'),
          dict(key='render:'+view_id,description='Target Blender camera, framing, layout, proportions and occlusion.'),
          *[dict(key='concept:'+side,description=f'{side.title()} concept art: intended colors, materials and surface details; not measured geometry or target camera.') for side in pair]]
    refs += [dict(key='extra:'+str(i),description=(
        'Supplementary appearance/detail reference only. Apply only the described contribution: '+r['description'].strip()+
        '. Do not copy its camera, framing, background or unrelated objects. Keep the target Blender guide.'))
        for i,r in enumerate(spec['extra_references'])]
    text=TRIGGER+'\n'+override.get('enhancement_suffix',spec['enhancement_suffix'])
    text+='\nAsset description: '+spec['asset_description']
    if spec['special_instructions'].strip():
        text+='\nPreserve and apply: '+spec['special_instructions'].strip()
    if override.get('special_instructions','').strip():
        text+='\nThis view specifically: '+override['special_instructions'].strip()
    text+='\nReference roles:\n'+'\n'.join(f'<image{i}>: {ref["description"]}' for i,ref in enumerate(refs,1))
    return text,refs


def sheet_enhancement(spec):
    refs=[dict(key='guide:sheet',description='The editing canvas: four measured Blender camera frames and black separator gutters.'),
          dict(key='appearance',description='Original identity, materials, palette and ornament; appearance reference.'),
          dict(key='concept:sheet',description='Concept appearance around this same object; colors and surface details, with approximate geometry.')]
    refs += [dict(key='extra:'+str(i),description='Apply only this appearance contribution: '+r['description'].strip())
             for i,r in enumerate(spec['extra_references'])]
    text=('Edit <image1> in place into a coherent finished product rendering sheet. All four panels depict the same object. '
          'The top-left panel is front, top-right is right side, bottom-left is back, bottom-right is left side, '
          'each from its existing slightly elevated camera. Preserve the exact panel boundaries and black separator gutters. '
          'Keep every object at its existing position, size and tilt inside its own panel. Preserve each panel silhouette, '
          'body proportions, camera perspective, visible surfaces, attachment positions and occlusion from <image1>. '
          'Restore crisp finished materials, colors and surface ornament using <image2> for identity and <image3> for appearance around the object. '
          'Keep the neutral gray panel backgrounds and black gutters unchanged, with one complete object in each panel. '
          'Keep details attached to the corresponding surfaces and consistent across views; rear-facing surfaces retain rear-facing presentation. '
          'The appearance references supply material and detail contributions; the four existing panels supply all target viewpoints and framing. '
          'Asset description: '+spec['asset_description'].strip()+'. ')
    if spec['special_instructions'].strip():text+='Appearance preservation instructions: '+spec['special_instructions'].strip()+'. '
    if spec['enhancement_suffix'].strip():text+='Additional preservation instructions: '+spec['enhancement_suffix'].strip()+'. '
    if spec.get('structure_control','off')!='off':
        text+='The structural condition supplies matching '+('depth' if spec['structure_control']=='depth' else 'edges')+' for these exact four panels. '
        if spec['mask_mode']=='foreground':text+='The edit mask identifies the object region to finish. '
        text+='Transfer appearance onto the corresponding visible surfaces; preserve the primary geometry and each existing viewpoint. '
    if spec.get('repair_enabled'):
        text+=('The guide supplies the camera, outer silhouette and major body proportions. Rebuild rough proxy surface '
               'details as finished materials and ornament from the appearance references; do not interpret proxy noise '
               'or faceting as intentional decoration. Structural depth can still constrain geometry; any incorrect '
               'controlled surface requires a separate masked correction. ')
    text+='Reference roles: '+' '.join(f'<image{i}>: {r["description"]}' for i,r in enumerate(refs,1))
    return text,refs


def repair_prompt(spec,view_id):
    view=next(v for v in view_records(spec) if v['id']==view_id)
    return (f'Finish the existing single {view_id} view of this same asset at azimuth {view["azimuth_deg"]} degrees '
        f'and elevation {view["elevation_deg"]} degrees. <image1> is the exact target frame with the masked region hidden; '
        'keep its viewpoint, object position, silhouette, major proportions and surrounding attached parts. '
        '<image2> supplies original identity and materials. <image3> supplies intended appearance for this side, '
        'not a replacement viewpoint. Rebuild the masked region into the described finished surface. Do not restore '
        'the faulty proxy pattern or copy the reference camera. Produce one complete image, no sheet, text or border. '
        'Whole asset: '+spec['asset_description']+'. '+spec['special_instructions']+' '
        'Target image and correction: '+spec['repair_requests'][view_id]['prompt'])
