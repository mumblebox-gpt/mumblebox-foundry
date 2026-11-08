"""Durable image-to-mesh provenance, independent of Gallery entry lifetime."""
import json
import uuid
from .library import identifier
from .package import provenance


def save_handoff(library,record,references):
    receipt=uuid.uuid4().hex
    images=[]
    for reference,fallback in zip(references,('front','back')):
        side=reference.get('id') if reference.get('id') in ('single','front','back') else fallback
        revision=library.revision(record,record['accepted'][side])
        images.append({'side':side,'revision':revision['id'],'sha256':revision['sha256'],
                       'filename':reference['filename'],'provenance':provenance(revision)})
    data={'schema':'foundry-image-handoff/1','id':record['id'],'receipt':receipt,
          'category':record['config']['category'],'images':images}
    root=library.state_root/'handoffs';root.mkdir(exist_ok=True)
    (root/(receipt+'.json')).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    return {'receipt':receipt}


def resolve_handoff(state_root,source,references):
    if not source:return None
    if not isinstance(source,dict):raise ValueError('Use the image creator handoff record.')
    receipt=identifier(source.get('receipt'))
    try:data=json.loads((state_root/'handoffs'/(receipt+'.json')).read_text(encoding='utf-8'))
    except FileNotFoundError:raise ValueError('This image handoff was not found. Send the accepted image pair to 3D again.') from None
    matched={(r['filename'],r['sha256']) for r in references}
    images=[{k:v for k,v in image.items() if k!='filename'} for image in data['images'] if (image['filename'],image['sha256']) in matched]
    if not images:return None
    return {**{k:v for k,v in data.items() if k!='images'},'images':images}
