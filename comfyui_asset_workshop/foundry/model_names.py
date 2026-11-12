"""Friendly labels for known weights and common local model components."""
import re
from pathlib import Path

NAMES = {
    "ccore_prop": "CCORE Q4_K_M", "ccore_prop_q8": "CCORE Q8_0",
    "ccore_vision_projector": "CCORE Vision Projector",
    "pixal_multiview": "Pixal3D Multi-View", "pixal_single": "Pixal3D Single Image",
    "dino": "DINOv3 NAF", "birefnet": "BiRefNet",
    "shape_vae": "TRELLIS.2 Shape VAE", "texture_vae": "TRELLIS.2 Texture VAE",
    "trellis2": "TRELLIS.2", "moge2": "MoGe 2", "moge2_fp16": "MoGe 2 FP16",
    "hairdeck_color": "HairDeck Color", "idol": "Idol",
    "idol_turbo_fast": "Idol Turbo Fast", "idol_turbo_slow": "Idol Turbo Quality",
}
PREFIXES = (
    ("minimax_h3_flf2v_lora", "MiniMax H3 360° Orbit LoRA"),
    ("minimax_h3_360", "MiniMax H3 360° Orbit LoRA"),
    ("minimax_h3_turbo", "MiniMax H3 Larry Turbo"),
    ("minimax_h3_video_vae", "MiniMax H3 Video VAE"),
    ("minimax_h3_fl2va", "MiniMax H3 FL2VA"),
    ("qwen3vl_32b_minimax_h3", "MiniMax H3 Text Encoder"),
    ("p-h3-image_text_encoder", "Pruna P-H3 Image Text Encoder"),
    ("p-h3-image_vae", "Pruna P-H3 Image VAE"),
    ("p-h3-image", "Pruna P-H3 Image"),
)


def model_name(key, metadata, path):
    filename = path.name
    if key in NAMES:
        return NAMES[key]
    for prefix, label in PREFIXES:
        if filename.casefold().startswith(prefix):
            return label
    explicit = metadata.get("display_name") or metadata.get("title")
    if explicit:
        return explicit
    name = Path(filename).stem
    if name.lower() in ("model", "pytorch_model", "diffusion_pytorch_model"):
        # A Hub snapshot directory is a commit hash, so use the repository
        # name from its enclosing models--owner--repository directory.
        repo = next((part.split("--", 2)[-1] for part in reversed(path.parts)
                     if part.startswith("models--") and part.count("--") >= 2), None)
        name = repo or next((part for part in reversed(path.parent.parts)
                             if part != "snapshots" and not re.fullmatch(r"[0-9a-f]{32,64}", part)), filename)
    if name.lower().startswith("hairdeck"):
        name = "HairDeck " + name[8:].strip("_- ")
    return re.sub(r"[_-]+", " ", name).strip() or filename
