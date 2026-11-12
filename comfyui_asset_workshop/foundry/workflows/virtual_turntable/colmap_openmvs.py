"""OpenMVS v2.4 author COLMAP recipe, adapted to Comfy cancellation and masked input.

Author: scripts/python/MvgMvsPipeline.py COLMAP preset, steps 12-14,16-21.
No synthetic GPS step. RGB and foreground masks use the SAME COLMAP undistorter.
Native algorithms own all reconstruction, refinement, UVs and texturing.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import time
import math
from pathlib import Path
import numpy as np
from PIL import Image
from comfy_api.latest import Types
from comfy.utils import ProgressBar
from .runtime import runtime_settings
from .references import CATEGORY
from .processes import release_models, run_process
from .openmvs_texture import texture_runtime, texture_options
from .colmap_geometry import image_records, prepare, read_camera
from .colmap_export import export_asset

ROOT=Path(__file__).resolve().parent

def registered_count(model):
    with (model/'images.bin').open('rb') as stream:
        return struct.unpack('<Q',stream.read(8))[0]

def overrides(raw):
    values=json.loads(raw)
    allowed=json.loads((ROOT/'native-options.json').read_text(encoding='utf-8'))
    if not isinstance(values,dict):raise ValueError('Native overrides must be an object keyed by stage.')
    for stage,flags in values.items():
        if stage not in allowed or not isinstance(flags,dict):raise ValueError(f'Unknown native stage: {stage}')
        for key,value in flags.items():
            if key not in allowed[stage] or re.search(r'path|file|folder|project|export-type|config|^help$',key,re.I):
                raise ValueError(f'Unknown or adapter-owned native option: {stage}.{key}')
            if not isinstance(value,(str,int,float,bool)):raise ValueError('Native option values must be scalar.')
    return values

def arglist(options):
    return [item for k,v in options.items() for item in ('--'+k,str(int(v)) if isinstance(v,bool) else str(v))]

class Reconstruct:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{
            'frame_set':('V360_FRAMESET',),
            'camera_model':(['PINHOLE','OPENCV','SIMPLE_RADIAL'],{'tooltip':'PINHOLE is a useful starting assumption for generated views. OPENCV is the author script default for photos; extra distortion freedom can overfit generated views.'}),
            'shared_camera':('BOOLEAN',{'default':True}),
            'initial_focal_factor':('FLOAT',{'default':1.2,'min':0.3,'max':5.0,'step':0.05,'tooltip':'Initial focal length / longest image side. A starting guess, not known H3 calibration.'}),
            'gpu_features':('BOOLEAN',{'default':True}),
            'gpu_index':('INT',{'default':0,'min':0,'max':7}),
            'max_features':('INT',{'default':8192,'min':1024,'max':32768,'step':1024}),
            'depth_downscale':([0,1,2],{'default':1,'tooltip':'0 full selected resolution; 1 halves it; 2 quarters it. Smaller depth maps use less memory.'}),
            'max_resolution':('INT',{'default':1024,'min':256,'max':2048,'step':32}),
            'neighbor_views':('INT',{'default':8,'min':2,'max':20}),
            'refine_mesh':('BOOLEAN',{'default':True}),
            'refine_on_gpu':('BOOLEAN',{'default':True,'tooltip':'Explicit CUDA refinement; turn off for the author CPU alternative. Never silently switches.'}),
            'texture_size':([2048,4096,8192],{'default':4096}),
            'cpu_threads':('INT',{'default':8,'min':1,'max':64}),
            'timeout_minutes':('INT',{'default':180,'min':5,'max':1440}),
            'advanced_overrides':('STRING',{'default':'{}','multiline':True,'tooltip':'Native scalar options keyed by feature, match, mapper, dense, mesh, refine or texture. Exact installed options in PARAMETER-GUIDE.md. Paths are owned by this adapter.'})
        }, 'optional': {
            'camera_calibration': (['Auto fit lens', 'Keep chosen lens'], {'default': 'Auto fit lens'}),
            'initial_fov': ('FLOAT', {'default': 10., 'min': 2., 'max': 120., 'tooltip': 'Horizontal field-of-view assumption for fixed PINHOLE calibration; not H3 camera metadata.'}),
            'refine_decimation': ('FLOAT', {'default': 0., 'min': 0., 'max': 1., 'step': .01, 'tooltip': 'OpenMVS RefineMesh input reduction. 0 = automatic, 1 = preserve the mesher density before refinement. Advanced refine.decimate takes precedence.'}),
            'output_mode': (['Full finish', 'Geometry review', 'Color review'], {'default': 'Full finish', 'tooltip': 'Geometry review stops before color projection and Hi3D. Color review projects the orbit images onto the selected mesh, then stops before Hi3D.'}),
        }}
    RETURN_TYPES=('FILE_3D','STRING','STRING','FILE_3D')
    RETURN_NAMES=('selected_mesh_preview','original_mesh_obj','project_folder','rough_mesh_preview')
    FUNCTION='reconstruct'
    CATEGORY=CATEGORY

    def reconstruct(self,frame_set,camera_model,shared_camera,initial_focal_factor,gpu_features,gpu_index,
                    max_features,depth_downscale,max_resolution,neighbor_views,refine_mesh,refine_on_gpu,
                    texture_size,cpu_threads,timeout_minutes,advanced_overrides,camera_calibration='Auto fit lens',initial_fov=10.,
                    refine_decimation=0.,output_mode='Full finish',camera_only=False):
        runtime=runtime_settings()
        colmap=Path(runtime['colmap']);mvs=Path(runtime['openmvs'])
        review = output_mode != 'Full finish'
        with_color = not camera_only and output_mode != 'Geometry review'
        if with_color:
            texture_executable, texture_info = texture_runtime(runtime)
        native_apps = [] if camera_only else ['InterfaceCOLMAP', 'DensifyPointCloud', 'ReconstructMesh']
        if refine_mesh and not camera_only:
            native_apps.append('RefineMesh')
        for exe in [colmap, *[mvs / (name + '.exe') for name in native_apps]]:
            if not exe.is_file():raise RuntimeError(f'Reconstruction dependency is missing: {exe}')
        extra=overrides(advanced_overrides)
        settings={k:v for k,v in locals().copy().items() if k in {**self.INPUT_TYPES()['required'], **self.INPUT_TYPES()['optional']} and k!='frame_set'}
        fixed=camera_calibration=='Keep chosen lens'
        fixed_models = {'PINHOLE', 'SIMPLE_PINHOLE'} if camera_only else {'PINHOLE'}
        if fixed and (camera_model not in fixed_models or not shared_camera):
            raise ValueError('Keep chosen lens requires a shared pinhole camera')
        source=Path(frame_set['root']).resolve()
        reconstruction_settings = {key: value for key, value in settings.items() if key != 'output_mode'}
        identity=json.dumps({'frames':frame_set['fingerprint'],'settings':reconstruction_settings,'runtime':runtime,'adapter':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},sort_keys=True)
        prefix = 'colmap-cameras-' if camera_only else 'colmap-openmvs-'
        job=source/(prefix+hashlib.sha256(identity.encode()).hexdigest()[:12])
        job.mkdir(exist_ok=True)
        rgb=source/'frames';sparse=job/'sparse';dense=job/'undistorted';dense_masks=job/'undistorted-masks';native=job/'openmvs';asset=job/'asset'
        for p in [sparse,dense,dense_masks,native,asset]:p.mkdir(exist_ok=True)
        mask_input=job/'mask-images';sift_masks=job/'feature-masks'
        mask_input.mkdir(exist_ok=True);sift_masks.mkdir(exist_ok=True)
        for path in sorted(rgb.glob('*.png')):
            mask=source/'masks'/path.name
            shutil.copyfile(mask,sift_masks/(path.name+'.png'))
            with Image.open(mask) as image:image.convert('RGB').save(mask_input/path.name)
        env=os.environ.copy();env['OMP_NUM_THREADS']=str(cpu_threads)
        env['PATH']=str(colmap.parent)+os.pathsep+env.get('PATH','')
        env['QT_PLUGIN_PATH']=str(colmap.parent.parent/'plugins')
        release_models()
        import torch
        if not camera_only and not torch.cuda.is_available():raise RuntimeError('This dense OpenMVS route requires the configured CUDA GPU.')
        started=time.monotonic();deadline=started+timeout_minutes*60
        progress=ProgressBar(6 if camera_only else 9 + int(refine_mesh) + int(with_color));done=0
        commands=[]
        def stage(key,exe,options,expected):
            nonlocal done
            merged=texture_options(options, extra.get(key,{}), texture_info) if key=='texture' else {**options,**extra.get(key,{})}
            command=[str(exe),*arglist(merged)]
            if exe==colmap:command.insert(1,{'feature':'feature_extractor','match':'exhaustive_matcher','mapper':'mapper','undistort':'image_undistorter','mask-undistort':'image_undistorter','camera-text':'model_converter'}[key])
            commands.append({'stage':key,'command':command})
            (job/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
            signature=hashlib.sha256(json.dumps(command).encode()).hexdigest()
            marker=job/(key+'.complete.json')
            cached=False
            if marker.is_file():
                old=json.loads(marker.read_text())
                if key=='mapper' and not expected:
                    expected=[Path(p) for p in old.get('expected',[])]
                cached=bool(expected) and old.get('signature')==signature and all(p.is_file() and p.stat().st_size for p in expected)
            if not cached:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError(f'Time limit reached; native cache remains in {job}')
                run_process(command,native,env,job/(key+'.log'),remaining)
                if key=='mapper':
                    expected=list(sparse.glob('*/images.bin'))
                    if not expected:raise RuntimeError(f'COLMAP registered no cameras. Inspect {job}/mapper.log')
                missing=[str(p) for p in expected if not p.is_file() or not p.stat().st_size]
                if missing:raise RuntimeError(f'{key} did not produce expected files: {missing}. Logs: {job}')
                marker.write_text(json.dumps({'signature':signature,'expected':[str(p) for p in expected]}),encoding='utf-8')
            done+=1;progress.update_absolute(done)
        db=job/'database.db'
        camera_options={}
        mapper_options={'Mapper.ba_refine_principal_point':False,'Mapper.min_focal_length_ratio':.28,'Mapper.max_focal_length_ratio':30}
        if fixed:
            with Image.open(next(rgb.glob('*.png'))) as first:width,height=first.size
            focal=width/(2*math.tan(math.radians(initial_fov)/2))
            intrinsics = (focal, width/2, height/2) if camera_model == 'SIMPLE_PINHOLE' else (focal, focal, width/2, height/2)
            camera_options['ImageReader.camera_params'] = ','.join(map(str, intrinsics))
            mapper_options.update({'Mapper.ba_refine_focal_length':False,'Mapper.ba_refine_extra_params':False})
        stage('feature',colmap,{'database_path':db,'image_path':rgb,'ImageReader.mask_path':sift_masks,
            'ImageReader.camera_model':camera_model,'ImageReader.single_camera':shared_camera,
            'ImageReader.default_focal_length_factor':initial_focal_factor,'FeatureExtraction.type':'SIFT',
            'FeatureExtraction.num_threads':cpu_threads,'FeatureExtraction.use_gpu':gpu_features,
            'FeatureExtraction.gpu_index':gpu_index,'FeatureExtraction.max_image_size':max_resolution,
            'SiftExtraction.max_num_features':max_features,**camera_options},[db])
        stage('match',colmap,{'database_path':db,'FeatureMatching.num_threads':cpu_threads,
            'FeatureMatching.use_gpu':gpu_features,'FeatureMatching.gpu_index':gpu_index,
            'FeatureMatching.max_num_matches':max_features},[db])
        stage('mapper',colmap,{'database_path':db,'image_path':rgb,'output_path':sparse,'Mapper.num_threads':cpu_threads,**mapper_options},[])
        models=[p for p in sparse.iterdir() if p.is_dir() and (p/'images.bin').is_file()]
        if not models:raise RuntimeError(f'COLMAP registered no camera model. Inspect {job}/mapper.log and frame consistency.')
        best=max(models,key=registered_count);registered=registered_count(best)
        if registered < (3 if camera_only else 12):raise RuntimeError(f'Only {registered} cameras registered. Inspect video consistency and masks before retrying.')
        # Run the same native camera transform on masks as RGB, rather than
        # assuming distorted input masks align with undistorted photos.
        common={'input_path':best,'output_type':'COLMAP','max_image_size':max_resolution,'num_threads':cpu_threads}
        stage('undistort',colmap,{**common,'image_path':rgb,'output_path':dense},[dense/'sparse'/'images.bin'])
        stage('mask-undistort',colmap,{**common,'image_path':mask_input,'output_path':dense_masks},[dense_masks/'sparse'/'images.bin'])
        def export_camera_text():
            camera_text = job / 'camera-text'
            camera_text.mkdir(exist_ok=True)
            stage('camera-text', colmap, {'input_path': dense / 'sparse', 'output_path': camera_text,
                                         'output_type': 'TXT'}, [camera_text / name for name in
                                                               ('cameras.txt', 'images.txt', 'points3D.txt')])
            return camera_text

        if camera_only:
            return {'camera_text': str(export_camera_text()), 'images': str(dense/'images'),
                    'masks': str(dense_masks/'images'), 'registered': registered,
                    'frame_set': frame_set}
        masks=native/'masks';masks.mkdir(exist_ok=True)
        # A resumed job already has OpenMVS mask sidecars in this directory.
        for image_path in sorted((dense/'images').glob('*.png')):
            if image_path.name.endswith('.mask.png'):
                continue
            mask_path=dense_masks/'images'/image_path.name
            if not mask_path.is_file():raise RuntimeError(f'Missing undistorted mask for {image_path.name}')
            with Image.open(image_path) as photo,Image.open(mask_path) as mask:
                if photo.size!=mask.size:raise RuntimeError('Undistorted RGB and mask dimensions disagree.')
                result=Image.fromarray((np.asarray(mask.convert('L'))>=128).astype(np.uint8)*255)
                result.save(masks/(image_path.stem+'.mask.png'))
                result.save(image_path.with_name(image_path.stem+'.mask.png'))
        if not list(masks.glob('*.mask.png')):raise RuntimeError('No aligned foreground masks were prepared for OpenMVS.')
        scene=native/'scene.mvs';cloud=native/'scene_dense.mvs';mesh=native/'scene_dense_mesh.ply';refined=native/'scene_dense_mesh_refine.ply'
        stage('interface',mvs/'InterfaceCOLMAP.exe',{'input-file':dense,'output-file':scene,'image-folder':dense/'images','working-folder':native,'max-threads':cpu_threads},[scene])
        stage('dense',mvs/'DensifyPointCloud.exe',{'input-file':scene,'output-file':cloud,'working-folder':native,
            'max-threads':cpu_threads,'cuda-device':gpu_index,'mask-path':str(masks)+os.sep,'ignore-mask-label':0,
            'resolution-level':depth_downscale,'max-resolution':max_resolution,'min-resolution':256,'number-views':neighbor_views,
            'tower-mode':0,'remove-dmaps':0},[cloud,native/'scene_dense.ply'])
        stage('mesh',mvs/'ReconstructMesh.exe',{'input-file':cloud,'pointcloud-file':native/'scene_dense.ply',
            'output-file':native/'scene_dense_mesh.mvs','working-folder':native,'max-threads':cpu_threads,'decimate':1},[mesh])
        if refine_mesh:
            stage('refine',mvs/'RefineMesh.exe',{'input-file':cloud,'mesh-file':mesh,'output-file':native/'scene_dense_mesh_refine.mvs',
                'working-folder':native,'max-threads':cpu_threads,'cuda-device':gpu_index if refine_on_gpu else -2,
                'scales':1,'gradient-step':25.05,'resolution-level':depth_downscale,'max-views':neighbor_views,
                'reduce-memory':1,'decimate':refine_decimation},[refined])
        import trimesh
        selected = refined if refine_mesh else mesh
        if with_color:
            obj=asset/'texturedMesh.obj'
            stage('texture',texture_executable,{'input-file':cloud,'mesh-file':selected,
                'output-file':asset/'texturedMesh.mvs','working-folder':native,'max-threads':cpu_threads,'cuda-device':gpu_index,
                'export-type':'obj','decimate':1,'close-holes':0,'ignore-mask-label':0,'max-texture-size':texture_size,
                'global-seam-leveling':1,'local-seam-leveling':1},[obj])
        else:
            obj=asset/'rawMesh.obj'
            trimesh.load(str(selected),force='mesh',process=False).export(str(obj),file_type='obj')
        result=trimesh.load(str(obj),force='scene',process=False)
        if not result.geometry:raise RuntimeError('The reconstruction OBJ contains no geometry.')
        glb=asset/(obj.stem+'.glb')
        camera_text = job / 'camera-text'
        camera_text.mkdir(exist_ok=True)
        stage('camera-text', colmap, {'input_path': dense / 'sparse', 'output_path': camera_text,
                                     'output_type': 'TXT'}, [camera_text / 'cameras.txt', camera_text / 'images.txt', camera_text / 'points3D.txt'])
        reference = min(record[9] for record in image_records(camera_text))
        rotation, _, intrinsics, width, _ = read_camera(camera_text, reference)
        vertices = np.vstack([item.vertices for item in result.geometry.values()])
        _, transform = prepare(vertices, rotation)
        context = {'transform': transform}
        export_asset(result, context, glb)
        rough_preview = None
        if review:
            rough = trimesh.load(str(mesh), force='mesh', process=False)
            rough_glb = asset / 'roughMesh.glb'
            export_asset(trimesh.Scene(rough), context, rough_glb)
            rough_preview = Types.File3D(str(rough_glb))
        errors = [float(line.split()[7]) for line in (camera_text / 'points3D.txt').read_text().splitlines()
                  if line.strip() and not line.startswith('#')]
        camera_report = {'reference': reference, 'reference_horizontal_fov': math.degrees(2 * math.atan(width / (2 * intrinsics[0]))),
                         'sparse_points': len(errors), 'mean_sparse_track_error_px': float(np.mean(errors)) if errors else None}
        receipt={'runtime':runtime,'settings':settings,'frames':frame_set['count'],'registered_cameras':registered,
            'elapsed_seconds':round(time.monotonic()-started,2),'faces':sum(len(g.faces) for g in result.geometry.values()),
            'frame_root':str(source),'best_model':str(best),'dense_model':str(dense/'sparse'),
            'topology':'triangles','metric_scale':'unknown','watertight':'not guaranteed','original':str(obj),'preview':str(glb),
            'rough_mesh':str(mesh),'selected_native_mesh':str(selected),'camera_report':camera_report,
            'author_recipe':'OpenMVS v2.4 MvgMvsPipeline COLMAP steps 12-14 and 16-20; optional texture projection; no GPS'}
        (job/'result.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        (job/(output_mode.lower().replace(' ', '-')+'.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        if review:
            (job/'README.md').write_text(
                '# Virtual 360 reconstruction review\n\n'
                f'{registered} of {frame_set["count"]} selected frames registered. '
                f'The selected surface contains {receipt["faces"]:,} triangles. Physical scale is unknown.\n\n'
                f'- `asset/{obj.name}` is the native-coordinate surface for the Hi3D camera adapter.\n'
                f'- `asset/{glb.name}` and `asset/roughMesh.glb` are upright previews. The export receipts record their transforms.\n'
                f'- `{selected.relative_to(job).as_posix()}` is the selected native OpenMVS PLY.\n'
                '- `openmvs/scene_dense_mesh.ply` is the mesh before native photometric refinement.\n'
                '- `camera-text/`, `commands.json` and `result.json` contain cameras, commands and processing settings.\n\n'
                'Reconstructed with COLMAP and OpenMVS. Hi3D and final asset finishing are separate stages.\n', encoding='utf-8')
        return (Types.File3D(str(glb)),str(obj),str(job),rough_preview)
