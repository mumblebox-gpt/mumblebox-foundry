"""HairDeck generation adapter: upstream cards/chains plus its current per-card color model."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import torch
from PIL import Image
import folder_paths
from .integration import upstream


def prepare(model,image,mask):
    """The native best-quality preprocessing recipe, retaining the official color model's person matte."""
    native=upstream();rt=native.runtime
    source=rt.image_bytes(image,mask)
    key=hashlib.sha256(source.tobytes()+str((source.mode,source.size,model.signature)).encode()).hexdigest()
    directory=Path(folder_paths.get_temp_directory())/'hairdeck'/'foundry-preprocess-v2'
    directory.mkdir(parents=True,exist_ok=True);cache=directory/(key+'.npz')
    if cache.exists():
        with np.load(cache,allow_pickle=False) as values:
            data={k:values[k].copy() for k in values.files}
        return data,True
    weights=model.load(model.preprocess,4)
    rgb,alpha,_=rt.load_image(source);preset=rt.PRESETS['best']
    prep=rt.Prep(preset['cfg'],matte='birefnet_matting',matte_size=preset.get('alpha_size',768),
        wr=preset.get('wr',1024),crop_expand=preset.get('crop_expand',1.3),model=weights.sam,
        processor=rt.Sam3Processor(weights.sam,device=str(model.device),confidence_threshold=.5),matte_model=weights.matte)
    p=rt.Preprocessor(prep=prep)(rgb,alpha)
    if p['box'] is None:raise ValueError('HairDeck could not locate hair or a face. Use a clear, uncropped portrait.')
    from hairdeck_core.data.crop import apply_crop
    opacity=p['person'].copy()
    if opacity.max()<=127:opacity[:]=255
    full=np.asarray(rt.composite(Image.fromarray(np.concatenate([rgb,opacity[...,None]],-1),'RGBA')))
    crop=rt.crop_white(full,p['box'],model.hair.model.args.res)
    matte=np.asarray(apply_crop(Image.fromarray(p['person']),tuple(p['box']),model.hair.model.args.res,resample=Image.Resampling.NEAREST))>127
    if not matte.any():matte[:]=True
    messages={'no_hair':'No hair was detected; HairDeck used the face to frame the reference.',
              'no_hair_no_face':'No hair or face was detected; HairDeck used the whole image.',
              'no_person_mask':'No foreground person mask was detected.',
              'matte_disagree':'The foreground masks disagree. Review the processing sheet carefully.',
              'box_fallback':'HairDeck used a fallback crop. Check that the complete hairstyle is visible.'}
    notes={'status':p.get('status'),'notes':p.get('notes',[]),'details':p.get('info',{}),
           'warnings':[messages[n] for n in dict.fromkeys([p.get('status'),*p.get('notes',[])]) if n in messages]}
    data=dict(crop=crop,matte=matte,color=np.asarray(rt.hair_color(rgb,p['hair'])),hair_mask=p['hair'],face_mask=p['face'],
              preview=np.asarray(rt.prep_panel(p,crop)),notes=np.asarray(json.dumps(notes,default=str)))
    temporary=cache.with_suffix('.tmp.npz');np.savez_compressed(temporary,**data);temporary.replace(cache)
    return data,False


def predict_colors(model,hair,crop,matte):
    from comfy.model_patcher import ModelPatcher
    from hairdeck_core.cards.tokens import clean_tokens,sign_token_normals
    from .upstream_color import load_color_dit,lab_to_srgb
    from .prepare import color_resource
    resource=color_resource();filename=model.root/resource['name']
    # Comfy owns residency and offloading, including this additional checkpoint.
    if not hasattr(model,'foundry_color'):
        net,args=load_color_dit(str(filename),model.tokenizer().dim,'cpu')
        expected=model.hair.model.args
        if (args.vae,args.dino,args.res)!=(expected.vae,expected.dino,expected.res):
            raise ValueError('The HairDeck color model does not match the selected card model.')
        model.foundry_color=ModelPatcher(net,model.device,torch.device('cpu'))
    weights=model.load(model.hair,2)
    pixels=torch.from_numpy(crop.copy()).permute(2,0,1)[None].to(model.device).float()
    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
        encoded=weights.encoder(pixels)
    color=model.load(model.foundry_color,2)
    token=model.tokenizer();tokens=torch.from_numpy(hair.tokens).to(model.device)
    clean=sign_token_normals(token,clean_tokens(token,tokens.float()))
    slots=torch.nonzero(clean[0,:,token.groups['exist']][:,0]>0)[:,0]
    if len(slots)!=len(hair.cards):raise ValueError('The generated card slots do not match color prediction.')
    with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
        context=color.encode_ctx(encoded,pixels,torch.from_numpy(matte.copy())[None].to(model.device))
        lab=color(clean,context)
    return np.round(lab_to_srgb(lab[0].float()[slots].cpu().numpy()),4)


class FoundryHairGenerate:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'model':('HAIRDECK_MODEL',),'image':('STRING',{'default':''}),
        'seed':('INT',{'default':0,'min':0,'max':2**53-16}), 'steps':('INT',{'default':50,'min':1,'max':200}),
        'cfg':('FLOAT',{'default':2.,'min':1.,'max':4.,'step':.25}), 'generate_bones':('BOOLEAN',{'default':True}),
        'colors':('BOOLEAN',{'default':True})},'optional':{'external_image':('IMAGE',),'transparent_mask':('MASK',)}}
    RETURN_TYPES=('HAIRDECK_RESULT',);FUNCTION='generate';CATEGORY='Mumblebox Foundry/Hair'
    def generate(self,model,image,seed,steps,cfg,generate_bones,colors,external_image=None,transparent_mask=None):
        started=time.monotonic();native=upstream();rt=native.runtime
        pixels,mask=native.load_input(image,external_image,transparent_mask)
        data,cache_hit=prepare(model,pixels,mask)
        signature=hashlib.sha256(data['crop'].tobytes()+model.signature.encode()).hexdigest()
        prepared=rt.PreparedImage(model.root,model.signature,signature,data['crop'],data['color'].tolist())
        hair=rt.generate(model,prepared,seed,steps,cfg)
        if colors:hair.card_colors=predict_colors(model,hair,data['crop'],data['matte'])
        hair.preprocess_notes=json.loads(str(data['notes']))
        rig=rt.generate_rig(model,hair,seed,50,2.) if generate_bones else None
        tensors=[rt.image_tensor(Image.fromarray(data['crop'])),
                 torch.from_numpy(data['hair_mask'].copy().astype(np.float32)).unsqueeze(0),
                 torch.from_numpy(data['face_mask'].copy().astype(np.float32)).unsqueeze(0),
                 rt.image_tensor(Image.fromarray(data['preview']))]
        result=native.generation.GenerationResult(hair,rig,*tensors,seed,steps,cfg,cache_hit,round(time.monotonic()-started,3))
        from comfy_api.latest import ui,io
        images=ui.ImageSaveHelper.save_images(result.preview,filename_prefix='hairdeck-preprocess',folder_type=io.FolderType.temp,cls=None)
        return {'ui':{'images':images},'result':(result,)}
