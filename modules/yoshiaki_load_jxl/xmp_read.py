"""
Parse the XMP written by YoshiakiSaveImageJXL and normalize it
(spec: docs/yoshiaki/JXL_Load_Node_指示書.md 4.2-4.4; the XMP itself is defined by
docs/yoshiaki/JXL_Save_Node_指示書.md ch.5, which this module must not change).

`normalize()` is the single source for both the node outputs and the `/info`
route, so what the node shows and what it outputs can never disagree.

No ComfyUI imports here so the logic can be tested on its own.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET

from yoshiaki_save_jxl.metadata import (
    NODE_CLASS as SAVE_NODE_CLASS,
    NS_DC,
    NS_RDF,
    NS_XMP,
    NS_YCOMFY,
    SCHEMA_ID,
    SCHEMA_VERSION,
)

_LOG_PREFIX = "[YoshiakiLoadImageJXL]"

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_NONE = "none"
STATUS_UNSUPPORTED = "unsupported_version"

_YCOMFY_PROPS = ("Parameters", "SchemaVersion", "Seed", "PositivePrompt", "NegativePrompt", "Note")
_SAMPLER_INT = ("steps",)
_SAMPLER_FLOAT = ("cfg", "denoise")
_SAMPLER_STR = ("sampler_name", "scheduler")
_MODEL_STRENGTHS = ("strength_model", "strength_clip", "strength")
_SEED_RE = re.compile(r"^-?\d+$")
# "ComfyUI / yoshiaki-comfy YoshiakiSaveImageJXL 1.0.0"
_CREATOR_RE = re.compile(r"yoshiaki-comfy\s+(\S+)\s+(\S+)")


# ---------------------------------------------------------------------------
# 4.2 XMP parsing
# ---------------------------------------------------------------------------

def _q(ns, name):
    return f"{{{ns}}}{name}"


def _descriptions(root):
    """Every rdf:Description, wherever it is (there may be more than one)."""
    if root.tag == _q(NS_RDF, "Description"):
        yield root
    yield from root.iter(_q(NS_RDF, "Description"))


def _find_prop(descriptions, ns, name):
    """Text of the first ns:name property, element form or attribute form."""
    tag = _q(ns, name)
    for desc in descriptions:
        if tag in desc.attrib:
            return desc.attrib[tag]
        el = desc.find(tag)
        if el is not None:
            return el.text or ""
    return None


def _find_dc_description(descriptions):
    tag = _q(NS_DC, "description")
    for desc in descriptions:
        el = desc.find(tag)
        if el is None:
            continue
        items = list(el.iter(_q(NS_RDF, "li")))
        if not items:
            if el.text and el.text.strip():
                return el.text
            continue
        lang_attr = "{http://www.w3.org/XML/1998/namespace}lang"
        default = next((li for li in items if li.get(lang_attr) == "x-default"), items[0])
        return default.text or ""
    return None


def parse_xmp(xmp_bytes):
    """Returns a dict of the raw property strings (None = absent), or None if the
    packet cannot be parsed as XML."""
    try:
        root = ET.fromstring(xmp_bytes)
    except ET.ParseError as e:
        logging.warning(f"{_LOG_PREFIX} XMP could not be parsed: {e}")
        return None
    descriptions = list(_descriptions(root))
    props = {name: _find_prop(descriptions, NS_YCOMFY, name) for name in _YCOMFY_PROPS}
    props["dc_description"] = _find_dc_description(descriptions)
    props["CreatorTool"] = _find_prop(descriptions, NS_XMP, "CreatorTool")
    props["CreateDate"] = _find_prop(descriptions, NS_XMP, "CreateDate")
    return props


# ---------------------------------------------------------------------------
# helpers for reading values defensively (version > 1 may change types)
# ---------------------------------------------------------------------------

def _dict(value):
    return value if isinstance(value, dict) else {}


def _str(value):
    return value if isinstance(value, str) else None


def _int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _number(value):
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _seed_string(value):
    """Seeds are decimal strings in v1; tolerate an int, reject anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and _SEED_RE.match(value.strip()):
        return value.strip()
    return None


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _empty_info(status, warnings=None):
    return {
        "status": status,
        "schema_version": None,
        "positive": None,
        "negative": None,
        "seed": None,
        "seed_source": None,
        "sampler": None,
        "image": None,
        "models": None,
        "created_at": None,
        "note": None,
        "generator": None,
        "warnings": list(warnings or []),
    }


# ---------------------------------------------------------------------------
# 4.3 / 4.4 normalization
# ---------------------------------------------------------------------------

def _load_parameters(raw, warnings):
    """Returns (parameters_dict_or_None, version_or_None)."""
    if raw is None:
        return None, None
    try:
        params = json.loads(raw)
    except (ValueError, TypeError) as e:
        warnings.append(f"ycomfy:Parameters is not valid JSON ({e})")
        return None, None
    if not isinstance(params, dict):
        warnings.append("ycomfy:Parameters is not a JSON object")
        return None, None
    if params.get("schema") != SCHEMA_ID:
        warnings.append(f"ycomfy:Parameters has an unknown schema: {params.get('schema')!r}")
        return None, None
    version = _int(params.get("version"))
    if version is None or version < 1:
        warnings.append(f"ycomfy:Parameters has an invalid version: {params.get('version')!r}")
        return None, None
    return params, version


def _normalize_sampler(sampler):
    sampler = _dict(sampler)
    out = {}
    for key in _SAMPLER_INT:
        value = _int(sampler.get(key))
        if value is not None:
            out[key] = value
    for key in _SAMPLER_FLOAT:
        value = _float(sampler.get(key))
        if value is not None:
            out[key] = value
    for key in _SAMPLER_STR:
        value = _str(sampler.get(key))
        if value is not None:
            out[key] = value
    return out or None


def _normalize_image(image):
    image = _dict(image)
    out = {}
    for key in ("width", "height", "quality"):
        value = _int(image.get(key))
        if value is not None:
            out[key] = value
    if isinstance(image.get("lossless"), bool):
        out["lossless"] = image["lossless"]
    for key in ("filename", "subfolder"):
        value = _str(image.get(key))
        if value is not None:
            out[key] = value
    return out or None


def _normalize_models(models):
    if not isinstance(models, list):
        return None
    out = []
    for model in models:
        if not isinstance(model, dict):
            continue
        name = _str(model.get("name"))
        if not name:
            continue
        entry = {"kind": _str(model.get("kind")) or "other", "name": name}
        for key in _MODEL_STRENGTHS:
            value = _number(model.get(key))
            if value is not None:
                entry[key] = value
        out.append(entry)
    return out


def _generator_from_creator_tool(creator_tool):
    match = _CREATOR_RE.search(creator_tool or "")
    if not match:
        return None
    return {"node": match.group(1), "node_version": match.group(2), "comfyui_version": None}


def _is_ycomfy(props):
    if any(props.get(name) is not None for name in _YCOMFY_PROPS):
        return True
    return SAVE_NODE_CLASS in (props.get("CreatorTool") or "")


def normalize(xmp_bytes):
    """Returns (info, parameters_raw).

    `info` follows spec 4.4 (without `nodes`); `parameters_raw` is the
    ycomfy:Parameters text exactly as stored, or "" when absent.
    """
    if not xmp_bytes:
        return _empty_info(STATUS_NONE), ""
    props = parse_xmp(xmp_bytes)
    if props is None:
        return _empty_info(STATUS_NONE, ["XMP could not be parsed"]), ""

    parameters_raw = props.get("Parameters") or ""
    if not _is_ycomfy(props):
        return _empty_info(STATUS_NONE), parameters_raw

    warnings = []
    params, version = _load_parameters(props.get("Parameters"), warnings)
    if params is None:
        status = STATUS_PARTIAL
        params = {}
        sv = _seed_string(props.get("SchemaVersion"))  # a plain decimal string, like the seed
        schema_version = int(sv) if sv is not None else None
    elif version > SCHEMA_VERSION:
        status = STATUS_UNSUPPORTED
        schema_version = version
        warnings.append(f"unsupported schema version {version}; showing what can be read")
    else:
        status = STATUS_OK
        schema_version = version

    # Parameters first, the duplicated XMP properties only fill what is missing
    # (spec 5.3: Parameters wins when they disagree).
    prompt = _dict(params.get("prompt"))
    seed = _dict(params.get("seed"))
    info = _empty_info(status, warnings)
    info["schema_version"] = schema_version
    info["positive"] = _first_present(_str(prompt.get("positive")), props.get("PositivePrompt"),
                                      props.get("dc_description"))
    info["negative"] = _first_present(_str(prompt.get("negative")), props.get("NegativePrompt"))

    seed_value = _seed_string(seed.get("value"))
    if seed_value is None and props.get("Seed") is not None:
        seed_value = _seed_string(props["Seed"])
        if seed_value is None:
            warnings.append(f"ycomfy:Seed is not an integer: {props['Seed']!r}")
    info["seed"] = seed_value
    if seed_value is not None and (seed.get("node_id") is not None or seed.get("class_type") is not None):
        info["seed_source"] = {"node_id": _str(seed.get("node_id")), "class_type": _str(seed.get("class_type"))}

    info["sampler"] = _normalize_sampler(params.get("sampler"))
    info["image"] = _normalize_image(params.get("image"))
    info["models"] = _normalize_models(params.get("models"))
    info["created_at"] = _first_present(_str(params.get("created_at")), props.get("CreateDate"))
    info["note"] = _first_present(_str(params.get("note")), props.get("Note"))

    generator = _dict(params.get("generator"))
    if generator:
        info["generator"] = {
            "node": _str(generator.get("node")),
            "node_version": _str(generator.get("node_version")),
            "comfyui_version": _str(generator.get("comfyui_version")),
        }
    else:
        info["generator"] = _generator_from_creator_tool(props.get("CreatorTool"))
    return info, parameters_raw


def seed_to_int(seed):
    """INT output for the seed string; 0 (with a warning) when it cannot be converted."""
    if seed is None:
        return 0
    try:
        return int(seed)
    except (ValueError, TypeError):
        logging.warning(f"{_LOG_PREFIX} seed {seed!r} is not an integer; outputting 0")
        return 0
