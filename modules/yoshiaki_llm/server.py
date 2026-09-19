"""Server route for the LLM nodes' dynamic model-list refresh.

`INPUT_TYPES` (see llm_caption_node.py / llm_prompt_translator_node.py) is a
classmethod: ComfyUI evaluates it once per server start / browser reload
(`/object_info`), with no access to any particular node instance's current
widget values. It also only ever queries DEFAULT_LEMONADE_HOST /
DEFAULT_LEMONADE_PORT, never the node's own lemonade_host/lemonade_port
widgets. So changing those widgets on a node can never update its `model`
combo on its own -- the frontend (js/yoshiaki-llm.js) has to explicitly ask
this route to re-fetch against whatever host/port/api_key the user actually
typed in.

`vision_only` is sent by the caption node only (it requires an image input).
It is honoured per request rather than per route because both node classes
share this one endpoint.
"""

from aiohttp import web
from server import PromptServer

from . import llm_common


@PromptServer.instance.routes.post("/yoshiaki/llm/models")
async def yoshiaki_llm_models(request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    host = (payload.get("host") or llm_common.DEFAULT_LEMONADE_HOST).strip()
    try:
        port = int(payload.get("port") or llm_common.DEFAULT_LEMONADE_PORT)
    except (TypeError, ValueError):
        port = llm_common.DEFAULT_LEMONADE_PORT
    api_key = payload.get("api_key") or ""
    vision_only = bool(payload.get("vision_only"))

    models, ok = llm_common.resolve_model_list(host, port, api_key, vision_only=vision_only)

    # 取得できたときに何もログが出ないと、「Refresh Models を押しても動いていない」ようにしか
    # 見えない（失敗時しか llm_common 側の出力が出ないため）。押されたこと・結果・実際の接続先が
    # 後から追えるよう、成否によらず必ず1行残す（2026-09-19 追加）。
    scope = "画像対応モデルのみ" if vision_only else "全モデル"
    if ok:
        print(f"[yoshiaki-comfy LLM] モデル一覧を更新しました "
              f"(http://{host}:{port}, {scope}): {len(models)}件")
    else:
        print(f"[yoshiaki-comfy LLM] モデル一覧を更新できませんでした "
              f"(http://{host}:{port}, {scope}): {models[0]}")
    return web.json_response({"ok": ok, "models": models})
