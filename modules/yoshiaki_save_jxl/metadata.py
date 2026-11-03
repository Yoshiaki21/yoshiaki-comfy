"""
Parameter collection (spec ch.6) and XMP packet generation (spec ch.5, v1 = fixed)
for YoshiakiSaveImageJXL.

The XMP layout and the `ycomfy:Parameters` JSON schema are consumed by a future
loader node. Do not change them; follow spec 5.5 (adding keys is compatible and
keeps version 1, anything else bumps `version` to 2).

No ComfyUI imports here so the logic can be tested without a running ComfyUI.
"""

import hashlib
import json
import re
from collections import deque
import xml.etree.ElementTree as ET

NODE_CLASS = "YoshiakiSaveImageJXL"
SCHEMA_ID = "yoshiaki-comfy/jxl-params"
SCHEMA_VERSION = 1

NS_X = "adobe:ns:meta/"
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XMP = "http://ns.adobe.com/xap/1.0/"
NS_YCOMFY = "https://github.com/Yoshiaki21/yoshiaki-comfy/ns/1.0/"
NS_XML = "http://www.w3.org/XML/1998/namespace"

_NAMESPACES = {"x": NS_X, "rdf": NS_RDF, "dc": NS_DC, "xmp": NS_XMP, "ycomfy": NS_YCOMFY}
for _prefix, _uri in _NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)

XPACKET_BEGIN = '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
XPACKET_END = '<?xpacket end="w"?>'

MAX_STRING_LEN = 16384
SEED_WIDGETS = ("seed", "noise_seed")
PROMPT_TEXT_WIDGETS = ("populated_text", "text", "prompt")
SAMPLER_FIELDS = ("steps", "cfg", "sampler_name", "scheduler", "denoise")
STRENGTH_WIDGETS = ("strength_model", "strength_clip", "strength")
MODEL_FILE_EXTS = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".sft")
_CLIP_NAME_RE = re.compile(r"^clip_name\d*$")
# Characters that are not allowed in XML 1.0 (would make the packet unparsable).
_XML_INVALID_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


# ---------------------------------------------------------------------------
# prompt graph helpers
# ---------------------------------------------------------------------------

def is_link(value):
    """A link in the API-format prompt is `["node_id", output_index]`."""
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


def node_id_sort_key(node_id):
    """Compare node ids as numbers ("3" < "12"); subgraph ids look like "12:5"."""
    parts = []
    for part in str(node_id).split(":"):
        parts.append((0, int(part), "") if part.isdecimal() else (1, 0, part))
    return tuple(parts)


def _inputs(prompt, node_id):
    node = prompt.get(node_id)
    if not isinstance(node, dict):
        return {}
    inputs = node.get("inputs")
    return inputs if isinstance(inputs, dict) else {}


def _class_type(prompt, node_id):
    node = prompt.get(node_id)
    return node.get("class_type", "") if isinstance(node, dict) else ""


def bfs_upstream(prompt, start_links=None, start_nodes=None):
    """Breadth-first walk upstream. Yields (node_id, distance).

    `start_links` are link values (distance 1 = the node the link points to);
    `start_nodes` are node ids visited at distance 0.
    """
    queue = deque()
    seen = set()
    for nid in start_nodes or ():
        if nid in prompt and nid not in seen:
            seen.add(nid)
            queue.append((nid, 0))
    for link in start_links or ():
        if is_link(link) and link[0] in prompt and link[0] not in seen:
            seen.add(link[0])
            queue.append((link[0], 1))
    while queue:
        nid, dist = queue.popleft()
        yield nid, dist
        for value in _inputs(prompt, nid).values():
            if is_link(value) and value[0] in prompt and value[0] not in seen:
                seen.add(value[0])
                queue.append((value[0], dist + 1))


# ---------------------------------------------------------------------------
# 6.1 nodes
# ---------------------------------------------------------------------------

def _record_value(value):
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return str(value)  # NaN/Infinity are not valid JSON
    if isinstance(value, str) and len(value) > MAX_STRING_LEN:
        return {
            "_truncated": True,
            "length": len(value),
            "sha256": hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest(),
        }
    return value


def collect_nodes(prompt):
    nodes = {}
    for node_id, node in (prompt or {}).items():
        if not isinstance(node, dict):
            continue
        meta = node.get("_meta")
        title = meta.get("title") if isinstance(meta, dict) else None
        inputs = {}
        for name, value in (node.get("inputs") or {}).items():
            # bool is a subclass of int; both are allowed. Lists (links) and dicts are dropped.
            if isinstance(value, (int, float, str)):
                inputs[name] = _record_value(value)
        nodes[str(node_id)] = {
            "class_type": node.get("class_type", ""),
            "title": title,
            "inputs": inputs,
        }
    return nodes


# ---------------------------------------------------------------------------
# 6.2 seed / primary sampler
# ---------------------------------------------------------------------------

def _resolve_int(prompt, value, depth=0):
    """Seed widget value, following a link to a primitive/int node if needed."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if is_link(value) and depth < 4:
        inputs = _inputs(prompt, value[0])
        for key in ("seed", "noise_seed", "value", "int", "number"):
            if key in inputs:
                resolved = _resolve_int(prompt, inputs[key], depth + 1)
                if resolved is not None:
                    return resolved
    return None


def find_seed_candidates(prompt, start_links=None, start_nodes=None):
    candidates = []
    for nid, dist in bfs_upstream(prompt, start_links, start_nodes):
        inputs = _inputs(prompt, nid)
        for widget in SEED_WIDGETS:
            if widget in inputs:
                value = _resolve_int(prompt, inputs[widget])
                if value is None:
                    continue
                candidates.append({
                    "node_id": str(nid),
                    "class_type": _class_type(prompt, nid),
                    "widget": widget,
                    "value": str(value),
                    "distance": dist,
                })
                break
    return candidates


def choose_primary_seed(candidates):
    if not candidates:
        return None

    def key(c):
        return (c["distance"], node_id_sort_key(c["node_id"]))

    preferred = [c for c in candidates
                 if "sampler" in c["class_type"].lower() or "noise" in c["class_type"].lower()]
    return min(preferred or candidates, key=key)


def find_sampler_node(prompt, start_links=None, start_nodes=None):
    best = None
    for nid, dist in bfs_upstream(prompt, start_links, start_nodes):
        if "Sampler" in _class_type(prompt, nid):
            k = (dist, node_id_sort_key(nid))
            if best is None or k < best[0]:
                best = (k, nid)
            elif dist > best[0][0]:
                break
    return best[1] if best else None


def build_sampler_info(prompt, sampler_id):
    if sampler_id is None:
        return None
    info = {"node_id": str(sampler_id), "class_type": _class_type(prompt, sampler_id)}
    inputs = _inputs(prompt, sampler_id)
    for field in SAMPLER_FIELDS:
        value = inputs.get(field)
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            info[field] = value
    return info


def resolve_seed_and_sampler(prompt, unique_id, primary_node=""):
    """Returns (seed_dict_or_None, sampler_node_id_or_None)."""
    image_links = [_inputs(prompt, str(unique_id)).get("images")] if unique_id is not None else []
    candidates = find_seed_candidates(prompt, start_links=image_links)

    primary_node = (primary_node or "").strip()
    if primary_node and primary_node not in prompt:
        print(f"[YoshiakiSaveImageJXL] primary_node '{primary_node}' not found in prompt; using auto detection")
        primary_node = ""

    if primary_node:
        sampler_id = primary_node
        # the primary node's own seed first, then whatever feeds it (e.g. RandomNoise)
        chosen = choose_primary_seed(find_seed_candidates(prompt, start_nodes=[primary_node]))
        if chosen is not None:
            match = next((c for c in candidates if c["node_id"] == chosen["node_id"]
                          and c["widget"] == chosen["widget"]), None)
            chosen = dict(chosen, distance=match["distance"] if match else None)
    else:
        sampler_id = find_sampler_node(prompt, start_links=image_links)
        chosen = choose_primary_seed(candidates)

    if chosen is None:
        return None, sampler_id

    seed = {
        "value": chosen["value"],
        "node_id": chosen["node_id"],
        "class_type": chosen["class_type"],
        "widget": chosen["widget"],
        "distance": chosen["distance"],
        "candidates": candidates,
    }
    return seed, sampler_id


# ---------------------------------------------------------------------------
# 6.3 prompts
# ---------------------------------------------------------------------------

def _find_conditioning_link(prompt, sampler_id, name):
    """The `positive`/`negative` link of the sampler, or of the first node upstream
    of it that has one (e.g. CFGGuider in a SamplerCustomAdvanced graph)."""
    for nid, _ in bfs_upstream(prompt, start_nodes=[sampler_id]):
        value = _inputs(prompt, nid).get(name)
        if is_link(value):
            return value
    return None


def auto_prompt_text(prompt, sampler_id, name):
    """Returns (text, source) for name in ("positive", "negative")."""
    if sampler_id is None or sampler_id not in prompt:
        return "", "none"
    link = _find_conditioning_link(prompt, sampler_id, name)
    if link is None:
        return "", "none"
    for nid, _ in bfs_upstream(prompt, start_links=[link]):
        inputs = _inputs(prompt, nid)
        for widget in PROMPT_TEXT_WIDGETS:
            if widget in inputs:
                value = inputs[widget]
                if isinstance(value, str):
                    return value, "auto"
                if is_link(value):
                    return "", "unresolved"
    return "", "none"


def pick_for_batch(values, index):
    """Element for this batch index; the last element if the list is too short."""
    if values is None:
        return None
    if not isinstance(values, (list, tuple)):
        return values
    if not values:
        return None
    return values[index] if index < len(values) else values[-1]


# ---------------------------------------------------------------------------
# 6.4 models
# ---------------------------------------------------------------------------

def _model_kind(widget, value):
    if widget == "ckpt_name":
        return "checkpoint"
    if widget == "unet_name":
        return "unet"
    if _CLIP_NAME_RE.match(widget):
        return "clip"
    if widget == "vae_name":
        return "vae"
    if widget == "lora_name":
        return "lora"
    if widget.endswith("_name") and value.lower().endswith(MODEL_FILE_EXTS):
        return "other"
    return None


def extract_models(nodes):
    models = []
    for node_id in sorted(nodes, key=node_id_sort_key):
        node = nodes[node_id]
        inputs = node["inputs"]
        strengths = {k: inputs[k] for k in STRENGTH_WIDGETS
                     if isinstance(inputs.get(k), (int, float)) and not isinstance(inputs.get(k), bool)}
        for widget, value in inputs.items():
            if not isinstance(value, str) or not value:
                continue
            kind = _model_kind(widget, value)
            if kind is None:
                continue
            entry = {"node_id": node_id, "class_type": node["class_type"], "kind": kind, "name": value}
            entry.update(strengths)
            models.append(entry)
    return models


# ---------------------------------------------------------------------------
# 5.4 Parameters JSON / 5.2 XMP packet
# ---------------------------------------------------------------------------

def build_parameters(*, node_version, comfyui_version, created_at, image, prompt_info,
                     seed, sampler, models, note, nodes):
    return {
        "schema": SCHEMA_ID,
        "version": SCHEMA_VERSION,
        "generator": {
            "node": NODE_CLASS,
            "node_version": node_version,
            "comfyui_version": comfyui_version,
        },
        "created_at": created_at,
        "image": image,
        "prompt": prompt_info,
        "seed": seed,
        "sampler": sampler,
        "models": models,
        "note": note,
        "nodes": nodes,
    }


def _xml_text(value):
    return _XML_INVALID_RE.sub("", str(value)).replace("\r\n", "\n").replace("\r", "\n")


def build_xmp(*, node_version, created_at, parameters, seed_value=None,
              positive="", negative="", note=""):
    """Returns the XMP packet as UTF-8 bytes."""
    root = ET.Element(f"{{{NS_X}}}xmpmeta")
    rdf = ET.SubElement(root, f"{{{NS_RDF}}}RDF")
    desc = ET.SubElement(rdf, f"{{{NS_RDF}}}Description", {f"{{{NS_RDF}}}about": ""})

    def prop(ns, name, text):
        el = ET.SubElement(desc, f"{{{ns}}}{name}")
        el.text = _xml_text(text)
        return el

    if positive:
        dc_desc = ET.SubElement(desc, f"{{{NS_DC}}}description")
        alt = ET.SubElement(dc_desc, f"{{{NS_RDF}}}Alt")
        li = ET.SubElement(alt, f"{{{NS_RDF}}}li", {f"{{{NS_XML}}}lang": "x-default"})
        li.text = _xml_text(positive)
    prop(NS_XMP, "CreatorTool", f"ComfyUI / yoshiaki-comfy {NODE_CLASS} {node_version}")
    prop(NS_XMP, "CreateDate", created_at)
    prop(NS_YCOMFY, "SchemaVersion", str(SCHEMA_VERSION))
    if seed_value is not None:
        prop(NS_YCOMFY, "Seed", str(seed_value))
    if positive:
        prop(NS_YCOMFY, "PositivePrompt", positive)
    if negative:
        prop(NS_YCOMFY, "NegativePrompt", negative)
    if note:
        prop(NS_YCOMFY, "Note", note)
    # json.dumps escapes every control character, so this is always valid XML text.
    prop(NS_YCOMFY, "Parameters", json.dumps(parameters, ensure_ascii=False, separators=(",", ":")))

    ET.indent(root, space=" ")
    body = ET.tostring(root, encoding="unicode")
    return f"{XPACKET_BEGIN}\n{body}\n{XPACKET_END}".encode("utf-8", "replace")
