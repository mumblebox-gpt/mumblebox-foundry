"""Selected hair outputs use Foundry's shared catalog, README and ZIP publisher."""
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from ...artifacts import owned_path, digest
from ....finishing.package_catalog import FileRecord, VariantRecord, build_catalog
from ....finishing.package_archive import publish_archive
from .definition import TITLE, REVISION
from .integration import upstream, models_root

DESCRIPTIONS={
    'Static/':'Static hair-card geometry and material for importing into a 3D editor or game project. GLB contains no spring-bone rig.',
    'Rigged/':'VRM 0.x avatar with fitted hair, skinning and spring-bone groups. Reference-avatar metadata and separate licensing are retained.',
    'Motion/':'A rendered head-turn video demonstrating the hair motion. MP4 is a visual preview, not an animation clip.',
    'Textures/':'Material maps and UV layout matching the selected hair export. When enabled, HairDeck ColorDiT predicts per-card root-to-tip base colors; strand normals, roughness and opacity are procedural. These are not baked photographic textures.',
    'Diagnostics/':'Model input, segmentation masks and multi-view renders showing what HairDeck interpreted and generated.',
    'Source/':'Generated card curves, matching chain curves, latent tokens and surface data for further editing and reproducible export.'}


def build(service,record):
    config=record['config'];source=record['export'];ident=uuid.uuid4().hex
    slug=re.sub('[^A-Za-z0-9_-]+','-',config['name']).strip('-')[:64] or 'hair'
    target=owned_path(service.output_root,service.output_root/'foundry-hair'/'packages'/(slug+'-'+ident[:8]))
    target.mkdir(parents=True,exist_ok=False);files=[];variants=[]
    def copy(path,relative,description,kind='data',role='support'):
        dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        files.append(FileRecord(relative,kind,relative.split('/')[0].lower() if relative.split('/')[0]+'/' in DESCRIPTIONS else None,
                                description,dest.suffix.lstrip('.'),role))
    for entry in source['files']:
        service.check(record)
        path=owned_path(service.output_root,service.output_root/entry['subfolder']/entry['filename'])
        suffix=path.suffix.lower();stem=path.stem
        if suffix=='.glb':directory='Static/' if config['glb'] else None
        elif suffix=='.vrm':directory='Rigged/' if config['vrm'] else None
        elif suffix=='.mp4':directory='Motion/' if config['motion'] else None
        elif path.parent.name=='textures':directory='Textures/'
        elif stem.startswith(('preview','preprocess','model_input','hair_mask','face_mask')):directory='Diagnostics/' if config['diagnostics'] else None
        elif stem in ('cards','chains','tokens','surface'):directory='Source/' if config['source_data'] else None
        else:continue
        if not directory:continue
        description={'model':'Static hair-card GLB.' if suffix=='.glb' else 'Skinned VRM avatar with spring bones.',
                     'video':'Head-turn motion preview.'}.get(entry.get('kind'),entry.get('label','Supporting hair data.'))
        labels={'base_color.png':'Hair base color and alpha.','normal.png':'Tangent-space hair normal map.',
                'roughness.png':'Linear roughness map.','alpha.png':'Hair opacity map.','uv_layout.png':'UV layout reference.',
                'metallic_roughness.png':'glTF packed metallic-roughness map.',
                'unity_metallic_smoothness.png':'Unity packed metallic-smoothness map.',
                'material.json':'Material settings and surface geometry counts.','cards.json':'Generated card control curves.',
                'chains.json':'Generated spring-chain curves.','tokens.npy':'Matching sampled hair latent tokens.',
                'surface.npz':'Material surface arrays without Python pickle objects.'}
        if path.name in labels:description=labels[path.name]
        elif directory=='Diagnostics/':description='Preprocessing image or multi-view hair review render.'
        copy(path,directory+path.name,description,'geometry' if suffix in ('.glb','.vrm') else 'texture' if directory=='Textures/' else 'data',
             'preview' if directory=='Diagnostics/' and stem.startswith('preview') else 'support')
    # Keep a thumbnail in every package, even when diagnostic output is disabled.
    preview=next((e for e in source['files'] if e['filename'].startswith('preview') and e['filename'].endswith('.png')),None)
    if preview and not config['diagnostics']:
        copy(service.output_root/preview['subfolder']/preview['filename'],'Metadata/preview.png','Hair preview thumbnail.','image','preview')
    native=upstream();pack=Path(native.__file__).parent
    licenses={'HairDeck-Apache-2.0.txt':pack/'LICENSE','Third-party-notices.md':pack/'THIRD_PARTY_NOTICES.md',
              'SAM3-LICENSE.txt':pack/'_vendor/hairdeck_sam3/LICENSE','DINOv3-LICENSE.md':pack/'_vendor/hairdeck_dinov3/LICENSE.md',
              'BiRefNet-LICENSE.txt':pack/'_vendor/hairdeck_birefnet/LICENSE','pyrender-LICENSE.txt':pack/'_vendor/hairdeck_pyrender/LICENSE'}
    for name,path in licenses.items():copy(path,'Licenses/'+name,'Unmodified upstream license or resource notice.','license')
    provenance={'workflow_title':TITLE,'node_pack_revision':REVISION,'reference_sha256':record['source_sha256'],
        'generation':{k:config[k] for k in ('seed','steps','cfg','bones','colors','checkpoints')},'selected_variation':record['selected'],
        'appearance':{k:config[k] for k in ('head_profile','scale','offset','color','material','uv_mode','texture_size','motion_chains')},
        'exported_appearance':source.get('appearance',{}),
        'selection':{k:config[k] for k in ('glb','vrm','motion','diagnostics','source_data','zip')},
        'generation_seed':source['measurements']['seed'],'rig_validation':source['measurements'].get('rig',{}),
        'models':record.get('models',{})}
    metadata=target/'Metadata';metadata.mkdir(exist_ok=True)
    (metadata/'generation.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    files.append(FileRecord('Metadata/generation.json','metadata',None,'Generation, fitting, material and output-selection provenance.','json','provenance'))
    files.append(FileRecord('Metadata/manifest.json','metadata',None,'Complete file catalog, measurements and SHA-256 integrity records.','json','catalog'))
    for directory,description in DESCRIPTIONS.items():
        if directory=='Static/' and config['show_head']:description+=' The selected reference head is included.'
        owned=[f.path for f in files if f.path.startswith(directory)]
        measurements={'geometry':{**source['measurements']['geometry'],'generated_chains':source['measurements']['generated_chains']},
                      'coordinates':{'units':'metres','up_axis':'Y'}} if directory in ('Static/','Rigged/') else {}
        if directory=='Rigged/':measurements['geometry'].update(source['measurements'].get('rig',{}))
        if owned:variants.append(VariantRecord(directory[:-1].lower(),directory,description,file_paths=owned,
            measurements=measurements,
            limitations=['Hair-card topology is preserved; global watertight repair and quad retopology are not applied.'] if directory in ('Static/','Rigged/') else []))
    registry=json.loads((Path(__file__).resolve().parents[3]/'finishing/package_resources.json').read_text(encoding='utf-8'))
    resources=[registry[key] for key in ('hairdeck','hairdeck_wrapper','sam3','dinov3','birefnet')]
    if config['colors']:resources.append(registry['hairdeck_color'])
    if config['vrm'] or config['motion']:
        resources.extend([dict(name='Reference avatar',stage='Rigged export',version=None,source='https://huggingface.co/hyz317/HairDeck',license='Apache-2.0 for bundled upstream example; custom heads retain their own terms',license_summary='Original author and VRM metadata remain in the avatar.'),registry['hairdeck_vrm']])
    from ... import VERSION
    catalog=build_catalog(files,variants,resources,dict(name='Mumblebox 3D Asset Foundry',description='Local image and 3D asset workflows.',
        github_url='https://github.com/mumblebox-gpt/mumblebox-foundry'),dict(asset_name=config['name'],export_id=ident,
        created_utc=datetime.now(timezone.utc).isoformat(),workflow_version=VERSION,production=provenance))
    archive=publish_archive(catalog,target,target.with_suffix('.zip'),lambda:service.check(record))
    history=service.library.import_package(archive)
    return dict(path=archive.relative_to(service.output_root).as_posix(),history_id=history['id'],bytes=archive.stat().st_size,
                sha256=digest(archive),files=len(catalog.files),zip_selected=config['zip'])
