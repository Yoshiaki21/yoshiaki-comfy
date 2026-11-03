"""
YoshiakiLoadImageJXL: load a JPEG XL (.jxl) image from the input folder like the
standard Load Image node, and read the regeneration parameters that
YoshiakiSaveImageJXL wrote into its XMP (spec: docs/yoshiaki/JXL_Load_Node_指示書.md).

The preview, upload button and metadata display live in js/yoshiaki-load-jxl.js
and the /yoshiaki/jxl/* routes (server.py), so nothing depends on the browser
being able to show JPEG XL.
"""

import hashlib
import logging
import os

import numpy as np
import torch
from PIL import Image, ImageSequence

import pillow_jxl  # noqa: F401  importing registers the "JXL" format with Pillow

from . import files
from . import jxl_boxes
from . import xmp_read

NODE_VERSION = "1.0.0"

NODE_CLASS = "YoshiakiLoadImageJXL"
NODE_DISPLAY_NAME = "Yoshiaki Load Image JXL"

_LOG_PREFIX = f"[{NODE_CLASS}]"

# Modes whose integer samples are 16 bit (or wider) and must not be squeezed to 8 bit.
_WIDE_INT_MODES = ("I;16", "I;16B", "I;16L", "I;16N", "I")


def _pillow(fn, arg):
    """node_helpers.pillow() (retries with LOAD_TRUNCATED_IMAGES) when available."""
    try:
        import node_helpers
        return node_helpers.pillow(fn, arg)
    except ImportError:
        return fn(arg)


def _target_device_dtype():
    try:
        import comfy.model_management as mm
        return mm.intermediate_device(), mm.intermediate_dtype()
    except (ImportError, AttributeError):
        return torch.device("cpu"), torch.float32


def open_image(path):
    return _pillow(Image.open, path)


def frame_to_arrays(frame):
    """(RGB float32 HxWx3 in 0..1, alpha float32 HxW in 0..1 or None) for one frame."""
    mode = frame.mode
    if mode in _WIDE_INT_MODES:
        gray = np.asarray(frame, dtype=np.float32) / 65535.0
        return np.repeat(np.clip(gray, 0.0, 1.0)[..., None], 3, axis=-1), None
    if mode == "F":
        gray = np.asarray(frame, dtype=np.float32)
        return np.repeat(np.clip(gray, 0.0, 1.0)[..., None], 3, axis=-1), None

    alpha = None
    if "A" in frame.getbands():
        alpha = np.asarray(frame.getchannel("A"), dtype=np.float32) / 255.0
    rgb = np.asarray(frame.convert("RGB"), dtype=np.float32) / 255.0
    return rgb, alpha


def decode_image(path):
    """(IMAGE [B,H,W,3], MASK [B,h,w]) following the standard LoadImage rules.

    Frames whose size differs from the first are skipped. Without alpha the mask
    is a 64x64 zero mask, exactly like the current standard LoadImage.
    """
    img = open_image(path)
    images = []
    masks = []
    size = None
    for frame in ImageSequence.Iterator(img):
        if size is None:
            size = frame.size
        elif frame.size != size:
            continue
        rgb, alpha = frame_to_arrays(frame)
        images.append(torch.from_numpy(rgb)[None,])
        if alpha is not None:
            masks.append((1.0 - torch.from_numpy(alpha))[None,])
        else:
            masks.append(torch.zeros((1, 64, 64), dtype=torch.float32))
    if not images:
        raise RuntimeError(f"{_LOG_PREFIX} no frames could be decoded: {path}")
    device, dtype = _target_device_dtype()
    image = torch.cat(images, dim=0).to(device=device, dtype=dtype)
    mask = torch.cat(masks, dim=0).to(device=device, dtype=dtype)
    return image, mask


def read_info(path):
    """(normalized info, parameters_raw). Never raises: failures become status 'none'."""
    try:
        xmp = jxl_boxes.read_xmp(path)
    except OSError as e:
        logging.warning(f"{_LOG_PREFIX} could not read XMP from {path}: {e}")
        info, raw = xmp_read.normalize(None)
        info["warnings"].append(f"could not read XMP: {e}")
        return info, raw
    try:
        return xmp_read.normalize(xmp)
    except Exception as e:  # metadata must never stop the image from loading
        logging.warning(f"{_LOG_PREFIX} could not interpret XMP of {path}: {e}")
        info, raw = xmp_read.normalize(None)
        info["warnings"].append(f"could not interpret XMP: {e}")
        return info, raw


class YoshiakiLoadImageJXL:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": (files.list_jxl_files(), {
                    "tooltip": "JPEG XL file in the ComfyUI input folder (subfolders included)",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING", "INT", "INT", "FLOAT", "STRING", "STRING")
    RETURN_NAMES = ("IMAGE", "MASK", "positive_text", "negative_text", "seed", "steps", "cfg",
                    "note", "parameters_json")
    OUTPUT_TOOLTIPS = (
        "Image",
        "1 - alpha (64x64 zeros when the image has no alpha, like Load Image)",
        "Positive prompt from the XMP (empty if none)",
        "Negative prompt from the XMP (empty if none)",
        "Main seed (0 if none)",
        "sampler.steps (0 if none)",
        "sampler.cfg (0.0 if none)",
        "xmp_note written when saving (empty if none)",
        "ycomfy:Parameters exactly as stored (empty if none)",
    )
    FUNCTION = "load_image"
    CATEGORY = "yoshiaki-comfy/image"
    DESCRIPTION = (
        "Loads a JPEG XL image from the input folder and outputs the prompts, seed and sampler "
        "settings that Yoshiaki Save Image JXL wrote into its XMP."
    )

    def load_image(self, image):
        path = files.resolve(image)
        out_image, out_mask = decode_image(path)
        info, parameters_raw = read_info(path)
        sampler = info.get("sampler") or {}
        steps = sampler.get("steps")
        cfg = sampler.get("cfg")
        result = (
            out_image,
            out_mask,
            info.get("positive") or "",
            info.get("negative") or "",
            xmp_read.seed_to_int(info.get("seed")),
            int(steps) if steps is not None else 0,
            float(cfg) if cfg is not None else 0.0,
            info.get("note") or "",
            parameters_raw or "",
        )
        return {"ui": {"jxl_info": [info]}, "result": result}

    @classmethod
    def IS_CHANGED(cls, image):
        try:
            path = files.resolve(image)
        except files.InvalidPathError:
            return ""  # VALIDATE_INPUTS reports the error
        m = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                m.update(chunk)
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        if not isinstance(image, str) or not image.lower().endswith(files.JXL_EXT):
            return f"Not a .jxl file: {image}"
        try:
            path = files.resolve(image)
        except files.InvalidPathError as e:
            return f"Invalid image path: {e}"
        if not os.path.isfile(path):
            return f"Invalid image file: {image}"
        return True


NODE_CLASS_MAPPINGS = {NODE_CLASS: YoshiakiLoadImageJXL}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_CLASS: NODE_DISPLAY_NAME}

logging.debug(f"[yoshiaki-comfy] {NODE_CLASS} {NODE_VERSION} loaded")
