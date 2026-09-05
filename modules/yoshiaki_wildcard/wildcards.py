"""
Wildcard prompt resolution for yoshiaki-comfy.

Trimmed personal fork of ComfyUI-Impact-Pack's `impact/wildcards.py`,
scoped down to just the two nodes this pack ships
(YoshiakiWildcardProcessor / YoshiakiWildcardEncode):

  * No content caching: `.txt` / `.yaml` wildcard files are re-read from
    disk on every resolution. Only a lightweight filename index
    (`available_wildcards`: key -> file path) is kept in memory, rebuilt
    via `wildcard_load()`.
  * No LoRA Block Weight (Inspire Pack) / no custom LOADER= (nunchaku)
    support -- `<lora:name>`, `<lora:name:weight>` and
    `<lora:name:model_weight:clip_weight>` are still supported.
"""

import logging
import os
import random
import re
import threading

import folder_paths
import nodes
import numpy as np
import yaml

from . import config

RE_WildCardQuantifier = re.compile(r"(?P<quantifier>\d+)#__(?P<keyword>[\w.\-+/*\\]+?)__", re.IGNORECASE)

available_wildcards = {}
_index_lock = threading.Lock()


def wildcard_normalize(x):
    return x.replace("\\", "/").replace(" ", "-").lower()


def get_search_dirs():
    cfg = config.get_config()
    if cfg["custom_wildcards_is_set"]:
        return [cfg["custom_wildcards"]]
    return [config.default_wildcards_path]


def wildcard_load():
    """Rebuild the wildcard filename index. Content is never cached -- only
    which keys exist and which file they live in."""
    os.makedirs(config.default_wildcards_path, exist_ok=True)

    index = {}
    for base in get_search_dirs():
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base, followlinks=True):
            for file in files:
                if file.endswith((".txt", ".yaml", ".yml")):
                    path = os.path.join(root, file)
                    rel = os.path.relpath(path, base)
                    key = wildcard_normalize(os.path.splitext(rel)[0])
                    index[key] = path

    with _index_lock:
        global available_wildcards
        available_wildcards = index

    logging.info(f"[yoshiaki-comfy] Wildcards indexed: {len(index)} file(s)")
    return index


def get_wildcard_list():
    with _index_lock:
        keys = sorted(available_wildcards.keys())
    return [f"__{k}__" for k in keys]


def find_wildcard_file(key):
    """
    Locate the file backing `key`.

    Returns (file_path, is_yaml). For a nested YAML key (e.g. "colors/warm")
    that isn't itself a filename, falls back to the parent file
    ("colors.yaml").

    Looks up `available_wildcards` (the real, on-disk paths recorded by
    wildcard_load()) instead of re-deriving a path from the normalized
    (lowercased) key. Reconstructing a path from the lowercased key only
    happened to work on case-insensitive filesystems (plain NTFS, WSL's
    /mnt/c) and silently failed to find any folder/file whose real name has
    uppercase letters on a case-sensitive one (native Linux ext4, e.g. Manjaro).
    """
    with _index_lock:
        path = available_wildcards.get(key)
    if path is not None:
        return path, path.endswith((".yaml", ".yml"))

    if "/" in key:
        parent = key.split("/", 1)[0]
        with _index_lock:
            parent_path = available_wildcards.get(parent)
        if parent_path is not None and parent_path.endswith((".yaml", ".yml")):
            return parent_path, True

    return None, False


def load_txt_wildcard(file_path):
    # Try UTF-8 first (the common case, including any non-ASCII wildcard
    # content) and only fall back to ISO-8859-1 for files that aren't valid
    # UTF-8. ISO-8859-1 decodes any byte sequence without error, so it must
    # come second -- trying it first (as this used to) meant the UTF-8
    # fallback below could never actually trigger, silently mojibake-ing any
    # non-ASCII content instead of reading it correctly.
    try:
        with open(file_path, "r", encoding="UTF-8") as f:
            lines = f.read().splitlines()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="ISO-8859-1") as f:
            lines = f.read().splitlines()
    return [x for x in lines if x.strip() and not x.strip().startswith("#")]


def _read_yaml(file_path):
    # See load_txt_wildcard() above for why UTF-8 must be tried first.
    try:
        with open(file_path, "r", encoding="UTF-8") as f:
            return yaml.load(f, Loader=yaml.FullLoader)
    except (yaml.reader.ReaderError, UnicodeDecodeError):
        with open(file_path, "r", encoding="ISO-8859-1") as f:
            return yaml.load(f, Loader=yaml.FullLoader)


def _extract_yaml_key(data, key):
    """Supports a top-level list/string/number, or one level of nesting
    (e.g. "colors/warm" inside `colors: {warm: [...]}`)."""
    if not data:
        return None

    def coerce(v):
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, (str, int, float)):
            return [str(v)]
        if isinstance(v, dict):
            out = []
            for inner in v.values():
                if isinstance(inner, list):
                    out.extend(str(x) for x in inner)
                elif isinstance(inner, (str, int, float)):
                    out.append(str(inner))
            return out or None
        return None

    if "/" in key:
        top, sub = key.split("/", 1)
        if top in data and isinstance(data[top], dict) and sub in data[top]:
            return coerce(data[top][sub])
        if key in data:
            return coerce(data[key])
        return None

    if key in data:
        return coerce(data[key])
    return None


def get_wildcard_value(key):
    """Always reads fresh from disk -- no content cache."""
    norm_key = wildcard_normalize(key)
    file_path, is_yaml = find_wildcard_file(norm_key)
    if file_path is None:
        return None

    try:
        if is_yaml:
            return _extract_yaml_key(_read_yaml(file_path), norm_key)
        return load_txt_wildcard(file_path)
    except Exception as e:
        logging.warning(f"[yoshiaki-comfy] Failed to read wildcard '{key}' from {file_path}: {e}")
        return None


def process_comment_out(text):
    lines = text.split('\n')

    lines0 = []
    flag = False
    for line in lines:
        if line.lstrip().startswith('#'):
            flag = True
            continue

        if len(lines0) == 0:
            lines0.append(line)
        elif flag:
            lines0[-1] += ' ' + line
            flag = False
        else:
            lines0.append(line)

    return '\n'.join(lines0)


def is_numeric_string(input_str):
    return re.match(r'^-?(\d*\.?\d+|\d+\.?\d*)$', input_str) is not None


def process(text, seed=None):
    text = process_comment_out(text)

    if seed is not None:
        random.seed(seed)
    random_gen = np.random.default_rng(seed)

    def replace_options(string):
        replacements_found = False

        def replace_option(match):
            nonlocal replacements_found
            options = match.group(1).split('|')

            multi_select_pattern = options[0].split('$$')
            select_range = None
            select_sep = ' '
            range_pattern = r'(\d+)(-(\d+))?'
            range_pattern2 = r'-(\d+)'
            wildcard_pattern = r"__([\w.\-+/*\\]+?)__"

            if len(multi_select_pattern) > 1:
                r = re.match(range_pattern, options[0])

                if r is None:
                    r = re.match(range_pattern2, options[0])
                    a = '1'
                    b = r.group(1).strip()
                else:
                    a = r.group(1).strip()
                    b = r.group(3)
                    if b is not None:
                        b = b.strip()
                    else:
                        b = a

                if r is not None:
                    if b is not None and is_numeric_string(a) and is_numeric_string(b):
                        select_range = int(a), int(b)
                    elif is_numeric_string(a):
                        x = int(a)
                        select_range = (x, x)

                    def expand_wildcard_or_return_string(options, pattern, wildcard_pattern):
                        matches = re.findall(wildcard_pattern, pattern)
                        if len(options) == 1 and matches:
                            return get_wildcard_options(pattern)
                        else:
                            options[0] = pattern
                            return options

                    if select_range is not None and len(multi_select_pattern) == 2:
                        options = expand_wildcard_or_return_string(options, multi_select_pattern[1], wildcard_pattern)
                    elif select_range is not None and len(multi_select_pattern) == 3:
                        select_sep = multi_select_pattern[1]
                        options = expand_wildcard_or_return_string(options, multi_select_pattern[2], wildcard_pattern)

            adjusted_probabilities = []
            total_prob = 0

            for option in options:
                parts = option.split('::', 1) if isinstance(option, str) else f"{option}".split('::', 1)

                if len(parts) == 2 and is_numeric_string(parts[0].strip()):
                    config_value = float(parts[0].strip())
                else:
                    config_value = 1

                adjusted_probabilities.append(config_value)
                total_prob += config_value

            normalized_probabilities = [prob / total_prob for prob in adjusted_probabilities]

            if select_range is None:
                select_count = 1
            else:
                def calculate_max(_options_length, _max_select_range):
                    return min(_max_select_range + 1, _options_length + 1) if _max_select_range > 0 else _options_length + 1

                def calculate_select_count(_max_value, _min_select_range, random_gen):
                    if max(_max_value, _min_select_range) <= 0:
                        return 0
                    elif _max_value == _min_select_range:
                        return _max_value
                    else:
                        _low_value = min(_min_select_range, _max_value)
                        _high_value = max(_min_select_range, _max_value)
                        return random_gen.integers(low=_low_value, high=_high_value, size=1)
                select_count = calculate_select_count(calculate_max(len(options), select_range[1]), select_range[0], random_gen)

            if select_count > len(options) or total_prob <= 1:
                random_gen.shuffle(options)
                selected_items = options
            else:
                selected_items = random_gen.choice(options, p=normalized_probabilities, size=select_count, replace=False)

            selected_items2 = [re.sub(r'^\s*[0-9.]+::', '', str(x), count=1) for x in selected_items]
            replacement = select_sep.join(selected_items2)

            replacements_found = True
            return replacement

        pattern = r'(?<!\\)\{((?:[^{}]|(?<=\\)[{}])*?)(?<!\\)\}'
        replaced_string = re.sub(pattern, replace_option, string)

        return replaced_string, replacements_found

    def get_wildcard_options(string):
        pattern = r"__([\w.\-+/*\\]+?)__"
        matches = re.findall(pattern, string)

        options = []

        for match in matches:
            keyword = match.lower()
            keyword = wildcard_normalize(keyword)

            wildcard_value = get_wildcard_value(keyword)

            if wildcard_value is not None:
                options.extend(wildcard_value)
            elif '*' in keyword:
                total_patterns = []
                found = False

                if keyword.startswith('*/') and len(keyword) > 2:
                    base_name = keyword[2:]

                    for k in available_wildcards.keys():
                        if (k == base_name or
                                k.endswith('/' + base_name) or
                                k.startswith(base_name + '/') or
                                ('/' + base_name + '/') in k):
                            v = get_wildcard_value(k)
                            if v:
                                total_patterns += v
                                found = True
                else:
                    subpattern = keyword.replace('*', '.*').replace('+', '\\+')
                    for k in available_wildcards.keys():
                        if re.match(subpattern, k) is not None or re.match(subpattern, k + '/') is not None:
                            v = get_wildcard_value(k)
                            if v:
                                total_patterns += v
                                found = True

                if found:
                    options.extend(total_patterns)

        return options

    def replace_wildcard(string):
        pattern = r"__([\w.\-+/*\\]+?)(?:#(\d+))?__"
        matches = re.findall(pattern, string)

        replacements_found = False

        for match, fixed_index in matches:
            keyword = match.lower()
            keyword = wildcard_normalize(keyword)
            full_token = f"__{match}#{fixed_index}__" if fixed_index else f"__{match}__"

            if fixed_index:
                # Fixed-line selection (__name#N__): only allowed for an exact,
                # single .txt wildcard file. N is 1-based over the filtered
                # (comment/blank-stripped) option list, matching random selection.
                if '*' in keyword:
                    raise ValueError(
                        f"[yoshiaki-comfy] Fixed-line wildcard syntax cannot be combined "
                        f"with a glob pattern: '{full_token}'")

                file_path, is_yaml = find_wildcard_file(keyword)
                if file_path is None:
                    raise ValueError(
                        f"[yoshiaki-comfy] Wildcard file not found for '__{keyword}__' "
                        f"(used with fixed-line syntax '{full_token}')")
                if is_yaml:
                    raise ValueError(
                        f"[yoshiaki-comfy] Fixed-line wildcard syntax only supports .txt "
                        f"wildcard files; '__{keyword}__' resolves to a YAML source "
                        f"('{full_token}')")

                options = get_wildcard_value(keyword)
                if not options:
                    raise ValueError(
                        f"[yoshiaki-comfy] Wildcard '__{keyword}__' has no usable lines "
                        f"for fixed-line syntax '{full_token}'")

                idx = int(fixed_index)
                if idx < 1 or idx > len(options):
                    raise ValueError(
                        f"[yoshiaki-comfy] Fixed-line index {idx} is out of range for "
                        f"'__{keyword}__' (valid range: 1-{len(options)}, '{full_token}')")

                selected_item = options[idx - 1]
                replacement = re.sub(r'^\s*[0-9.]+::', '', selected_item, count=1)
                replacements_found = True
                string = string.replace(full_token, replacement, 1)
                continue

            options = get_wildcard_value(keyword)

            if options is not None:
                adjusted_probabilities = []
                total_prob = 0
                for option in options:
                    parts = option.split('::', 1)
                    if len(parts) == 2 and is_numeric_string(parts[0].strip()):
                        config_value = float(parts[0].strip())
                    else:
                        config_value = 1

                    adjusted_probabilities.append(config_value)
                    total_prob += config_value

                normalized_probabilities = [prob / total_prob for prob in adjusted_probabilities]
                selected_item = random_gen.choice(options, p=normalized_probabilities, replace=False)
                replacement = re.sub(r'^\s*[0-9.]+::', '', selected_item, count=1)
                replacements_found = True
                string = string.replace(f"__{match}__", replacement, 1)
            elif '*' in keyword:
                total_patterns = []
                found = False

                if keyword.startswith('*/') and len(keyword) > 2:
                    base_name = keyword[2:]

                    for k in available_wildcards.keys():
                        if (k == base_name or
                                k.endswith('/' + base_name) or
                                k.startswith(base_name + '/') or
                                ('/' + base_name + '/') in k):
                            v = get_wildcard_value(k)
                            if v:
                                total_patterns += v
                                found = True
                else:
                    subpattern = keyword.replace('*', '.*').replace('+', '\\+')
                    for k in available_wildcards.keys():
                        if re.match(subpattern, k) is not None or re.match(subpattern, k + '/') is not None:
                            v = get_wildcard_value(k)
                            if v:
                                total_patterns += v
                                found = True

                if found:
                    replacement = random_gen.choice(total_patterns)
                    replacements_found = True
                    string = string.replace(f"__{match}__", replacement, 1)
            elif '/' not in keyword:
                string_fallback = string.replace(f"__{match}__", f"__*/{match}__", 1)
                string, replacements_found = replace_wildcard(string_fallback)

        return string, replacements_found

    replace_depth = 100
    stop_unwrap = False
    while not stop_unwrap and replace_depth > 1:
        replace_depth -= 1

        option_quantifier = [e.groupdict() for e in RE_WildCardQuantifier.finditer(text)]
        for match in option_quantifier:
            keyword = match['keyword'].lower()
            quantifier = int(match['quantifier']) if match['quantifier'] else 1
            replacement = '__|__'.join([keyword, ] * quantifier)
            wilder_keyword = keyword.replace('*', '\\*')
            RE_TEMP = re.compile(fr"(?P<quantifier>\d+)#__(?P<keyword>{wilder_keyword})__", re.IGNORECASE)
            text = RE_TEMP.sub(f"__{replacement}__", text)

        pass1, is_replaced1 = replace_options(text)

        while is_replaced1:
            pass1, is_replaced1 = replace_options(pass1)

        text, is_replaced2 = replace_wildcard(pass1)
        stop_unwrap = not is_replaced1 and not is_replaced2

    return text


def extract_lora_values(string):
    """Parses `<lora:name>`, `<lora:name:weight>` and
    `<lora:name:model_weight:clip_weight>`. Any extra non-numeric segment
    (e.g. LBW=/LOADER= syntax from upstream Impact-Pack) is ignored rather
    than erroring, since this pack doesn't apply it."""
    pattern = r'<lora:([^>]+)>'
    matches = re.findall(pattern, string)

    added = set()
    result = []
    for match in matches:
        item = match.strip(':').split(':')
        if not item or not item[0]:
            continue

        lora = item[0]
        weights = [float(x) for x in item[1:] if is_numeric_string(x)]
        a = weights[0] if len(weights) > 0 else 1.0
        b = weights[1] if len(weights) > 1 else a

        if lora not in added:
            result.append((lora, a, b))
            added.add(lora)

    return result


def remove_lora_tags(string):
    return re.sub(r'<lora:[^>]+>', '', string)


def resolve_lora_name(lora_name_cache, name):
    if os.path.exists(name):
        return name

    if len(lora_name_cache) == 0:
        lora_name_cache.extend(folder_paths.get_filename_list("loras"))

    for x in lora_name_cache:
        if x.endswith(name):
            return x

    return None


def process_with_loras(wildcard_opt, model, clip, clip_encoder=None, seed=None, processed=None):
    """
    Process wildcard text (including `<lora:...>` tags) into (model, clip, conditioning).

    :param wildcard_opt: wildcard text
    :param model: model
    :param clip: clip
    :param clip_encoder: optional custom encoder such as adv_cliptext_encode
    :param seed: seed for populating
    :param processed: output list -- [pass1, pass2, pass3] will be appended
    :return: model, clip, conditioning
    """
    lora_name_cache = []

    pass1 = process(wildcard_opt, seed)
    loras = extract_lora_values(pass1)
    pass2 = remove_lora_tags(pass1)

    for lora_name, model_weight, clip_weight in loras:
        lora_name_ext = lora_name.split('.')
        if ('.' + lora_name_ext[-1]) not in folder_paths.supported_pt_extensions:
            lora_name = lora_name + ".safetensors"

        orig_lora_name = lora_name
        resolved_lora_name = resolve_lora_name(lora_name_cache, lora_name)

        if resolved_lora_name is not None:
            path = folder_paths.get_full_path("loras", resolved_lora_name)
        else:
            path = None

        if path is not None:
            logging.info(f"[yoshiaki-comfy] LOAD LORA: {resolved_lora_name}: {model_weight}, {clip_weight}")
            model, clip = nodes.LoraLoader().load_lora(model, clip, resolved_lora_name, model_weight, clip_weight)
        else:
            logging.warning(f"[yoshiaki-comfy] LORA NOT FOUND: {orig_lora_name}")

    pass3 = [x.strip() for x in pass2.split("BREAK")]
    pass3 = [x for x in pass3 if x != '']

    if len(pass3) == 0:
        pass3 = ['']

    result = None

    for prompt in pass3:
        if clip_encoder is None:
            cur = nodes.CLIPTextEncode().encode(clip, prompt)[0]
        else:
            cur = clip_encoder.encode(clip, prompt)[0]

        if result is not None:
            result = nodes.ConditioningConcat().concat(result, cur)[0]
        else:
            result = cur

    if processed is not None:
        processed.append(pass1)
        processed.append(pass2)
        processed.append(pass3)

    return model, clip, result
