"""
Server route for YoshiakiResolutionLatent (spec ch.5):

  GET /yoshiaki/resolution_latent/presets   presets loaded at startup (file order)

The frontend uses it to swap the aspect-ratio list per model, fill in the
multiple / megapixels on model change, and compute the live preview.
"""

from aiohttp import web

from server import PromptServer

from . import calc, presets


@PromptServer.instance.routes.get("/yoshiaki/resolution_latent/presets")
async def get_presets(request):
    return web.json_response({
        "presets": list(presets.PRESETS.values()),
        "fallback": presets.fallback(),
        "custom_label": calc.CUSTOM_LABEL,
        "load_warnings": presets.LOAD_WARNINGS,
    })
