"""
Server routes for YoshiakiLoadImageJXL (spec 3.2):

  GET /yoshiaki/jxl/list                  .jxl files of the input folder
  GET /yoshiaki/jxl/preview?filename=...  512px WebP preview (decoded on the server,
                                          so the browser does not need JPEG XL support)
  GET /yoshiaki/jxl/info?filename=...     normalized XMP metadata (spec 4.4), without
                                          decoding the image

Uploads use the standard POST /upload/image, which accepts .jxl as-is.
"""

import asyncio
import io
import logging
import os
import threading
from collections import OrderedDict

import numpy as np
from aiohttp import web
from PIL import Image

from server import PromptServer

from . import files
from .load_jxl import NODE_CLASS, frame_to_arrays, open_image, read_info

PREVIEW_MAX_SIDE = 512
PREVIEW_QUALITY = 85
_PREVIEW_CACHE_SIZE = 32
_INFO_CACHE_SIZE = 64

_LOG_PREFIX = f"[{NODE_CLASS}]"


class _LRU:
    def __init__(self, capacity):
        self._capacity = capacity
        self._data = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key, value):
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._capacity:
                self._data.popitem(last=False)


_preview_cache = _LRU(_PREVIEW_CACHE_SIZE)
_info_cache = _LRU(_INFO_CACHE_SIZE)


def _to_preview_image(img):
    """8-bit RGB (RGBA when there is alpha) built with the same conversion as the node."""
    rgb, alpha = frame_to_arrays(img)
    if alpha is not None:
        rgb = np.concatenate([rgb, alpha[..., None]], axis=-1)
    arr = (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(arr)  # HxWx3 -> RGB, HxWx4 -> RGBA


def build_preview(path):
    img = open_image(path)
    img = _to_preview_image(img)
    img.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=PREVIEW_QUALITY)
    return buf.getvalue()


def _resolve_request(request):
    """(path, cache key) or raises an HTTP error response."""
    name = request.rel_url.query.get("filename", "")
    try:
        path = files.resolve(name)
    except files.InvalidPathError as e:
        raise web.HTTPBadRequest(text=str(e))
    if not name.lower().endswith(files.JXL_EXT):
        raise web.HTTPBadRequest(text=f"not a .jxl file: {name}")
    if not os.path.isfile(path):
        raise web.HTTPNotFound(text=f"file not found: {name}")
    return path, files.stat_key(path)


_NO_STORE = {"Cache-Control": "no-store"}


@PromptServer.instance.routes.get("/yoshiaki/jxl/list")
async def jxl_list(request):
    file_list = await asyncio.to_thread(files.list_jxl_files)
    return web.json_response(file_list, headers=_NO_STORE)


@PromptServer.instance.routes.get("/yoshiaki/jxl/preview")
async def jxl_preview(request):
    path, key = _resolve_request(request)
    data = _preview_cache.get(key)
    if data is None:
        try:
            data = await asyncio.to_thread(build_preview, path)
        except Exception as e:
            logging.warning(f"{_LOG_PREFIX} preview failed for {path}: {e}")
            raise web.HTTPInternalServerError(text=f"preview failed: {e}")
        _preview_cache.put(key, data)
    return web.Response(body=data, content_type="image/webp", headers=_NO_STORE)


@PromptServer.instance.routes.get("/yoshiaki/jxl/info")
async def jxl_info(request):
    path, key = _resolve_request(request)
    info = _info_cache.get(key)
    if info is None:
        info, _ = await asyncio.to_thread(read_info, path)
        _info_cache.put(key, info)
    return web.json_response(info, headers=_NO_STORE)
