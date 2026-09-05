"""
Server route for the LLM caption node's dynamic model-list refresh.

`INPUT_TYPES` (see llm_caption_node.py) is a classmethod: ComfyUI evaluates
it once per server start / browser reload (`/object_info`), with no access
to any particular node instance's current widget values. It also only ever
queries DEFAULT_LEMONADE_HOST/DEFAULT_LEMONADE_PORT, never the node's own
lemonade_host/lemonade_port widgets. So changing those widgets on a node
can never update its `model` combo on its own -- the frontend
(js/yoshiaki-llm.js) has to explicitly ask this route to re-fetch against
whatever host/port/api_key the user actually typed in.
"""

from aiohttp import web
from server import PromptServer

from . import llm_caption_node


@PromptServer.instance.routes.post("/yoshiaki/llm/models")
async def yoshiaki_llm_models(request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    host = (payload.get("host") or llm_caption_node.DEFAULT_LEMONADE_HOST).strip()
    try:
        port = int(payload.get("port") or llm_caption_node.DEFAULT_LEMONADE_PORT)
    except (TypeError, ValueError):
        port = llm_caption_node.DEFAULT_LEMONADE_PORT
    api_key = payload.get("api_key") or ""

    models = llm_caption_node.fetch_lemonade_models(host, port, api_key)
    if not models:
        return web.json_response({"ok": False, "models": [llm_caption_node.FALLBACK_MODEL_LABEL]})
    return web.json_response({"ok": True, "models": models})
