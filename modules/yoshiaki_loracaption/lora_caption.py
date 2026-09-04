"""
Ported from Yoshiaki21/Image-Captioning-in-ComfyUI (a personal fork of
LarryJane491/Image-Captioning-in-ComfyUI). Kept faithful to that fork's
behavior, including its known bug-fix patches (cstr fallback, prefix
handling, IS_CHANGED) and its pre-existing upstream quirks -- see
docs/yoshiaki/tasks_done.md for what was and wasn't touched during the
port.
"""

import glob
import os
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


class YoshiakiLoRACaptionSave:
    def __init__(self):
        pass

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
            }
        }

    OUTPUT_NODE = True
    RETURN_TYPES = ()
    FUNCTION = "save_text_file"
    CATEGORY = "yoshiaki-comfy/LoRA"

    def save_text_file(self, text, path, namelist, prefix):

        if not os.path.exists(path):
            cstr(f"The path `{path}` doesn't exist! Creating it...").warning.print()
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as e:
                cstr(f"The path `{path}` could not be created! Is there write access?\n{e}").error.print()

        if text.strip() == '':
            cstr(f"There is no text specified to save! Text is empty.").error.print()

        namelistsplit = namelist.splitlines()
        namelistsplit = [i[:-4] for i in namelistsplit]

        if prefix.strip() == "":
            prefix = ""
        elif prefix.endswith(","):
            prefix += " "
        elif not prefix.endswith(", "):
            prefix += ", "

        file_extension = '.txt'
        filename = self.generate_filename(path, namelistsplit, file_extension)

        file_path = os.path.join(path, filename)
        self.writeTextFile(file_path, text, prefix)

        return (text, { "ui": { "string": text } } )

    def generate_filename(self, path, namelistsplit, extension):
        counter = 1
        filename = f"{namelistsplit[counter-1]}{extension}"
        while os.path.exists(os.path.join(path, filename)):
            counter += 1
            filename = f"{namelistsplit[counter-1]}{extension}"

        return filename

    def writeTextFile(self, file, content, prefix):
        try:
            with open(file, 'w', encoding='utf-8', newline='\n') as f:
                content= prefix + content
                f.write(content)
        except OSError:
            cstr(f"Unable to save file `{file}`").error.print()


def io_file_list(dir='', pattern='*.txt'):
    res = []
    for filename in glob.glob(os.path.join(dir, pattern)):
        res.append(filename)
    return res


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

    # --- patch: pathが同じでも毎回フォルダを再スキャンさせる（IS_CHANGED未定義対策） ---
    @classmethod
    def IS_CHANGED(cls, path):
        return float("nan")
    # --- patch end ---

    def captionload(self, path, pattern='*.png'):
        text = io_file_list(path, pattern)
        text = list(map(os.path.basename, text))
        text = '\n'.join(text)

        # image loader
        if not os.path.isdir(path):
            raise FileNotFoundError(f"path '{path} cannot be found.'")
        dir_files = os.listdir(path)
        if len(dir_files) == 0:
            raise FileNotFoundError(f"No files in path '{path}'.")

        # Filter files by extension
        valid_extensions = ['.png']
        dir_files = [f for f in dir_files if any(f.lower().endswith(ext) for ext in valid_extensions)]

        dir_files = [os.path.join(path, x) for x in dir_files]

        images = []
        image_count = 0

        for image_path in dir_files:
            if os.path.isdir(image_path) and os.path.ex:
                continue
            i = Image.open(image_path)
            i = ImageOps.exif_transpose(i)
            image = i.convert("RGB")
            image = np.array(image).astype(np.float32) / 255.0
            image = torch.from_numpy(image)[None,]
            images.append(image)
            image_count += 1

        if len(images) == 1:
            return (images[0], 1)
        elif len(images) > 1:
            image1 = images[0]
            for image2 in images[1:]:
                if image1.shape[1:] != image2.shape[1:]:
                    image2 = comfy.utils.common_upscale(image2.movedim(-1, 1), image1.shape[2], image1.shape[1], "bilinear", "center").movedim(1, -1)
                image1 = torch.cat((image1, image2), dim=0)

        return text, path, image1, len(images)


NODE_CLASS_MAPPINGS = {
    "YoshiakiLoRACaptionSave": YoshiakiLoRACaptionSave,
    "YoshiakiLoRACaptionLoad": YoshiakiLoRACaptionLoad,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YoshiakiLoRACaptionSave": "Yoshiaki LoRA Caption Save",
    "YoshiakiLoRACaptionLoad": "Yoshiaki LoRA Caption Load",
}
