"""
YoshiakiSaveImageJXL: save images as JPEG XL (.jxl) with save-image-extended
style file / folder naming, plus an XMP packet holding the parameters needed to
regenerate the image (spec: docs/yoshiaki/JXL_Save_Node_指示書.md).

The workflow itself is intentionally NOT embedded.

INPUT_IS_LIST = True so that `positive_text` / `negative_text` coming from a
list output can be paired with images by index (spec 6.3). Every input
therefore arrives as a list; widget values are taken from element 0 and the
images are flattened across all incoming batches.
"""

import logging
import os

import numpy
from PIL import Image

import pillow_jxl  # noqa: F401  importing registers the "JXL" format with Pillow

import folder_paths

from . import metadata as meta
from . import naming

NODE_VERSION = "1.0.0"

NODE_CLASS = meta.NODE_CLASS
NODE_DISPLAY_NAME = "Yoshiaki Save Image JXL"

# upstream (save-image-extended 2.88) defaults
DEFAULT_FILENAME_PREFIX = "ComfyUI"
DEFAULT_FILENAME_KEYS = "sampler_name, cfg, steps, %F %H-%M-%S"
DEFAULT_FOLDERNAME_PREFIX = ""
DEFAULT_FOLDERNAME_KEYS = "ckpt_name"
DEFAULT_DELIMITER = "-"
DEFAULT_COUNTER_DIGITS = 4


def _comfyui_version():
    try:
        import comfyui_version
        return str(comfyui_version.__version__)
    except Exception:
        return "unknown"


def _first(value, default=None):
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return value if value is not None else default


def _tensor_to_pil(image):
    arr = numpy.clip(255.0 * image.cpu().numpy(), 0, 255).astype(numpy.uint8)
    if arr.ndim == 3 and arr.shape[-1] == 1:
        arr = arr[..., 0]
    if arr.ndim == 3 and arr.shape[-1] == 2:
        return Image.fromarray(arr, mode="LA")
    return Image.fromarray(arr)  # RGB / RGBA / L (alpha kept as-is)


class YoshiakiSaveImageJXL:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "Images to save (batch supported)"}),
                "filename_prefix": ("STRING", {"default": DEFAULT_FILENAME_PREFIX, "multiline": False,
                                               "tooltip": "Fixed string prefixed to file name"}),
                "filename_keys": ("STRING", {"default": DEFAULT_FILENAME_KEYS, "multiline": True,
                                             "tooltip": "Comma separated keys added to the file name in order.\n"
                                                        "* widget name (e.g. `sampler_name`) or `id.widget` (e.g. `3.seed`)\n"
                                                        "* `resolution`, datetime formats (`%F %H-%M-%S`), `'fixed'` strings\n"
                                                        "* `ckpt_path` / `lora_path` / `control_net_path`, `.custom_string`\n"
                                                        "* unknown keys are used as fixed strings. The same applies to `foldername_keys`"}),
                "foldername_prefix": ("STRING", {"default": DEFAULT_FOLDERNAME_PREFIX, "multiline": False,
                                                 "tooltip": "Fixed string prefixed to subfolders"}),
                "foldername_keys": ("STRING", {"default": DEFAULT_FOLDERNAME_KEYS, "multiline": True,
                                               "tooltip": "Same rules as `filename_keys`. Create subfolders with `/` or `../` "
                                                          "(never outside the output folder)"}),
                "delimiter": ("STRING", {"default": DEFAULT_DELIMITER, "multiline": False,
                                         "tooltip": "Delimiter between values (first character only)"}),
                "counter_digits": ("INT", {"default": DEFAULT_COUNTER_DIGITS, "min": 0, "max": 8, "step": 1,
                                           "tooltip": "Digits of the image counter (continues from the highest existing "
                                                      ".jxl number). 0 = no counter"}),
                "counter_position": (naming.COUNTER_POSITIONS, {"default": naming.DEFAULT_COUNTER_POSITION,
                                                                "tooltip": "image-0001.jxl (last) or 0001-image.jxl (first)"}),
                "named_keys": ("BOOLEAN", {"default": False,
                                           "tooltip": "Prefix each value with its key name: prefix-seed=123-cfg=5.0-0001.jxl"}),
                "image_preview": ("BOOLEAN", {"default": True, "tooltip": "Show the saved images on the node"}),
                "quality": ("INT", {"default": 90, "min": 1, "max": 100, "step": 1,
                                    "tooltip": "JPEG XL quality (ignored when lossless)"}),
                "lossless": ("BOOLEAN", {"default": False, "tooltip": "Mathematically lossless (quality is ignored)"}),
                "effort": ("INT", {"default": 7, "min": 1, "max": 9, "step": 1,
                                   "tooltip": "Encoder effort: higher = smaller file, slower"}),
                "write_xmp": ("BOOLEAN", {"default": True,
                                          "tooltip": "Write generation parameters into XMP (the workflow is never embedded)"}),
                "primary_node": ("STRING", {"default": "", "multiline": False,
                                            "tooltip": "Node ID of the main sampler (e.g. 3). Empty = auto detect"}),
            },
            "optional": {
                "positive_text": ("STRING", {"forceInput": True,
                                             "tooltip": "Positive prompt actually used (e.g. wildcard result, "
                                                        "PromptTranslator combined_prompt)"}),
                "negative_text": ("STRING", {"forceInput": True, "tooltip": "Negative prompt actually used"}),
                "xmp_note": ("STRING", {"default": "", "multiline": True, "tooltip": "Free note written into XMP"}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO", "unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    INPUT_IS_LIST = True
    CATEGORY = "yoshiaki-comfy/image"
    DESCRIPTION = (
        "Saves images as JPEG XL with save-image-extended style file/folder naming, "
        "and writes regeneration parameters (seed, prompts, sampler, models, widget values) into XMP. "
        "The workflow itself is not embedded."
    )

    def save_images(self, images, filename_prefix, filename_keys, foldername_prefix, foldername_keys,
                    delimiter, counter_digits, counter_position, named_keys, image_preview,
                    quality, lossless, effort, write_xmp, primary_node,
                    positive_text=None, negative_text=None, xmp_note=None,
                    prompt=None, extra_pnginfo=None, unique_id=None):
        filename_prefix = _first(filename_prefix, "")
        filename_keys = _first(filename_keys, "")
        foldername_prefix = _first(foldername_prefix, "")
        foldername_keys = _first(foldername_keys, "")
        delimiter = _first(delimiter, "")
        counter_digits = int(_first(counter_digits, DEFAULT_COUNTER_DIGITS))
        counter_position = _first(counter_position, naming.DEFAULT_COUNTER_POSITION)
        named_keys = bool(_first(named_keys, False))
        image_preview = bool(_first(image_preview, True))
        quality = int(_first(quality, 90))
        lossless = bool(_first(lossless, False))
        effort = int(_first(effort, 7))
        write_xmp = bool(_first(write_xmp, True))
        primary_node = str(_first(primary_node, "") or "")
        xmp_note = _first(xmp_note, "") or ""
        prompt = _first(prompt)
        unique_id = _first(unique_id)

        frames = [img for batch in images for img in batch]
        if not frames:
            return {"ui": {"images": []}}

        if delimiter:
            delimiter = delimiter[0]

        timestamp = naming.now_local()
        first = _tensor_to_pil(frames[0])
        resolution = f"{first.width}x{first.height}"

        custom_foldername = naming.generate_custom_name(
            naming.split_keys(foldername_keys), foldername_prefix, delimiter, prompt, resolution, timestamp, named_keys)
        custom_filename = naming.generate_custom_name(
            naming.split_keys(filename_keys), filename_prefix, delimiter, prompt, resolution, timestamp, named_keys)

        output_path, filename = naming.resolve_output_paths(self.output_dir, custom_foldername, custom_filename)
        os.makedirs(output_path, exist_ok=True)
        counter = naming.get_latest_counter(output_path, filename, counter_digits, counter_position)

        # Everything that does not depend on the individual image is computed once.
        shared = None
        if write_xmp:
            shared = self._collect_shared(prompt, unique_id, primary_node)

        created_at = timestamp.isoformat(timespec="seconds")
        batch_size = len(frames)
        results = []
        for index, frame in enumerate(frames):
            img = first if index == 0 else _tensor_to_pil(frame)
            image_name = naming.build_image_name(
                filename, filename_prefix, delimiter, counter, counter_digits, counter_position)
            image_path = os.path.join(output_path, image_name)
            subfolder = naming.get_subfolder_path(image_path, self.output_dir)

            save_kwargs = {
                "format": "JXL",
                "lossless": lossless,
                "quality": quality,
                "effort": effort,
            }
            if write_xmp:
                save_kwargs["xmp"] = self._build_xmp(
                    shared, created_at, img, image_name, subfolder, index, batch_size,
                    lossless, quality, positive_text, negative_text, xmp_note)
                save_kwargs["compress_metadata"] = False  # plain "xml " box, not brob
            img.save(image_path, **save_kwargs)

            results.append({"filename": image_name, "subfolder": subfolder, "type": self.type})
            counter += 1

        if not image_preview:
            results = []
        return {"ui": {"images": results}}

    # -- XMP ---------------------------------------------------------------

    @staticmethod
    def _collect_shared(prompt, unique_id, primary_node):
        prompt = prompt if isinstance(prompt, dict) else {}
        nodes = meta.collect_nodes(prompt)
        seed, sampler_id = meta.resolve_seed_and_sampler(prompt, unique_id, primary_node)
        auto_pos = meta.auto_prompt_text(prompt, sampler_id, "positive")
        auto_neg = meta.auto_prompt_text(prompt, sampler_id, "negative")
        return {
            "nodes": nodes,
            "seed": seed,
            "sampler": meta.build_sampler_info(prompt, sampler_id),
            "models": meta.extract_models(nodes),
            "auto_positive": auto_pos,
            "auto_negative": auto_neg,
            "comfyui_version": _comfyui_version(),
        }

    @staticmethod
    def _prompt_for(values, index, auto):
        picked = meta.pick_for_batch(values, index)
        if picked is not None:
            return str(picked), "input"
        return auto

    def _build_xmp(self, shared, created_at, img, image_name, subfolder, index, batch_size,
                   lossless, quality, positive_text, negative_text, note):
        positive, positive_source = self._prompt_for(positive_text, index, shared["auto_positive"])
        negative, negative_source = self._prompt_for(negative_text, index, shared["auto_negative"])
        subfolder_json = "" if subfolder in ("", ".") else subfolder.replace(os.sep, "/").replace("\\", "/")

        parameters = meta.build_parameters(
            node_version=NODE_VERSION,
            comfyui_version=shared["comfyui_version"],
            created_at=created_at,
            image={
                "filename": image_name,
                "subfolder": subfolder_json,
                "width": img.width,
                "height": img.height,
                "batch_index": index,
                "batch_size": batch_size,
                "lossless": lossless,
                "quality": quality,
            },
            prompt_info={
                "positive": positive,
                "negative": negative,
                "positive_source": positive_source,
                "negative_source": negative_source,
            },
            seed=shared["seed"],
            sampler=shared["sampler"],
            models=shared["models"],
            note=note,
            nodes=shared["nodes"],
        )
        seed = shared["seed"]
        return meta.build_xmp(
            node_version=NODE_VERSION,
            created_at=created_at,
            parameters=parameters,
            seed_value=seed["value"] if seed else None,
            positive=positive,
            negative=negative,
            note=note,
        )


NODE_CLASS_MAPPINGS = {NODE_CLASS: YoshiakiSaveImageJXL}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_CLASS: NODE_DISPLAY_NAME}

logging.debug(f"[yoshiaki-comfy] {NODE_CLASS} {NODE_VERSION} loaded")
