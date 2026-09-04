"""
Ported from Yoshiaki21/ComfyUI-WD14-Tagger (a personal fork of
pythongosssss/ComfyUI-WD14-Tagger, MIT licensed) -- kept faithful to that
fork's behavior and its own additions (exclude_tags wildcard matching via
fnmatch, tag priority reordering, CPU-only onnxruntime by default).

Dropped during the port (see docs/yoshiaki/tasks_done.md):
  * The canvas-wide "right-click any image -> quick tag" context menu
    feature and its backing /pysssss/wd14tagger/tag HTTP route -- unused,
    and the node itself (wired into a workflow) is unaffected by its
    removal.
  * The generic pysssss.py legacy-JS-install machinery (see helpers.py).
"""

# https://huggingface.co/spaces/SmilingWolf/wd-v1-4-tags

import csv
import fnmatch
import logging
import os

import aiohttp
import comfy.utils
import folder_paths
import numpy as np
import onnxruntime as ort
from onnxruntime import InferenceSession
from PIL import Image

from .helpers import download_to_file, get_ext_dir, load_config, update_node_status, wait_for_async
from .tag_priority import is_reorder_enabled, reorder_general_tags

config = load_config()

defaults = {
    "model": "wd-v1-4-moat-tagger-v2",
    "threshold": 0.35,
    "character_threshold": 0.85,
    "replace_underscore": False,
    "trailing_comma": False,
    "exclude_tags": "",
    "ortProviders": ["CPUExecutionProvider"],
    "HF_ENDPOINT": "https://huggingface.co",
}
defaults.update(config.get("settings", {}))

# Saved inside this pack's own folder (modules/yoshiaki_wd14tagger/models/,
# git-ignored) rather than ComfyUI's shared models/ dir -- this node is the
# only thing that uses these files.
models_dir = get_ext_dir("models", mkdir=True)
known_models = list(config["models"].keys())

logging.info("[yoshiaki-comfy] WD14 Tagger available ORT providers: " + ", ".join(ort.get_available_providers()))
logging.info("[yoshiaki-comfy] WD14 Tagger using ORT providers: " + ", ".join(defaults["ortProviders"]))


def get_installed_models():
    models = filter(lambda x: x.endswith(".onnx"), os.listdir(models_dir))
    models = [m for m in models if os.path.exists(os.path.join(models_dir, os.path.splitext(m)[0] + ".csv"))]
    return models


async def tag(image, model_name, threshold=0.35, character_threshold=0.85, exclude_tags="", replace_underscore=True, trailing_comma=False, client_id=None, node=None):
    if model_name.endswith(".onnx"):
        model_name = model_name[0:-5]
    installed = list(get_installed_models())
    if not any(model_name + ".onnx" in s for s in installed):
        await download_model(model_name, client_id, node)

    name = os.path.join(models_dir, model_name + ".onnx")
    model = InferenceSession(name, providers=defaults["ortProviders"])

    input = model.get_inputs()[0]
    height = input.shape[1]

    # Reduce to max size and pad with white
    ratio = float(height)/max(image.size)
    new_size = tuple([int(x*ratio) for x in image.size])
    image = image.resize(new_size, Image.LANCZOS)
    square = Image.new("RGB", (height, height), (255, 255, 255))
    square.paste(image, ((height-new_size[0])//2, (height-new_size[1])//2))

    image = np.array(square).astype(np.float32)
    image = image[:, :, ::-1]  # RGB -> BGR
    image = np.expand_dims(image, 0)

    # Read all tags from csv and locate start of each category
    tags = []
    general_index = None
    character_index = None
    with open(os.path.join(models_dir, model_name + ".csv")) as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if general_index is None and row[2] == "0":
                general_index = reader.line_num - 2
            elif character_index is None and row[2] == "4":
                character_index = reader.line_num - 2
            if replace_underscore:
                tags.append(row[1].replace("_", " "))
            else:
                tags.append(row[1])

    label_name = model.get_outputs()[0].name
    probs = model.run([label_name], {input.name: image})[0]

    result = list(zip(tags, probs[0]))

    general = [item for item in result[general_index:character_index] if item[1] > threshold]
    character = [item for item in result[character_index:] if item[1] > character_threshold]

    # generalタグ確定後、characterとの合成前に優先度並べ替えを適用
    # (キャラ名は最優先固定のため、reorder対象はgeneralのみ)
    if is_reorder_enabled():
        general = reorder_general_tags(general)

    all = character + general
    # exclude_tagsをワイルドカード対応（fnmatch）でフィルタする
    # 例: "* hair" -> "brown hair", "long hair" などを除外
    remove = [s.strip() for s in exclude_tags.lower().split(",") if s.strip()]
    all = [
        tag for tag in all
        if not any(fnmatch.fnmatch(tag[0].lower(), pattern) for pattern in remove)
    ]

    res = ("" if trailing_comma else ", ").join((item[0].replace("(", "\\(").replace(")", "\\)") + (", " if trailing_comma else "") for item in all))

    return res


async def download_model(model, client_id, node):
    hf_endpoint = os.getenv("HF_ENDPOINT", defaults["HF_ENDPOINT"])
    if not hf_endpoint.startswith("https://"):
        hf_endpoint = f"https://{hf_endpoint}"
    if hf_endpoint.endswith("/"):
        hf_endpoint = hf_endpoint.rstrip("/")

    url = config["models"][model]
    url = url.replace("{HF_ENDPOINT}", hf_endpoint)
    url = f"{url}/resolve/main/"
    async with aiohttp.ClientSession() as session:
        async def update_callback(perc):
            message = ""
            if perc < 100:
                message = f"Downloading {model}"
            update_node_status(client_id, node, message, perc)

        try:
            await download_to_file(
                f"{url}model.onnx", os.path.join(models_dir, f"{model}.onnx"), update_callback, session=session)
            await download_to_file(
                f"{url}selected_tags.csv", os.path.join(models_dir, f"{model}.csv"), update_callback, session=session)
        except aiohttp.client_exceptions.ClientConnectorError:
            logging.error("[yoshiaki-comfy] WD14 Tagger: unable to download model. Download files manually or set the HF_ENDPOINT environment variable to a mirror.")
            raise

        update_node_status(client_id, node, None)


class YoshiakiWD14Tagger:
    @classmethod
    def INPUT_TYPES(s):
        extra = [name for name, _ in (os.path.splitext(m) for m in get_installed_models()) if name not in known_models]
        models = known_models + extra
        return {"required": {
            "image": ("IMAGE", ),
            "model": (models, {"default": defaults["model"]}),
            "threshold": ("FLOAT", {"default": defaults["threshold"], "min": 0.0, "max": 1, "step": 0.05}),
            "character_threshold": ("FLOAT", {"default": defaults["character_threshold"], "min": 0.0, "max": 1, "step": 0.05}),
            "replace_underscore": ("BOOLEAN", {"default": defaults["replace_underscore"]}),
            "trailing_comma": ("BOOLEAN", {"default": defaults["trailing_comma"]}),
            "exclude_tags": ("STRING", {"default": defaults["exclude_tags"]}),
        }}

    RETURN_TYPES = ("STRING",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "tag"
    OUTPUT_NODE = True

    CATEGORY = "yoshiaki-comfy/LLM"

    def tag(self, image, model, threshold, character_threshold, exclude_tags="", replace_underscore=False, trailing_comma=False):
        tensor = image*255
        tensor = np.array(tensor, dtype=np.uint8)

        pbar = comfy.utils.ProgressBar(tensor.shape[0])
        tags = []
        for i in range(tensor.shape[0]):
            img = Image.fromarray(tensor[i])
            tags.append(wait_for_async(lambda: tag(img, model, threshold, character_threshold, exclude_tags, replace_underscore, trailing_comma)))
            pbar.update(1)
        return {"ui": {"tags": tags}, "result": (tags,)}


NODE_CLASS_MAPPINGS = {
    "YoshiakiWD14Tagger": YoshiakiWD14Tagger,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "YoshiakiWD14Tagger": "Yoshiaki WD14 Tagger",
}
