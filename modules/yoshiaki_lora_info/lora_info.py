"""
Trimmed, independent re-implementation of rgthree-comfy's LoRA "info"
feature (https://github.com/rgthree/rgthree-comfy, MIT licensed) for the
"Select to add LoRA" combo on YoshiakiWildcardEncode.

This is NOT a port of rgthree's code -- written fresh, covering only what's
needed here: local .safetensors embedded metadata + a Civitai lookup by
SHA256 hash, both cached. Deliberately excludes rgthree's editable notes,
custom video playback UI, dev-mode menu, and bulk model-management routes
(list/clear/save-by-post). Does not read or write any of rgthree-comfy's
own cache files (its `<lora>.rgthree-info.json` sidecar files, or its
private userdata directory) -- this keeps its own cache entirely inside
modules/yoshiaki_lora_info/cache/ (git-ignored), keyed by file hash, so a
real rgthree-comfy install (if also present) is completely unaffected.
"""

import hashlib
import json
import logging
import os

import aiohttp
import folder_paths
from aiohttp import web
from server import PromptServer

CIVITAI_API_BASE = "https://civitai.com/api/v1/model-versions/by-hash"


def _cache_dir():
    d = os.path.join(os.path.dirname(os.path.realpath(__file__)), "cache")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_path(file_hash, kind):
    return os.path.join(_cache_dir(), f"{file_hash}.{kind}.json")


def _read_cache(file_hash, kind):
    path = _cache_path(file_hash, kind)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(file_hash, kind, data):
    try:
        with open(_cache_path(file_hash, kind), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        logging.warning(f"[yoshiaki-comfy] lora_info: failed to write cache for {file_hash}.{kind}: {e}")


def sha256_of_file(path):
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 128), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def read_safetensors_metadata(path):
    """Reads the __metadata__ block from a .safetensors file header (no external deps)."""
    if not path.endswith(".safetensors"):
        return None
    try:
        with open(path, "rb") as f:
            header_size = int.from_bytes(f.read(8), "little", signed=False)
            if header_size <= 0:
                return None
            header = json.loads(f.read(header_size))
        metadata = header.get("__metadata__")
        if not metadata:
            return None
        # ss_tag_frequency and similar fields are themselves JSON encoded as strings.
        for key, value in metadata.items():
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                try:
                    metadata[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
        return metadata
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        logging.warning(f"[yoshiaki-comfy] lora_info: failed to read metadata from {path}: {e}")
        return None


def _trained_words_from_metadata(metadata):
    words = {}
    freq = metadata.get("ss_tag_frequency") if metadata else None
    if isinstance(freq, dict):
        for bucket in freq.values():
            if isinstance(bucket, dict):
                for tag, count in bucket.items():
                    entry = words.setdefault(tag, {"word": tag, "count": 0, "source": "metadata"})
                    try:
                        entry["count"] += int(count)
                    except (TypeError, ValueError):
                        pass
    return words


def _trained_words_from_civitai(civitai_data):
    words = {}
    raw = (civitai_data or {}).get("trainedWords") or []
    # Civitai entries are sometimes a single word, sometimes a comma-joined phrase.
    joined = ",".join(w for w in raw if isinstance(w, str))
    for token in joined.split(","):
        token = token.strip()
        if token:
            words.setdefault(token, {"word": token, "count": None, "source": "civitai"})
    return words


async def _fetch_civitai(file_hash):
    url = f"{CIVITAI_API_BASE}/{file_hash}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 404:
                    return {"error": "Model not found on Civitai"}
                if response.status != 200:
                    return {"error": f"Civitai returned HTTP {response.status}"}
                return await response.json()
    except Exception as e:
        logging.warning(f"[yoshiaki-comfy] lora_info: civitai lookup failed for {file_hash}: {e}")
        return {"error": str(e)}


def _resolve_lora_path(file):
    path = folder_paths.get_full_path("loras", file)
    if path is None or not os.path.isfile(path):
        return None
    return path


def _build_info(file, file_hash, metadata, civitai):
    info = {"file": file, "sha256": file_hash, "hasCivitaiData": False}

    if civitai and "error" not in civitai:
        info["hasCivitaiData"] = True
        model = civitai.get("model") or {}
        info["name"] = model.get("name") or civitai.get("name")
        info["type"] = model.get("type")
        info["baseModel"] = civitai.get("baseModel")
        model_id = civitai.get("modelId")
        if model_id:
            link = f"https://civitai.com/models/{model_id}"
            version_id = civitai.get("id")
            if version_id:
                link += f"?modelVersionId={version_id}"
            info["civitaiLink"] = link
        images = []
        for img in (civitai.get("images") or []):
            if not img.get("url"):
                continue
            meta = img.get("meta") or {}
            images.append({
                "url": img.get("url"),
                "type": img.get("type") or "image",
                "seed": meta.get("seed"),
                "steps": meta.get("steps"),
                "cfg": meta.get("cfgScale"),
                "sampler": meta.get("sampler"),
                "model": meta.get("Model") or meta.get("model"),
                "positive": meta.get("prompt"),
                "negative": meta.get("negativePrompt"),
            })
        info["images"] = images
    elif civitai and "error" in civitai:
        info["civitaiError"] = civitai["error"]

    words = _trained_words_from_metadata(metadata)
    for word, data in _trained_words_from_civitai(civitai).items():
        if word in words:
            words[word]["source"] = "both"
        else:
            words[word] = data
    info["trainedWords"] = sorted(
        words.values(), key=lambda w: (w["count"] is None, -(w["count"] or 0))
    )

    return info


async def get_or_refresh_lora_info(file, refresh=False):
    path = _resolve_lora_path(file)
    if path is None:
        return {"error": f"LoRA file not found: {file}"}

    file_hash = sha256_of_file(path)

    metadata = _read_cache(file_hash, "metadata")
    if metadata is None:
        metadata = read_safetensors_metadata(path) or {}
        _write_cache(file_hash, "metadata", metadata)

    civitai = None if refresh else _read_cache(file_hash, "civitai")
    if civitai is None and refresh:
        civitai = await _fetch_civitai(file_hash)
        _write_cache(file_hash, "civitai", civitai)

    return _build_info(file, file_hash, metadata, civitai)


routes = PromptServer.instance.routes


@routes.get("/yoshiaki/lora_info")
async def yoshiaki_lora_info(request):
    file = request.query.get("file")
    if not file:
        return web.json_response({"error": "missing 'file' query param"}, status=400)
    info = await get_or_refresh_lora_info(file, refresh=False)
    return web.json_response(info)


@routes.get("/yoshiaki/lora_info/refresh")
async def yoshiaki_lora_info_refresh(request):
    file = request.query.get("file")
    if not file:
        return web.json_response({"error": "missing 'file' query param"}, status=400)
    info = await get_or_refresh_lora_info(file, refresh=True)
    return web.json_response(info)
