"""Bounded frame selection and persistent RGB/mask sets for photogrammetry."""
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
import folder_paths
import comfy.model_management as mm
from .references import CATEGORY

def frame_fingerprint(root, indices):
    digest=hashlib.sha256(json.dumps(indices).encode())
    for i in range(len(indices)):
        for sub in ("frames","masks"):
            with (root/sub/f"frame_{i:05d}.png").open("rb") as stream:
                while block:=stream.read(1024*1024):
                    digest.update(block)
    return digest.hexdigest()

class SelectFrames:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "images":("IMAGE",),
            "max_frames":("INT",{"default":48,"min":12,"max":200}),
            "max_edge":("INT",{"default":1024,"min":256,"max":2048,"step":32}),
            "drop_loop_endpoint":("BOOLEAN",{"default":True}),
            "exclude_indices":("STRING",{"default":"","tooltip":"Original frame numbers to leave out, separated by commas. Exclusion applies before evenly spaced selection."}),
        }}
    RETURN_TYPES=("IMAGE","STRING")
    RETURN_NAMES=("selected_frames","source_indices")
    FUNCTION="select"
    CATEGORY=CATEGORY
    def select(self,images,max_frames,max_edge,drop_loop_endpoint,exclude_indices):
        excluded={int(x.strip()) for x in exclude_indices.split(",") if x.strip()}
        candidates=[i for i in range(len(images)-int(drop_loop_endpoint)) if i not in excluded]
        if len(candidates)<12:
            raise ValueError("At least 12 distinct frames are needed for this reconstruction recipe.")
        indices=[candidates[i] for i in np.linspace(0,len(candidates)-1,min(max_frames,len(candidates))).round().astype(int)]
        chosen=images[indices].cpu()
        h,w=chosen.shape[1:3]
        scale=min(1.0,max_edge/max(h,w))
        if scale<1:
            chosen=F.interpolate(chosen.movedim(-1,1),(round(h*scale),round(w*scale)),mode="bilinear",align_corners=False).movedim(1,-1)
        return (chosen,json.dumps(indices))

class SaveFrames:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "images":("IMAGE",),"masks":("MASK",),"source_indices":("STRING",{"forceInput":True}),
            "asset_name":("STRING",{"default":"virtual-turntable"}),
            "mask_threshold":("FLOAT",{"default":0.5,"min":0.05,"max":0.95,"step":0.01}),
            "erode_pixels":("INT",{"default":0,"min":0,"max":8}),
            "release_gpu":("BOOLEAN",{"default":True}),
        }}
    RETURN_TYPES=("V360_FRAMESET","IMAGE","MASK","STRING")
    RETURN_NAMES=("frame_set","masked_review","foreground_masks","saved_folder")
    FUNCTION="save"
    CATEGORY=CATEGORY
    def save(self,images,masks,source_indices,asset_name,mask_threshold,erode_pixels,release_gpu):
        if len(images)!=len(masks) or images.shape[1:3]!=masks.shape[1:3]:
            raise ValueError("RGB frames and masks must have matching counts and dimensions.")
        if len(images)>200:
            raise ValueError("Select at most 200 frames before saving.")
        indices=json.loads(source_indices)
        if len(indices)!=len(images):
            raise ValueError("Frame index manifest does not match the selected batch.")
        masks=(masks.cpu()>=mask_threshold).float()
        if erode_pixels:
            k=2*erode_pixels+1
            masks=-F.max_pool2d(-masks[:,None],k,stride=1,padding=erode_pixels).squeeze(1)
        coverage=masks.mean(dim=(1,2))
        if torch.any(coverage<0.002) or torch.any(coverage>0.995):
            bad=[indices[i] for i,c in enumerate(coverage) if c<0.002 or c>0.995]
            raise ValueError(f"Inspect foreground masks for source frames {bad}: nearly empty or full masks are unsuitable for reconstruction.")
        rgb=(images.cpu().clamp(0,1).numpy()*255).round().astype(np.uint8)
        mask_bytes=(masks.numpy()*255).astype(np.uint8)
        digest=hashlib.sha256()
        digest.update(rgb.tobytes());digest.update(mask_bytes.tobytes());digest.update(source_indices.encode())
        slug=re.sub(r"[^a-zA-Z0-9_-]+","-",asset_name).strip("-")[:60] or "virtual-turntable"
        root=(Path(folder_paths.get_output_directory())/"foundry/vt"/(slug+"-"+digest.hexdigest()[:16])).resolve()
        frames=root/"frames"; mask_dir=root/"masks"
        frames.mkdir(parents=True,exist_ok=True);mask_dir.mkdir(exist_ok=True)
        for j,(image,mask) in enumerate(zip(rgb,mask_bytes)):
            mm.throw_exception_if_processing_interrupted()
            name=f"frame_{j:05d}.png"
            Image.fromarray(image).save(frames/name)
            Image.fromarray(mask).save(mask_dir/name)
        manifest={"schema":1,"fingerprint":frame_fingerprint(root,indices),"source_indices":indices,"count":len(indices),
            "width":rgb.shape[2],"height":rgb.shape[1],"mask_convention":"255 foreground; 0 background",
            "rgb":"frames","masks":"masks","camera_poses":"unknown; estimated by the selected reconstruction engine","metric_scale":"unknown"}
        (root/"frames.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        if release_gpu:
            mm.unload_all_models();mm.soft_empty_cache()
        review=images.cpu()*masks[...,None]+0.5*(1-masks[...,None])
        return ({"root":str(root),**manifest},review,masks,str(root))

class ResumeFrames:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"saved_folder":("STRING",{"default":"","tooltip":"Folder containing frames.json from Save Masked Frames. Connect this instead of regenerating the orbit."})}}
    RETURN_TYPES=("V360_FRAMESET",)
    FUNCTION="load"
    CATEGORY=CATEGORY
    def load(self,saved_folder):
        root=Path(saved_folder).expanduser().resolve()
        data=json.loads((root/"frames.json").read_text(encoding="utf-8"))
        if data.get("schema")!=1 or not 12<=data.get("count",0)<=200:
            raise ValueError("Not a supported Virtual 360 frame set.")
        for i in range(data["count"]):
            for sub in ("frames","masks"):
                if not (root/sub/f"frame_{i:05d}.png").is_file():
                    raise ValueError(f"Saved frame set is incomplete: {sub}, frame {i}.")
        data["fingerprint"]=frame_fingerprint(root,data["source_indices"])
        return ({"root":str(root),**data},)




class VideoSource:
    """Lazy source: saved-video mode never requests the generated IMAGE batch.

    Decode saved video on CPU with PyAV. Retain only the bounded selected frames,
    at bounded resolution; never load an entire long/4K clip into RAM.
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "enabled":("BOOLEAN",{"default":False,"tooltip":"Enable only this independent branch. Does not run it."}),
            "source":(["Generated orbit","Saved video"],),
            "saved_video":("STRING",{"default":"","tooltip":"Absolute local MP4/MOV path, used only in Saved video mode."}),
            "max_frames":("INT",{"default":48,"min":12,"max":200}),
            "max_edge":("INT",{"default":1024,"min":256,"max":2048,"step":32}),
            "drop_loop_endpoint":("BOOLEAN",{"default":True}),
            "exclude_indices":("STRING",{"default":""}),
        },"optional":{"generated_images":("IMAGE",{"lazy":True})}}
    RETURN_TYPES=("IMAGE","STRING")
    RETURN_NAMES=("selected_frames","source_indices")
    FUNCTION="select"
    CATEGORY=CATEGORY
    def check_lazy_status(self,source,generated_images=None,**kwargs):
        return ["generated_images"] if source=="Generated orbit" and generated_images is None else []
    def select(self,enabled,source,saved_video,max_frames,max_edge,drop_loop_endpoint,exclude_indices,generated_images=None):
        if not enabled:
            raise ValueError("Enable the chosen Virtual 360 branch first.")
        if source=="Generated orbit":
            return SelectFrames().select(generated_images,max_frames,max_edge,drop_loop_endpoint,exclude_indices)
        import av
        path=Path(saved_video).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise ValueError("Choose an existing absolute local video path.")
        excluded={int(x.strip()) for x in exclude_indices.split(',') if x.strip()}
        # Count frames without retaining decoded images, then decode the selected
        # indices. Two bounded passes avoid unreliable container frame counts.
        with av.open(str(path)) as container:
            count=0
            for _ in container.decode(video=0):
                mm.throw_exception_if_processing_interrupted();count+=1
                if count>18000:
                    raise ValueError("Use an object-orbit clip of at most 18,000 frames.")
        candidates=[i for i in range(count-int(drop_loop_endpoint)) if i not in excluded]
        if len(candidates)<12:
            raise ValueError("At least 12 usable video frames are required.")
        indices=[candidates[i] for i in np.linspace(0,len(candidates)-1,min(max_frames,len(candidates))).round().astype(int)]
        wanted=set(indices);frames=[]
        with av.open(str(path)) as container:
            for i,frame in enumerate(container.decode(video=0)):
                mm.throw_exception_if_processing_interrupted()
                if i in wanted:
                    scale=min(1.0,max_edge/max(frame.width,frame.height))
                    img=frame.reformat(width=max(1,round(frame.width*scale)),height=max(1,round(frame.height*scale)),format='rgb24')
                    frames.append(torch.from_numpy(img.to_ndarray().copy()).float().div_(255))
                if i>=indices[-1]:break
        if len(frames)!=len(indices):raise ValueError("Video decode did not return the selected frames.")
        return (torch.stack(frames),json.dumps(indices))
    @classmethod
    def IS_CHANGED(cls,source,saved_video,**kwargs):
        if source!='Saved video':return source
        p=Path(saved_video)
        if not p.is_file():return float('nan')
        stat=p.stat();return f"{p.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"


class MaskFrames:
    """Call Comfy's native background remover with bounded GPU input batches."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"bg_removal_model":("BACKGROUND_REMOVAL",),"image":("IMAGE",),
            "batch_size":("INT",{"default":1,"min":1,"max":8,"tooltip":"Frames sent to BiRefNet at once. One keeps GPU memory low."}),
            "release_previous_models":("BOOLEAN",{"default":True})}}
    RETURN_TYPES=("MASK",)
    FUNCTION="mask"
    CATEGORY=CATEGORY
    def mask(self,bg_removal_model,image,batch_size,release_previous_models):
        if release_previous_models:mm.unload_all_models();mm.soft_empty_cache()
        parts=[]
        try:
            for start in range(0,len(image),batch_size):
                mm.throw_exception_if_processing_interrupted()
                with torch.inference_mode():
                    parts.append(bg_removal_model.encode_image(image[start:start+batch_size]).cpu())
            return (torch.cat(parts),)
        finally:
            if release_previous_models:mm.unload_all_models();mm.soft_empty_cache()
