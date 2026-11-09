"""Bounded local reference preparation and the pinned vision runtime protocol."""
import base64
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ...artifacts import owned_path
from .contract import IMAGE_MAX_TOKENS


def prepare_reference(root, name):
    path = owned_path(root, Path(root) / name)
    if not path.is_file() or path.stat().st_size > 20 * 1024**2:
        raise ValueError("Upload a reference image smaller than 20 MB.")
    try:
        with Image.open(path, formats=("PNG", "JPEG", "WEBP")) as source:
            if source.width * source.height > 40_000_000 or source.n_frames != 1:
                raise ValueError("Use one still reference image under 40 megapixels.")
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            prepared = Image.new("RGB", image.size, "white")
            prepared.paste(image, mask=image.getchannel("A"))
            output = BytesIO()
            prepared.save(output, "PNG")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
        raise ValueError("The reference could not be read as a PNG, JPEG or WebP image.") from error
    payload = output.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def arguments(projector, device):
    return ["--mmproj", str(projector), "--mmproj-device", device,
            "--image-min-tokens", str(IMAGE_MAX_TOKENS), "--image-max-tokens", str(IMAGE_MAX_TOKENS)]


def content(prompt, image):
    encoded = base64.b64encode(image).decode("ascii")
    return [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}},
            {"type": "text", "text": prompt}]
