"""Exact panel geometry. No image generation, content-based crop or model imports."""
import copy
import numpy as np
from .camera_math import validate_camera

ORDER=('front','right','back','left')


def make_layout(cameras,gutter):
    if len(cameras)!=4 or {c['id'] for c in cameras}!=set(ORDER):
        raise ValueError('Sheet needs exactly four named cardinal cameras.')
    if not isinstance(gutter,int) or gutter<0:raise ValueError('Invalid sheet gutter.')
    by_id={c['id']:c for c in cameras}; size=cameras[0]['width']; panels=[]
    for i,ident in enumerate(ORDER):
        camera=copy.deepcopy(by_id[ident]);validate_camera(camera)
        if (camera['width'],camera['height'])!=(size,size):raise ValueError('Camera panel sizes disagree.')
        x=(i%2)*(size+gutter);y=(i//2)*(size+gutter)
        K=copy.deepcopy(camera['K']);K[0][2]+=x;K[1][2]+=y
        panels.append(dict(id=ident,rect=[x,y,size,size],camera=camera,sheet_K=K))
    return dict(schema='fvb.sheet/1',width=2*size+gutter,height=2*size+gutter,gutter=gutter,
                panel_size=size,background_rgb=[96,96,96],separator_rgb=[0,0,0],panels=panels)


def pack_arrays(images,cameras,gutter):
    layout=make_layout(cameras,gutter)
    if set(images)!=set(ORDER):raise ValueError('Each panel needs its matching camera image.')
    result=np.zeros((layout['height'],layout['width'],3),dtype=np.float32)
    for panel in layout['panels']:
        pixels=np.asarray(images[panel['id']],dtype=np.float32);x,y,w,h=panel['rect']
        if pixels.ndim!=3 or pixels.shape[:2]!=(h,w) or pixels.shape[2] not in (3,4) or not np.isfinite(pixels).all():
            raise ValueError('Guide dimensions/channels do not match its camera.')
        rgb=pixels[...,:3]
        if pixels.shape[2]==4:rgb=rgb*pixels[...,3:4]+(96/255)*(1-pixels[...,3:4])
        result[y:y+h,x:x+w]=rgb
    return result,layout


def split_array(pixels,layout):
    pixels=np.asarray(pixels)
    if layout.get('schema')!='fvb.sheet/1' or pixels.ndim!=3 or pixels.shape[:2]!=(layout['height'],layout['width']) or pixels.shape[2] not in (3,4):
        raise ValueError('Enhanced sheet dimensions must match the saved layout exactly; no automatic resize.')
    if not np.isfinite(pixels).all():raise ValueError('Enhanced sheet contains invalid pixels.')
    # Reconstruct expected rectangles independently of the generated image content.
    expected=make_layout([p['camera'] for p in layout['panels']],layout['gutter'])
    if [p['rect'] for p in layout['panels']]!=[p['rect'] for p in expected['panels']]:
        raise ValueError('Saved sheet rectangles are inconsistent.')
    return {p['id']:pixels[p['rect'][1]:p['rect'][1]+p['rect'][3],p['rect'][0]:p['rect'][0]+p['rect'][2]].copy() for p in layout['panels']}
