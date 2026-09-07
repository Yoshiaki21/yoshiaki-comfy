"""
Ported from Yoshiaki21/Image-Captioning-in-ComfyUI (a personal fork of
LarryJane491/Image-Captioning-in-ComfyUI). Kept faithful to that fork's
behavior, including its known bug-fix patches (cstr fallback, prefix
handling, IS_CHANGED) -- see docs/yoshiaki/tasks_done.md for what was and
wasn't touched during the port.

2026-09-08: the Save node was rewritten to consume the whole caption list at
once (INPUT_IS_LIST) and pair it 1:1 with the Load node's name list, and the
Load node now builds both of its lists from a single sorted directory scan.
See the class comments below for why.
"""

import os
import shutil
from PIL import Image
from PIL import ImageOps
import numpy as np
import torch
import comfy

# --- patch: cstr未import対策（本体側の既知バグ回避） ---
import logging
class _cstr_fallback:
    def __call__(self, msg): logging.warning(msg); return self
    def print(self): pass
    warning = error = property(lambda self: self)
cstr = _cstr_fallback()
# --- patch end ---

IMAGE_EXTENSIONS = ('.png',)
CAPTION_EXTENSION = '.txt'


def _first(value, default=None):
    # INPUT_IS_LIST = True のため全入力がリストで届く。単一値として扱う入力を取り出す。
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return value


def _as_list(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def list_image_files(path):
    # Load / Save の両方で使う「フォルダ内のPNG一覧」。大文字小文字を区別せず拡張子で
    # 絞り込み、ディレクトリは除外し、名前順にソートして順序を固定する。
    return sorted(
        f for f in os.listdir(path)
        if f.lower().endswith(IMAGE_EXTENSIONS) and os.path.isfile(os.path.join(path, f))
    )


class YoshiakiLoRACaptionSave:
    """
    Writes one caption .txt per entry in `namelist`, pairing the i-th caption
    in `text` with the i-th file name.

    Why INPUT_IS_LIST: `text` is normally fed from a list-output node
    (YoshiakiLLMCaptionGenerator / YoshiakiWD14Tagger, OUTPUT_IS_LIST). Without
    INPUT_IS_LIST ComfyUI calls this node once per caption (map_node_over_list)
    and the node has no way of knowing *which* image the current call belongs
    to -- the previous implementation guessed via "first name without a .txt"
    or an instance counter. The counter turned out to persist across queued
    prompts (ComfyUI caches node objects by node id in `caches.objects`), so an
    interrupted run or a folder with a different image count shifted every
    subsequent caption onto the wrong file name. Receiving the full list makes
    the pairing explicit and stateless.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "namelist": ("STRING", {"forceInput": True}),
                "path": ("STRING", {"forceInput": True}),
                "text": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "prefix": ("STRING", {"default": " "}),
                "output_path": ("STRING", {"default": "", "tooltip": "Leave empty to save into 'path' (default, no image copy). If set, both the caption .txt and a copy of the source image are written here instead."}),
                "overwrite": ("BOOLEAN", {"default": False, "tooltip": "Captions are always paired 1:1 with 'namelist' by position. Off (default): a name whose .txt already exists in the destination is skipped (existing files are never touched). On: every .txt (and image copy) is (re)written."}),
            }
        }

    INPUT_IS_LIST = True
    OUTPUT_NODE = True
    RETURN_TYPES = ()
    FUNCTION = "save_text_file"
    CATEGORY = "yoshiaki-comfy/LoRA"

    def save_text_file(self, text, path, namelist, prefix=" ", output_path="", overwrite=False):
        path = _first(path, "") or ""
        namelist = _first(namelist, "") or ""
        prefix = _first(prefix, " ")
        prefix = "" if prefix is None else str(prefix)
        output_path = _first(output_path, "") or ""
        overwrite = bool(_first(overwrite, False))
        texts = [t if isinstance(t, str) else "" for t in _as_list(text)]

        dest = output_path.strip() if output_path.strip() else path
        copy_image = os.path.abspath(dest) != os.path.abspath(path)

        if not os.path.exists(dest):
            cstr(f"The path `{dest}` doesn't exist! Creating it...").warning.print()
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError as e:
                cstr(f"The path `{dest}` could not be created! Is there write access?\n{e}").error.print()

        names = [line.strip() for line in namelist.splitlines() if line.strip()]

        if len(names) != len(texts):
            cstr(f"Name list has {len(names)} entries but {len(texts)} caption(s) were received; "
                 f"only the first {min(len(names), len(texts))} pair(s) will be written.").warning.print()

        if prefix.strip() == "":
            prefix = ""
        elif prefix.endswith(","):
            prefix += " "
        elif not prefix.endswith(", "):
            prefix += ", "

        written = []
        for name, caption in zip(names, texts):
            base_name, _ = os.path.splitext(name)
            file_path = os.path.join(dest, base_name + CAPTION_EXTENSION)

            if os.path.exists(file_path) and not overwrite:
                cstr(f"`{file_path}` already exists, skipping (overwrite is off).").warning.print()
                continue

            if caption.strip() == '':
                cstr(f"Caption for `{name}` is empty; writing prefix only.").warning.print()

            self.writeTextFile(file_path, caption, prefix)
            written.append(base_name)

            if copy_image:
                self.copy_source_image(path, dest, name, overwrite)

        cstr(f"Wrote {len(written)} caption file(s) to `{dest}`.").warning.print()
        return {"ui": {"string": texts}}

    def copy_source_image(self, src_dir, dest_dir, file_name, overwrite):
        src_image = os.path.join(src_dir, file_name)
        dst_image = os.path.join(dest_dir, file_name)

        if not os.path.exists(src_image):
            cstr(f"Source image `{src_image}` not found, skipping image copy.").warning.print()
            return

        if os.path.exists(dst_image) and not overwrite:
            return

        try:
            shutil.copy2(src_image, dst_image)
        except OSError as e:
            cstr(f"Unable to copy image to `{dst_image}`\n{e}").error.print()

    def writeTextFile(self, file, content, prefix):
        try:
            with open(file, 'w', encoding='utf-8', newline='\n') as f:
                content= prefix + content
                f.write(content)
        except OSError:
            cstr(f"Unable to save file `{file}`").error.print()


class YoshiakiLoRACaptionLoad:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "IMAGE",)
    RETURN_NAMES = ("Name list", "path", "Image list",)

    FUNCTION = "captionload"

    CATEGORY = "yoshiaki-comfy/LoRA"

    # Required for the {"ui": {"text": [...]}} image-count display to
    # actually reach the frontend (see js/yoshiaki-loracaption.js) --
    # without this ComfyUI doesn't forward "ui" data for a node that isn't
    # marked as an output node.
    OUTPUT_NODE = True

    # --- patch: pathが同じでも毎回フォルダを再スキャンさせる（IS_CHANGED未定義対策） ---
    @classmethod
    def IS_CHANGED(cls, path):
        return float("nan")
    # --- patch end ---

    def captionload(self, path):
        if not os.path.isdir(path):
            raise FileNotFoundError(f"path '{path} cannot be found.'")
        if len(os.listdir(path)) == 0:
            raise FileNotFoundError(f"No files in path '{path}'.")

        # `Name list` と `Image list` は必ず同じ1回の走査結果から作る。以前は名前一覧を
        # glob('*.png')、画像一覧を os.listdir + lower() で別々に集めていたため、Linux では
        # 大文字拡張子（.PNG）やドット始まりのファイルが片方にしか入らず、件数がずれていた。
        file_names = list_image_files(path)
        if len(file_names) == 0:
            raise FileNotFoundError(f"No PNG images found in path '{path}'.")

        text = '\n'.join(file_names)

        images = []
        for file_name in file_names:
            image_path = os.path.join(path, file_name)
            i = Image.open(image_path)
            i = ImageOps.exif_transpose(i)
            image = i.convert("RGB")
            image = np.array(image).astype(np.float32) / 255.0
            image = torch.from_numpy(image)[None,]
            images.append(image)

        # Batch every loaded image into a single IMAGE tensor -- this loop
        # naturally also handles the single-image case (the loop body just
        # never runs when there's nothing in images[1:]).
        image1 = images[0]
        for image2 in images[1:]:
            if image1.shape[1:] != image2.shape[1:]:
                image2 = comfy.utils.common_upscale(image2.movedim(-1, 1), image1.shape[2], image1.shape[1], "bilinear", "center").movedim(1, -1)
            image1 = torch.cat((image1, image2), dim=0)

        # Image count is shown on this node only (via "ui"), not sent to any
        # other node -- RETURN_TYPES stays at exactly the 3 declared outputs.
        return {
            "ui": {"text": [f"{len(images)} images"]},
            "result": (text, path, image1),
        }


NODE_CLASS_MAPPINGS = {
    "YoshiakiLoRACaptionSave": YoshiakiLoRACaptionSave,
    "YoshiakiLoRACaptionLoad": YoshiakiLoRACaptionLoad,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YoshiakiLoRACaptionSave": "Yoshiaki LoRA Caption Save",
    "YoshiakiLoRACaptionLoad": "Yoshiaki LoRA Caption Load",
}
