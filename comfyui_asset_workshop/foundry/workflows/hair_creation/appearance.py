"""Place HairDeck's 16 root-to-tip colors in its native material atlas."""
import json
import numpy as np
from PIL import Image


def color_rows(colors,height,kind):
    """Upstream card UV: v=0 at root, v=1 at tip; PNG rows run from tip to root."""
    colors=np.asarray(colors,dtype=np.float64)
    if colors.ndim!=2 or colors.shape[1]!=3 or not np.isfinite(colors).all():
        raise ValueError('HairDeck card colors must be finite RGB samples.')
    position=np.full(height,0. if kind=='root' else 1.) if kind!='surface' else np.linspace(1.,0.,height)
    centers=(np.arange(len(colors))+.5)/len(colors)
    return np.stack([np.interp(position,centers,colors[:,axis]) for axis in range(3)],-1)


def create_appearance(hair,rgb,color,uv_mode,resolution,preset,directory,work):
    from hairdeck_core import materials
    colors=getattr(hair,'card_colors',None)
    predicted=colors is not None and color=='auto'
    # Distinct predicted card colors cannot share an atlas chart. UI explains
    # this constraint; manual single-color styling can still use shared UVs.
    asset=materials.create(hair.cards,[1.,1.,1.] if predicted else rgb,
                           'unique' if predicted else uv_mode,resolution,preset,directory,work)
    if not predicted or preset=='checker':return asset
    pixels=np.array(Image.open(directory/'base_color.png').convert('RGBA'))
    for tile in asset.mesh.layout:
        card,kind=tile['key'];x,y,width,height=tile['rect'];g=tile['gutter']
        rows=color_rows(colors[card],height,kind)
        tile_pixels=pixels[y:y+height,x:x+width].copy()
        tile_pixels[...,:3]=np.uint8(np.clip(tile_pixels[...,:3]/255.*rows[:,None,:],0,1)*255+.5)
        pixels[y-g:y+height+g,x-g:x+width+g]=np.pad(tile_pixels,((g,g),(g,g),(0,0)),mode='edge')
    Image.fromarray(pixels).save(directory/'base_color.png')
    asset.material['color_source']='HairDeck ColorDiT: 16 predicted root-to-tip colors per card'
    (directory/'material.json').write_text(json.dumps(asset.material,ensure_ascii=False,indent=2),encoding='utf-8')
    return asset
