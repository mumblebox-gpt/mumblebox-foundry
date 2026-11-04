"""Aligned structural pixels. No neural preprocessing or inference."""
import numpy as np
from PIL import Image, ImageFilter
from .sheet import split_array, ORDER


def control_arrays(maps,alphas,layout,threshold,dilation):
    if set(maps)!=set(ORDER) or set(alphas)!=set(ORDER):
        raise ValueError('Each structural panel needs its matching diagnostic alpha.')
    shape=(layout['height'],layout['width'])
    result=np.zeros((*shape,3),np.float32);mask=np.zeros(shape,np.float32)
    # Independently validate the camera rectangles before using them.
    split_array(result,layout)
    for panel in layout['panels']:
        ident=panel['id'];x,y,w,h=panel['rect']
        value=np.asarray(maps[ident],np.float32);alpha=np.asarray(alphas[ident],np.float32)
        for pixels in (value,alpha):
            if pixels.ndim!=3 or pixels.shape[:2]!=(h,w) or pixels.shape[2] not in (3,4) or not np.isfinite(pixels).all() or pixels.min()<0 or pixels.max()>1:
                raise ValueError('Structural/alpha dimensions, channels or range do not match camera '+ident)
        # Diagnostic value is RGB, NOT the always-opaque PNG alpha channel.
        coverage=(alpha[:,:,0]>=threshold).astype(np.uint8)*255
        if dilation:coverage=np.asarray(Image.fromarray(coverage).filter(ImageFilter.MaxFilter(2*dilation+1)))
        mask[y:y+h,x:x+w]=coverage/255
        rgb=value[:,:,:3].copy()
        rgb[alpha[:,:,0]==0]=0
        result[y:y+h,x:x+w]=rgb
    return result,mask


def restore_gutters(pixels,layout):
    # Validate before any save; never crop/recenter a generated object.
    split_array(pixels,layout)
    result=np.asarray(pixels).copy();occupied=np.zeros(result.shape[:2],bool)
    for panel in layout['panels']:
        x,y,w,h=panel['rect'];occupied[y:y+h,x:x+w]=True
    result[~occupied]=0
    return result
