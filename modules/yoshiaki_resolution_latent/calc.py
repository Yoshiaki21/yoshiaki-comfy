"""
Pure size calculation for YoshiakiResolutionLatent (spec: docs/yoshiaki/ResolutionLatent_Node_指示書.md ch.4).

No ComfyUI / torch imports here, so this module can be unit-tested on its own.
The same logic is implemented in js/yoshiaki-resolution-latent-calc.js for the
live preview; keep both in sync (tests/cases.json is shared by both tests).
"""

import math
import re

CUSTOM_LABEL = "カスタム"
ORIENT_LANDSCAPE = "横長"
ORIENT_PORTRAIT = "縦長"
ORIENTATIONS = [ORIENT_LANDSCAPE, ORIENT_PORTRAIT]

MIN_FIXED_SIDE = 64
DEFAULT_MAX_RESOLUTION = 16384  # nodes.MAX_RESOLUTION (ComfyUI 0.46.2)

_FIXED_RE = re.compile(r"^(\d+)\s*[x×X]\s*(\d+)$")
_NUM = r"(\d+(?:\.\d+)?|\.\d+)"
_RATIO_RE = re.compile(rf"^{_NUM}\s*:\s*{_NUM}$")
_DECIMAL_RE = re.compile(rf"^{_NUM}$")

INPUT_EXAMPLES = "入力例: 16:9 / 2.39:1 / 1.85 / 1152x896"


class CalcError(ValueError):
    pass


def spec_token(text):
    """The part before the first half-width space ("16:9 Widescreen" -> "16:9")."""
    return str(text).strip().split(" ", 1)[0]


def parse_spec(text):
    """Return ("ratio", rw, rh) or ("fixed", W, H). Raise CalcError when invalid."""
    token = spec_token(text)
    m = _FIXED_RE.match(token)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if w < MIN_FIXED_SIDE or h < MIN_FIXED_SIDE:
            raise CalcError(
                f"固定解像度 '{token}' の辺が{MIN_FIXED_SIDE}px未満です。"
                f"比率なら 16:9 のように ':' で書いてください"
            )
        return ("fixed", w, h)
    m = _RATIO_RE.match(token)
    if m:
        rw, rh = float(m.group(1)), float(m.group(2))
    else:
        m = _DECIMAL_RE.match(token)
        if not m:
            raise CalcError(f"比率 '{text}' を解析できません（{INPUT_EXAMPLES}）")
        rw, rh = float(m.group(1)), 1.0
    if rw <= 0 or rh <= 0:
        raise CalcError(f"比率 '{text}' は0より大きい値で書いてください（{INPUT_EXAMPLES}）")
    return ("ratio", rw, rh)


def round_to(x, m):
    """Round half up to a multiple of m (Python's round() is banker's rounding)."""
    return int(math.floor(x / m + 0.5)) * m


def orient(a, b, orientation):
    """Landscape: long side is the width. Portrait: long side is the height."""
    long_side, short_side = max(a, b), min(a, b)
    if orientation == ORIENT_PORTRAIT:
        return short_side, long_side
    return long_side, short_side


def required_multiple(preset_multiple, downscale, generic):
    if generic:
        return int(downscale)
    return math.lcm(int(preset_multiple), int(downscale))


def fix_multiple(multiple, req):
    """Round `multiple` up to a multiple of `req`. Returns (multiple, warning or None)."""
    multiple = int(multiple)
    if multiple % req == 0:
        return multiple, None
    fixed = -(-multiple // req) * req
    return fixed, f"倍数 {multiple} は必要倍数 {req} の倍数でないため {fixed} に切り上げました"


def compute(text, orientation, megapixels, multiple, req, mp_range=None,
            max_resolution=DEFAULT_MAX_RESOLUTION):
    """
    Returns {"kind", "width", "height", "mp", "multiple", "warnings"}.
    Raises CalcError for inputs that cannot produce the intended image.
    """
    warnings = []
    kind, a, b = parse_spec(text)
    m, warn = fix_multiple(multiple, req)
    if warn:
        warnings.append(warn)

    if kind == "ratio":
        rw, rh = orient(a, b, orientation)
        scale = math.sqrt(megapixels * 1024 * 1024 / (rw * rh))
        width = max(m, round_to(rw * scale, m))
        height = max(m, round_to(rh * scale, m))
        if mp_range and not (mp_range[0] <= megapixels <= mp_range[1]):
            warnings.append(
                f"メガピクセル {megapixels:.2f} が推奨範囲 {mp_range[0]}〜{mp_range[1]} の外です"
            )
    else:
        fw, fh = orient(a, b, orientation)
        width = max(m, round_to(fw, m))
        height = max(m, round_to(fh, m))
        if (width, height) != (fw, fh):
            warnings.append(f"固定解像度 {fw}x{fh} を倍数 {m} に合わせて {width}x{height} にしました")
        actual = width * height / (1024 * 1024)
        if mp_range and not (mp_range[0] <= actual <= mp_range[1]):
            warnings.append(
                f"メガピクセル {actual:.2f} が推奨範囲 {mp_range[0]}〜{mp_range[1]} の外です"
            )

    if width > max_resolution or height > max_resolution:
        raise CalcError(f"{width}x{height} は最大解像度 {max_resolution} を超えています")

    return {
        "kind": kind,
        "width": width,
        "height": height,
        "mp": width * height / (1024 * 1024),
        "multiple": m,
        "warnings": warnings,
    }
