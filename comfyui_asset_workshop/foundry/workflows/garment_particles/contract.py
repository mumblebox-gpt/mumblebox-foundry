"""Validated options shared by the garment wizard and its Comfy node."""
from pathlib import PurePosixPath
import re

MODES = ("text", "image", "sketch", "surprise")
AUTHOR = "https://github.com/garment-particles/GarmentParticles"
WEIGHTS = "https://huggingface.co/georgeNakayama/GarmentParticles"
EXAMPLE = "A fitted sleeveless waistcoat with a V-neck, open front and a straight hem."
GENERATION_PRESETS = {
    "quick": {"label": "Quick draft", "points": 2048, "steps": 60},
    "balanced": {"label": "Balanced (default)", "points": 4096, "steps": 100},
    "detail": {"label": "Higher detail", "points": 6144, "steps": 125},
}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch("[a-f0-9]{32}", value):
        raise ValueError("Invalid Garment Particles run.")
    return value


def options(data):
    mode = data.get("mode", "text")
    if mode not in MODES:
        raise ValueError("Choose a text description, reference image or sketch.")
    name = str(data.get("name", "")).strip()[:80] or "Garment"
    prompt = str(data.get("prompt", "")).strip()
    image = str(data.get("image", ""))
    back_image = str(data.get("back_image", ""))
    if mode == "text":
        if not 1 <= len(prompt) <= 500:
            raise ValueError("Describe your garment in 1 to 500 characters.")
        image = ""
    elif mode == "surprise":
        image, prompt = "", ""
    else:
        path = PurePosixPath(image)
        if not image or len(image) > 500 or path.is_absolute() or ".." in path.parts or "\\" in image or ":" in image:
            raise ValueError("Choose one garment image or sketch from the local inputs.")
        prompt = ""
    config = dict(name=name, mode=mode, prompt=prompt, image=image)
    if mode in ("image", "sketch") and back_image:
        path = PurePosixPath(back_image)
        if len(back_image) > 500 or path.is_absolute() or ".." in path.parts or "\\" in back_image or ":" in back_image:
            raise ValueError("Choose the back reference from the local inputs.")
        config["back_image"] = back_image
    for key, default, low, high in (("seed", 42, 0, 2147483647), ("points", GENERATION_PRESETS["balanced"]["points"], 100, 8192),
                                    ("steps", GENERATION_PRESETS["balanced"]["steps"], 2, 250)):
        value = data.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key.capitalize()} must be between {low} and {high}.")
        config[key] = value
    return config


def mesh_options(data):
    budget = data.get("budget", 20000)
    if type(budget) is not int or not 2000 <= budget <= 100000:
        raise ValueError("Choose a triangle budget from 2,000 to 100,000.")
    return {"budget": budget}

