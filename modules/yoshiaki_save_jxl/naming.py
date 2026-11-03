"""
File / folder naming logic for YoshiakiSaveImageJXL.

Ported from audioscavenger/save-image-extended-comfyui (GPL-3.0), release 2.88
(`save_image_extended.py`): `generate_custom_name`, `find_keys_recursively`,
`cleanup_fileName`, `get_latest_counter`, `get_subfolder_path`. The goal is the
*same* folder / file names as upstream for the same keys, so the behavior
(including its quirks) is kept on purpose. Differences from upstream:

- extension branching and jobs.json code removed (this node only writes .jxl)
- `resolve_output_paths()` adds a guard so `../` can never escape ComfyUI's
  output directory (upstream only fixed the leading `/name` case in 2.44)
- upstream calls `locale.setlocale(locale.LC_TIME, '')` at import time; that is
  a process-wide side effect, so it is NOT ported. Only locale-dependent
  datetime codes (`%a`, `%b`, `%c`, `%p` ...) can differ from upstream.
- no ComfyUI imports, so this file can be unit-tested on its own
"""

import os
import re
from datetime import datetime
from pathlib import Path

OUTPUT_EXT = ".jxl"

COUNTER_POSITIONS = ["last", "first"]
DEFAULT_COUNTER_POSITION = "last"

# upstream: modelExtensions
MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt", ".bin", ".pth"]


def cleanup_file_name(file="", ext_to_remove=MODEL_EXTENSIONS):
    if isinstance(file, str):
        for ext in ext_to_remove:
            file = file.removesuffix(ext)
    return file


def find_keys_recursively(prompt, keys_to_find, found_values):
    """Self-updating recursive search; fills `found_values` (upstream semantics:
    the last match in iteration order wins)."""
    for key, value in prompt.items():
        if key in keys_to_find:
            # pythongosssss/ComfyUI-Custom-Scripts stores the value as a dict
            if isinstance(value, dict):
                value = value["content"] if "content" in value else ""

            if key in ["ckpt_path", "ckpt_name"]:
                value_path = Path(value)
                if "ckpt_path" in keys_to_find:
                    found_values["ckpt_path"] = cleanup_file_name(str(value_path.parent))
                elif "ckpt_name" in keys_to_find:
                    found_values["ckpt_name"] = cleanup_file_name(str(value_path.name))
            elif key in ["control_net_path", "control_net_name"]:
                value_path = Path(value)
                if "control_net_path" in keys_to_find:
                    found_values["control_net_path"] = cleanup_file_name(str(value_path.parent))
                elif "control_net_name" in keys_to_find:
                    found_values["control_net_name"] = cleanup_file_name(str(value_path.name))
            elif key in ["lora_path", "lora_name"]:
                value_path = Path(value)
                if "lora_path" in keys_to_find:
                    found_values["lora_path"] = cleanup_file_name(str(value_path.parent))
                elif "lora_name" in keys_to_find:
                    found_values["lora_name"] = cleanup_file_name(str(value_path.name))
            else:
                found_values[key] = cleanup_file_name(value)
        elif isinstance(value, dict):
            find_keys_recursively(value, keys_to_find, found_values)


def _find_for_key(prompt, node_key, found_values):
    if node_key == "ckpt_path":
        find_keys_recursively(prompt, ["ckpt_name", node_key], found_values)
    elif node_key == "control_net_path":
        find_keys_recursively(prompt, ["control_net_name", node_key], found_values)
    elif node_key == "lora_path":
        find_keys_recursively(prompt, ["lora_name", node_key], found_values)
    else:
        find_keys_recursively(prompt, [node_key], found_values)


def split_keys(keys_text):
    return [item.strip() for item in keys_text.split(",")]


def generate_custom_name(keys_to_extract, prefix, delimiter, prompt, resolution, timestamp, named_keys=False):
    custom_name = []

    if prefix:
        if "%" in prefix:
            custom_name.append(timestamp.strftime(prefix))
        else:
            custom_name.append(prefix)

    if prompt is not None and keys_to_extract != [""]:
        found_values = {}
        for key in keys_to_extract:
            if not key:
                continue

            value = None
            node, node_key = None, None

            # datetime format
            if "%" in key:
                value = timestamp.strftime(key)

            # subfolder: ./key or ../key or /key ==> last / is removed
            if "/" in key:
                values = re.split("/+", key)
                if values[0] in ["", ".", ".."]:
                    custom_name.append(values[0] + "/")
                    key = values[1]
                    if not key:
                        continue
                else:
                    key = values[0]

            # fixed string: 'xxx' or "xxx"
            if (key.startswith("'") and key.endswith("'")) or (key.startswith('"') and key.endswith('"')):
                value = key

            if value is None:
                split_key = key.split(".")
                if len(split_key) == 2:
                    if "" not in split_key:
                        if split_key[0].isdecimal():
                            # num.widget_name
                            node, node_key = split_key[0], split_key[1]
                            if node in prompt:
                                _find_for_key(prompt[node], node_key, found_values)
                            else:
                                print(f"[YoshiakiSaveImageJXL] info: node #{node} not found")
                                _find_for_key(prompt, node_key, found_values)
                        else:
                            # string.string = fixed string (known extensions removed)
                            value = cleanup_file_name(key)
                    else:
                        # ".string" / "string." / "." : kept as is (the dot acts as delimiter)
                        value = key
                else:
                    node_key = key
                    if node_key == "resolution":
                        value = resolution
                    else:
                        _find_for_key(prompt, node_key, found_values)

            if value is None:
                if node_key is not None:
                    if node_key in found_values:
                        if named_keys:
                            value = f"{node_key}={found_values[node_key]}"
                        else:
                            value = found_values[node_key]
                    if value is None:
                        value = node_key

            if isinstance(value, str):
                if node_key in ["ckpt_path", "control_net_path", "lora_path"]:
                    value = found_values[node_key]
                else:
                    value = cleanup_file_name(value)
            elif isinstance(value, float):
                value = float(f"{value:.10g}")

            custom_name.append(str(value))

    custom_name = list(filter(None, custom_name))
    custom_name = list(map(str.strip, custom_name))
    string_name = (
        delimiter.join(custom_name)
        .replace("/" + delimiter, "/")
        .replace(delimiter + "/", "/")
        .replace(delimiter + ".", ".")
    )
    string_name = re.sub(r"\s+", " ", string_name).strip(delimiter).strip("/").strip(delimiter).strip(".")
    return re.sub(r'[*?:"<>|]', "", string_name).replace("/", os.sep)


def get_latest_counter(folder_path, filename, counter_digits, counter_position, output_ext=OUTPUT_EXT):
    counter = 1
    if not os.path.exists(folder_path):
        return counter

    try:
        files = [f for f in os.listdir(folder_path) if f.endswith(output_ext)]
        ext_len = len(output_ext)
        if files:
            if counter_position not in COUNTER_POSITIONS:
                counter_position = DEFAULT_COUNTER_POSITION
            # issue/48: no filename -> files are just "0001.jxl"
            if not filename:
                counters = [
                    int(f[:counter_digits]) if (f[:counter_digits].isdecimal() and len(f) == (counter_digits + ext_len)) else 0
                    for f in files
                ]
            elif counter_position == "last":
                counters = [
                    int(f[-(ext_len + counter_digits):-ext_len]) if f[-(ext_len + counter_digits):-ext_len].isdecimal() else 0
                    for f in files if f.startswith(filename)
                ]
            else:
                counters = [
                    int(f[:counter_digits]) if f[:counter_digits].isdecimal() else 0
                    for f in files if f[counter_digits + 1:].startswith(filename)
                ]
            if counters:
                counter = max(counters) + 1
    except Exception as e:
        print(f"[YoshiakiSaveImageJXL] error while finding the latest counter: {e}")

    return counter


def build_image_name(filename, filename_prefix, delimiter, counter, counter_digits, counter_position, output_ext=OUTPUT_EXT):
    if counter_digits > 0:
        if filename:
            if counter_position == "last":
                return f"{filename}{delimiter}{counter:0{counter_digits}}{output_ext}"
            return f"{counter:0{counter_digits}}{delimiter}{filename}{output_ext}"
        return f"{counter:0{counter_digits}}{output_ext}"
    if filename:
        return f"{filename}{output_ext}"
    return f"{filename_prefix}{output_ext}"


def _is_within(path, root):
    path = os.path.normcase(os.path.abspath(path))
    root = os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives on Windows
        return False


def resolve_output_paths(output_dir, custom_foldername, custom_filename):
    """Returns (output_path, filename). Raises ValueError if the result would
    land outside `output_dir` (e.g. too many `../`)."""
    if custom_filename:
        full = Path(os.path.join(output_dir, custom_foldername, custom_filename))
        output_path, filename = full.parent, full.name
    else:
        output_path, filename = Path(os.path.join(output_dir, custom_foldername)), ""

    if not _is_within(output_path, output_dir):
        raise ValueError(
            f"[YoshiakiSaveImageJXL] refusing to save outside the output directory: "
            f"'{os.path.abspath(output_path)}' is not under '{os.path.abspath(output_dir)}'"
        )
    return output_path, filename


def get_subfolder_path(image_path, output_path):
    """Relative folder of image_path from output_path (OS separators, '.' at root)."""
    image_path = Path(os.path.abspath(image_path))
    output_path = Path(os.path.abspath(output_path))
    return str(image_path.relative_to(output_path).parent)


def now_local():
    return datetime.now().astimezone()
