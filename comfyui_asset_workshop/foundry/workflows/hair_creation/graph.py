"""Native HairDeck templates, with a durable Foundry checkpoint at their boundary."""
import json
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def template():
    """The shipped independent branch also upgrades older user graphs in place."""
    source=Path(__file__).resolve().parents[3]/'workflows/Mumblebox 3D Asset Foundry.json'
    graph=json.loads(source.read_text(encoding='utf-8-sig'))
    ids={70000,70001,70002,70003,70004,70005}
    return dict(nodes=[n for n in graph['nodes'] if n['id'] in ids],
        links=[row for row in graph['links'] if row[1] in ids and row[3] in ids],
        groups=[g for g in graph['groups'] if g['title'].startswith('HAIR /')])


def generate(record, variant):
    c = record['config']
    return {
        '70000': {'class_type': 'FoundryLoadCreationImage', 'inputs': {'filename': c['image'], 'sha256': record['source_sha256']}},
        '70001': {'class_type': 'HairDeckLoader', 'inputs': {**c['checkpoints'], 'resources': 'hairdeck'}},
        '70002': {'class_type': 'FoundryHairGenerate', 'inputs': {'model': ['70001', 0], 'image': '',
                    'external_image': ['70000', 0], 'transparent_mask': ['70000', 1],
                    'seed': c['seed']+variant, 'steps': c['steps'], 'cfg': c['cfg'], 'generate_bones': c['bones'],'colors':c.get('colors',True)}},
        '70003': {'class_type': 'FoundryHairCheckpoint', 'inputs': {'result': ['70002', 0], 'creation_id': record['id'], 'variant': variant}}
    }


def export(record, checkpoint):
    return {'70004': {'class_type': 'FoundryHairExport', 'inputs': {'checkpoint': checkpoint,
              'options': json.dumps(record['config'], ensure_ascii=False)}}}


def rig(record, selected):
    return {
        '70001': {'class_type':'HairDeckLoader','inputs':{**record['config']['checkpoints'],'resources':'hairdeck'}},
        '70005': {'class_type':'FoundryHairRig','inputs':{'model':['70001',0],
            'checkpoint':record['variants'][selected]['checkpoint'],'creation_id':record['id'],'variant':selected}}
    }
