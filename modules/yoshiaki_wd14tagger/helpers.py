"""
Trimmed replacement for ComfyUI-WD14-Tagger's pysssss.py: only what
wd14tagger.py actually needs (config loading, model download with
progress, running an async tagging call from a sync node FUNCTION).

Dropped entirely: the legacy web/extensions/pysssss symlink-install
machinery (install_js/link_js/is_junction/should_install_js/
get_web_ext_dir). yoshiaki-comfy already serves js/ via the modern
nodes.EXTENSION_WEB_DIRS mechanism (see __init__.py), so none of that
compatibility shim for old ComfyUI versions is needed.
"""

import asyncio
import concurrent.futures
import json
import os

import aiohttp
from server import PromptServer
from tqdm import tqdm


def get_ext_dir(subpath=None, mkdir=False):
    dir = os.path.dirname(os.path.realpath(__file__))
    if subpath is not None:
        dir = os.path.join(dir, subpath)
    dir = os.path.abspath(dir)
    if mkdir and not os.path.exists(dir):
        os.makedirs(dir)
    return dir


def load_config():
    """config.json, merged with config.user.json (git-ignored local override) if present."""
    with open(get_ext_dir("config.json"), "r", encoding="utf-8") as f:
        config = json.load(f)

    user_path = get_ext_dir("config.user.json")
    if os.path.exists(user_path):
        with open(user_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        config["settings"] = {**config.get("settings", {}), **user_config.get("settings", {})}
        config["models"] = {**config.get("models", {}), **user_config.get("models", {})}

    return config


async def download_to_file(url, destination, update_callback, session=None):
    close_session = False
    if session is None:
        close_session = True
        session = aiohttp.ClientSession()
    try:
        proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        proxy_auth = None
        if proxy:
            proxy_auth = aiohttp.BasicAuth(os.getenv("PROXY_USER", ""), os.getenv("PROXY_PASS", ""))

        async with session.get(url, proxy=proxy, proxy_auth=proxy_auth) as response:
            size = int(response.headers.get('content-length', 0)) or None

            with tqdm(unit='B', unit_scale=True, miniters=1, desc=url.split('/')[-1], total=size) as progressbar:
                with open(destination, mode='wb') as f:
                    last = 0
                    async for chunk in response.content.iter_chunked(2048):
                        f.write(chunk)
                        progressbar.update(len(chunk))
                        if update_callback is not None and progressbar.total:
                            perc = round(progressbar.n / progressbar.total, 2)
                            if perc != last:
                                last = perc
                                await update_callback(perc)
    finally:
        if close_session and session is not None:
            await session.close()


def wait_for_async(async_fn):
    try:
        # Check if we're in a running event loop
        asyncio.get_running_loop()
        # We're in a running loop, so run the async function in a separate thread
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, async_fn())
            return future.result()
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        return asyncio.run(async_fn())


def update_node_status(client_id, node, text, progress=None):
    if client_id is None:
        client_id = PromptServer.instance.client_id
    if client_id is None:
        return

    PromptServer.instance.send_sync("yoshiaki/wd14tagger/update_status", {
        "node": node,
        "progress": progress,
        "text": text,
    }, client_id)
