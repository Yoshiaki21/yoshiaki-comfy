"""
Preset loading for YoshiakiResolutionLatent (spec ch.3).

The presets live in <repo root>/yoshiaki-resolution-latent.toml (git-ignored).
If it does not exist, it is created once from yoshiaki-resolution-latent.toml.example.
After that the file is hand-written: this module never writes it back (the
user's comments would be lost). Loaded once at import; edit + restart ComfyUI.
"""

import logging
import os
import shutil
import tomllib

from . import calc

LOG_PREFIX = "[yoshiaki-comfy] ResolutionLatent:"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOML_PATH = os.path.join(ROOT_DIR, "yoshiaki-resolution-latent.toml")
EXAMPLE_PATH = os.path.join(ROOT_DIR, "yoshiaki-resolution-latent.toml.example")

GENERIC_NAME = "汎用"

BUILTIN_GENERIC = {
    "name": GENERIC_NAME,
    "generic": True,
    "latent_channels": 4,
    "downscale": 8,
    "multiple": 16,
    "default_mp": 1.0,
    "mp_range": None,
    "aspect_ratios": ["1:1 Square", "5:4", "4:3", "3:2", "16:10", "16:9 Widescreen",
                      "21:9 Ultrawide", "2.39:1 Cinemascope"],
}

_REQUIRED = {
    "latent_channels": int,
    "downscale": int,
    "multiple": int,
    "default_mp": (int, float),
    "aspect_ratios": list,
}


def _warn(warnings, msg):
    logging.warning(f"{LOG_PREFIX} {msg}")
    warnings.append(msg)


def _is_type(value, types):
    # bool is a subclass of int; do not accept true/false as a number
    return isinstance(value, types) and not isinstance(value, bool)


def _validate(name, table, warnings):
    """Return a normalized preset dict, or None (skipped with a warning)."""
    if not isinstance(table, dict):
        _warn(warnings, f"[{name}] はテーブルではないためスキップします")
        return None
    for key, types in _REQUIRED.items():
        if key not in table:
            _warn(warnings, f"[{name}] に必須キー '{key}' が無いためスキップします")
            return None
        if not _is_type(table[key], types):
            _warn(warnings, f"[{name}] の '{key}' の型が不正なためスキップします")
            return None
    for key in ("latent_channels", "downscale", "multiple"):
        if table[key] < 1:
            _warn(warnings, f"[{name}] の '{key}' は1以上にしてください。スキップします")
            return None
    if table["default_mp"] <= 0:
        _warn(warnings, f"[{name}] の 'default_mp' は0より大きくしてください。スキップします")
        return None

    mp_range = table.get("mp_range")
    if mp_range is not None:
        if (not isinstance(mp_range, list) or len(mp_range) != 2
                or not all(_is_type(v, (int, float)) for v in mp_range)
                or mp_range[0] > mp_range[1]):
            _warn(warnings, f"[{name}] の 'mp_range' が不正なため無視します（[最小, 最大] の形で書く）")
            mp_range = None
        else:
            mp_range = [float(mp_range[0]), float(mp_range[1])]

    ratios = []
    for item in table["aspect_ratios"]:
        if not isinstance(item, str):
            _warn(warnings, f"[{name}] のアスペクト比 {item!r} が文字列でないためスキップします")
            continue
        try:
            calc.parse_spec(item)
        except calc.CalcError as e:
            _warn(warnings, f"[{name}] のアスペクト比 '{item}' をスキップします: {e}")
            continue
        if item == calc.CUSTOM_LABEL or item in ratios:
            continue
        ratios.append(item)
    if not ratios:
        _warn(warnings, f"[{name}] に有効なアスペクト比が無いためスキップします")
        return None

    downscale = table["downscale"]
    multiple = table["multiple"]
    if multiple % downscale:
        fixed = -(-multiple // downscale) * downscale
        _warn(warnings, f"[{name}] の multiple {multiple} を downscale {downscale} の倍数 {fixed} に切り上げます")
        multiple = fixed

    return {
        "name": name,
        "generic": bool(table.get("generic", False)),
        "latent_channels": table["latent_channels"],
        "downscale": downscale,
        "multiple": multiple,
        "default_mp": float(table["default_mp"]),
        "mp_range": mp_range,
        "aspect_ratios": ratios,
    }


def _ensure_file(warnings):
    if os.path.exists(TOML_PATH):
        return
    if not os.path.exists(EXAMPLE_PATH):
        _warn(warnings, f"{TOML_PATH} も {EXAMPLE_PATH} も無いため、内蔵の「{GENERIC_NAME}」だけで起動します")
        return
    try:
        shutil.copyfile(EXAMPLE_PATH, TOML_PATH)
        logging.info(f"{LOG_PREFIX} created {TOML_PATH} from the example file")
    except OSError as e:
        _warn(warnings, f"{TOML_PATH} を作成できません: {e}")


def load(path=None):
    """Return (presets: dict name -> preset (file order), warnings: list[str])."""
    warnings = []
    if path is None:
        _ensure_file(warnings)
        path = TOML_PATH
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        if not warnings:
            _warn(warnings, f"{path} が無いため、内蔵の「{GENERIC_NAME}」だけで起動します")
        data = {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        _warn(warnings, f"{path} を読めないため、内蔵の「{GENERIC_NAME}」だけで起動します: {e}")
        data = {}

    presets = {}
    for name, table in data.items():
        preset = _validate(name, table, warnings)
        if preset is not None:
            presets[name] = preset
    if not presets:
        if data:
            _warn(warnings, f"有効なプリセットが無いため、内蔵の「{GENERIC_NAME}」だけで起動します")
        presets = {GENERIC_NAME: dict(BUILTIN_GENERIC)}
    return presets, warnings


PRESETS, LOAD_WARNINGS = load()


def names():
    return list(PRESETS)


def fallback():
    """Preset used when a saved model name is no longer in the file."""
    for p in PRESETS.values():
        if p["generic"]:
            return p
    return dict(BUILTIN_GENERIC)


def all_aspect_ratios():
    """Union of every preset's list (file order, no duplicates) + カスタム."""
    seen = []
    for p in PRESETS.values():
        for r in p["aspect_ratios"]:
            if r not in seen:
                seen.append(r)
    return seen + [calc.CUSTOM_LABEL]
