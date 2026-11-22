"""
YoshiakiResolutionLatent: Resolution Selector + Empty Latent Image in one node
(spec: docs/yoshiaki/ResolutionLatent_Node_指示書.md).
"""

import logging

import torch

import comfy.model_management
import nodes as comfy_nodes

from . import calc, presets

NODE_CLASS = "YoshiakiResolutionLatent"
NODE_DISPLAY_NAME = "Yoshiaki-ResolutionLatent"
LOG_PREFIX = presets.LOG_PREFIX
UI_KEY = "yoshiaki_resolution_latent"

SOURCE_VAE = "VAE"
SOURCE_PRESET = "プリセット"
SOURCE_GENERIC = "汎用"


def _intermediate_dtype():
    fn = getattr(comfy.model_management, "intermediate_dtype", None)
    return fn() if fn else torch.float32


def _vae_shape_info(vae):
    """(latent_channels, spatial downscale) of a connected VAE."""
    channels = int(vae.latent_channels)
    try:
        downscale = vae.spacial_compression_encode()
    except AttributeError:
        downscale = vae.downscale_ratio
    if isinstance(downscale, (tuple, list)):  # video VAE: (temporal fn, h, w)
        downscale = downscale[-1]
    return channels, int(downscale)


class YoshiakiResolutionLatent:
    @classmethod
    def INPUT_TYPES(cls):
        names = presets.names()
        ratios = presets.all_aspect_ratios()
        first = presets.PRESETS[names[0]]
        return {
            "required": {
                "model_preset": (names, {"default": names[0], "display_name": "モデル",
                                         "tooltip": "yoshiaki-resolution-latent.toml のモデル名"}),
                "aspect_ratio": (ratios, {"default": first["aspect_ratios"][0], "display_name": "アスペクト比",
                                          "tooltip": "選択モデルのアスペクト比。「カスタム」ならカスタム比率欄を使う"}),
                "custom_ratio": ("STRING", {"default": "2.39:1", "display_name": "カスタム比率",
                                            "tooltip": "「カスタム」選択時のみ使用。16:9 / 1.85 / 1152x896 など"}),
                "orientation": (calc.ORIENTATIONS, {"default": calc.ORIENT_LANDSCAPE, "display_name": "向き",
                                                    "tooltip": "長辺を幅（横長）にするか高さ（縦長）にするか"}),
                "megapixels": ("FLOAT", {"default": first["default_mp"], "min": 0.1, "max": 16.0, "step": 0.01,
                                         "display_name": "メガピクセル",
                                         "tooltip": "1.0MP = 1024x1024。固定解像度のときは無視"}),
                "multiple": ("INT", {"default": first["multiple"], "min": 1, "max": 256, "display_name": "倍数",
                                     "tooltip": "幅・高さの丸め単位"}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 4096, "display_name": "バッチサイズ"}),
            },
            "optional": {
                "vae": ("VAE", {"display_name": "VAE",
                                "tooltip": "接続すると潜在画像のチャンネル数・縮小率をVAEから決める"}),
            },
        }

    RETURN_TYPES = ("LATENT", "INT", "INT")
    RETURN_NAMES = ("潜在画像", "幅", "高さ")
    FUNCTION = "generate"
    CATEGORY = "yoshiaki-comfy/latent"
    DESCRIPTION = "モデル別プリセットのアスペクト比・メガピクセルから幅・高さを計算し、全ゼロの潜在画像を作る"

    # Declaring these two takes them out of ComfyUI's generic combo check
    # (execution.py: `if x not in validate_function_inputs and not validate_has_kwargs:`),
    # so a workflow saved with a model / ratio that was later removed from the
    # TOML still runs (with a warning, see generate). Do NOT add **kwargs: that
    # would also disable the min/max checks of every other input.
    @classmethod
    def VALIDATE_INPUTS(cls, model_preset, aspect_ratio):
        return True

    def generate(self, model_preset, aspect_ratio, custom_ratio, orientation, megapixels,
                 multiple, batch_size, vae=None):
        warnings = []

        preset = presets.PRESETS.get(model_preset)
        if preset is None:
            preset = presets.fallback()
            warnings.append(f"モデル '{model_preset}' がプリセットに無いため「{preset['name']}」として計算しました")

        if aspect_ratio == calc.CUSTOM_LABEL:
            spec = custom_ratio
        else:
            spec = aspect_ratio
            if aspect_ratio not in preset["aspect_ratios"]:
                warnings.append(f"アスペクト比 '{aspect_ratio}' は「{preset['name']}」のリストにありません（文字列をそのまま解析）")

        if vae is not None:
            channels, downscale = _vae_shape_info(vae)
            source = SOURCE_VAE
            if not preset["generic"] and (channels, downscale) != (preset["latent_channels"], preset["downscale"]):
                warnings.append(
                    f"VAE（{channels}ch・1/{downscale}）がプリセット「{preset['name']}」"
                    f"（{preset['latent_channels']}ch・1/{preset['downscale']}）と違います。"
                    f"モデル選択とVAEが合っていない可能性があります（VAEの値で生成）"
                )
        else:
            channels, downscale = preset["latent_channels"], preset["downscale"]
            source = SOURCE_GENERIC if preset["generic"] else SOURCE_PRESET

        req = calc.required_multiple(preset["multiple"], downscale, preset["generic"])
        try:
            res = calc.compute(spec, orientation, megapixels, multiple, req,
                               mp_range=preset["mp_range"], max_resolution=comfy_nodes.MAX_RESOLUTION)
        except calc.CalcError as e:
            raise ValueError(f"{LOG_PREFIX} {e}") from e
        warnings.extend(res["warnings"])
        width, height = res["width"], res["height"]

        shape = [batch_size, channels, height // downscale, width // downscale]
        latent = torch.zeros(shape, device=comfy.model_management.intermediate_device(),
                             dtype=_intermediate_dtype())

        for w in warnings:
            logging.warning(f"{LOG_PREFIX} {w}")

        info = {
            "width": width,
            "height": height,
            "mp": res["mp"],
            "shape": shape,
            "source": source,
            "preset": preset["name"],
            "multiple": res["multiple"],
            "warnings": warnings,
        }
        return {
            "ui": {UI_KEY: [info]},
            "result": ({"samples": latent, "downscale_ratio_spacial": downscale}, width, height),
        }


NODE_CLASS_MAPPINGS = {NODE_CLASS: YoshiakiResolutionLatent}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_CLASS: NODE_DISPLAY_NAME}
