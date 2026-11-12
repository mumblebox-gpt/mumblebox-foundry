"""Input and memory controls for the isolated Virtual 360 Turntable experiment."""
import hashlib
import json
import math
import os
import torch
import torch.nn.functional as F
import folder_paths
import nodes
import comfy.model_management as mm

CATEGORY = "experiments/Virtual 360 Turntable"

class ReferenceImage:
    @classmethod
    def INPUT_TYPES(cls):
        files = sorted(folder_paths.get_filename_list("input")) if "input" in folder_paths.folder_names_and_paths else []
        if not files:
            files = sorted(f for f in os.listdir(folder_paths.get_input_directory())
                           if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
        return {"required": {"image": (["none"] + files, {"image_upload": True}),
                             "required_reference": ("BOOLEAN", {"default": False})}}
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "load"
    CATEGORY = CATEGORY
    def load(self, image, required_reference=False):
        if image == "none":
            if required_reference:
                raise ValueError("Upload your starting reference image before generating the turnaround sheet.")
            return (None,)
        return (nodes.LoadImage().load_image(image)[0],)
    @classmethod
    def IS_CHANGED(cls, image, required_reference=False):
        if image == "none":
            return str(required_reference)
        with open(folder_paths.get_annotated_filepath(image), "rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()
    @classmethod
    def VALIDATE_INPUTS(cls, image, required_reference=False):
        return True if image == "none" or folder_paths.exists_annotated_filepath(image) else "Choose an existing reference image."

class MemoryProfile:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "profile": (["Author video size + 4K sheet", "Lower memory - smaller sheet and video", "Custom"],),
            "width": ("INT", {"default":768,"min":256,"max":2048,"step":32}),
            "height": ("INT", {"default":768,"min":256,"max":2048,"step":32}),
            "length": ("INT", {"default":73,"min":22,"max":362,"step":17}),
            "feedforward_chunks": ("INT", {"default":4,"min":1,"max":64}),
            "attention_chunks": ("INT", {"default":8,"min":1,"max":56}),
            "decode_tile": ("INT", {"default":256,"min":128,"max":1024,"step":32}),
            "decode_frames": ("INT", {"default":32,"min":16,"max":128,"step":4}),
            "sheet_panel_size": ("INT", {"default":1024,"min":256,"max":2048,"step":32})
        }}
    RETURN_TYPES = ("INT","INT","INT","INT","INT","INT","INT","STRING","INT","INT")
    RETURN_NAMES = ("width","height","length","feedforward_chunks","attention_chunks","decode_tile","decode_frames","profile_note","sheet_width","sheet_height")
    FUNCTION = "select"
    CATEGORY = CATEGORY
    def select(self, profile, width, height, length, feedforward_chunks, attention_chunks, decode_tile, decode_frames, sheet_panel_size):
        if not torch.cuda.is_available():
            raise RuntimeError("This experiment requires a CUDA GPU. CPU-only generation is not enabled.")
        if profile.startswith("Author"):
            values = (768,768,73,4,8,256,32)
            panel = 1024
        elif profile.startswith("Lower"):
            values = (512,512,73,8,8,256,16)
            panel = 768
        else:
            if (length-5) % 17:
                raise ValueError("H3 length must be 5 + 17n, such as 73, 124 or 243.")
            values = (width,height,length,feedforward_chunks,attention_chunks,decode_tile,decode_frames)
            panel = sheet_panel_size
        return (*values, "Native offload, sequential stages and tiled decode; combined memory fit remains untested.", panel*4, panel)

class SplitTurnaround:
    """Crop four generated panels; never invent or regenerate view content."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "sheet": ("IMAGE",),
            "crop_rectangles": ("STRING", {"default":"[[0,0,0.25,1],[0.25,0,0.25,1],[0.5,0,0.25,1],[0.75,0,0.25,1]]",
                "multiline":True,"tooltip":"Four [x,y,width,height] rectangles, normalized 0-1: FRONT, SIDE, THREE-QUARTER, BACK. Adjust if the generated panel layout drifts."})
        }}
    RETURN_TYPES = ("IMAGE","IMAGE","IMAGE","IMAGE")
    RETURN_NAMES = ("front","side","three_quarter","back")
    FUNCTION = "split"
    CATEGORY = CATEGORY
    def split(self, sheet, crop_rectangles):
        rectangles = json.loads(crop_rectangles)
        if not isinstance(rectangles,list) or len(rectangles)!=4:
            raise ValueError("Four crop rectangles are required: front, side, three-quarter and back.")
        h,w = sheet.shape[1:3]
        crops=[]
        for r in rectangles:
            if not isinstance(r,list) or len(r)!=4 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in r):
                raise ValueError("Each crop is [x,y,width,height] using finite normalized coordinates.")
            x,y,cw,ch=r
            if min(x,y)<0 or min(cw,ch)<=0 or x+cw>1.000001 or y+ch>1.000001:
                raise ValueError("Crop rectangles must remain inside the generated sheet.")
            left,top,right,bottom=round(x*w),round(y*h),round((x+cw)*w),round((y+ch)*h)
            if min(right-left,bottom-top)<32:
                raise ValueError("Each turnaround view must be at least 32 pixels wide and tall.")
            crops.append(sheet[:1,top:bottom,left:right,:3].cpu())
        return tuple(crops)

def fit_canvas(image, mask, width, height, margin, background):
    image=image[:1,:,:,:3].cpu()
    mask=mask[:1].cpu().clamp(0,1)
    h,w=image.shape[1:3]
    scale=min(width*(1-margin*2)/w,height*(1-margin*2)/h)
    nw,nh=max(1,round(w*scale)),max(1,round(h*scale))
    rgb=F.interpolate(image.movedim(-1,1),(nh,nw),mode="bilinear",align_corners=False).movedim(1,-1)
    alpha=F.interpolate(mask[:,None],(nh,nw),mode="bilinear",align_corners=False).squeeze(1)
    canvas=torch.full((1,height,width,3),background)
    y,x=(height-nh)//2,(width-nw)//2
    canvas[:,y:y+nh,x:x+nw]=rgb*alpha[...,None]+background*(1-alpha[...,None])
    return canvas

class PrepareReferences:
    """Segment all four generated crops and release the sheet stage before video."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "bg_model":("BACKGROUND_REMOVAL",),
            "front":("IMAGE",),"side":("IMAGE",),"three_quarter":("IMAGE",),"back":("IMAGE",),
            "width":("INT",{"default":768,"min":256,"max":2048,"step":32}),
            "height":("INT",{"default":768,"min":256,"max":2048,"step":32}),
            "margin":("FLOAT",{"default":0.04,"min":0,"max":0.25,"step":0.01}),
            "background":("FLOAT",{"default":0.5,"min":0,"max":1,"step":0.01}),
            "release_previous_models":("BOOLEAN",{"default":True})
        }}
    RETURN_TYPES=("IMAGE","IMAGE","IMAGE","IMAGE","IMAGE")
    RETURN_NAMES=("front","side","three_quarter","back","review_all_four")
    FUNCTION="prepare"
    CATEGORY=CATEGORY
    def prepare(self,bg_model,front,side,three_quarter,back,width,height,margin,background,release_previous_models):
        if release_previous_models:
            mm.unload_all_models()
            mm.soft_empty_cache()
        prepared=[]
        for image in (front,side,three_quarter,back):
            mm.throw_exception_if_processing_interrupted()
            with torch.inference_mode():
                mask=bg_model.encode_image(image[:1])
            prepared.append(fit_canvas(image,mask,width,height,margin,background))
        if release_previous_models:
            mm.unload_all_models()
            mm.soft_empty_cache()
        return (*prepared,torch.cat(prepared))

class GuideFrames:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "length":("INT",{"default":73,"min":22,"max":362,"step":17}),
            "side_fraction":("FLOAT",{"default":0.25,"min":0.01,"max":0.99,"step":0.01}),
            "three_quarter_fraction":("FLOAT",{"default":0.125,"min":0.01,"max":0.99,"step":0.005}),
            "back_fraction":("FLOAT",{"default":0.5,"min":0.01,"max":0.99,"step":0.01})
        }}
    RETURN_TYPES=("INT","INT","INT")
    RETURN_NAMES=("side_frame","three_quarter_frame","back_frame")
    FUNCTION="frames"
    CATEGORY=CATEGORY
    def frames(self,length,side_fraction,three_quarter_fraction,back_fraction):
        indices=tuple(round(f*(length-1)) for f in (side_fraction,three_quarter_fraction,back_fraction))
        if (length-5)%17 or len(set(indices))!=3 or min(indices)<1 or max(indices)>=length-1:
            raise ValueError("Use three distinct internal guide frames and an H3 length of 5 + 17n.")
        return indices


class VideoPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "orbit_prompt":("STRING",{"multiline":True,"tooltip":"Pablo Dawson's published prompt is the baseline. Editing it changes the experiment."}),
            "subject_direction":("STRING",{"default":"","multiline":True,"tooltip":"Optional additional description of the same subject. Leave blank for the exact author prompt; do not request animation or changing parts."})
        }}
    RETURN_TYPES=("STRING",)
    RETURN_NAMES=("video_prompt",)
    FUNCTION="compose"
    CATEGORY=CATEGORY
    def compose(self,orbit_prompt,subject_direction):
        if not orbit_prompt.strip():
            raise ValueError("The video requires an orbit instruction.")
        return (orbit_prompt.strip()+("\n\n"+subject_direction.strip() if subject_direction.strip() else ""),)
