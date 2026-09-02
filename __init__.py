"""
@author: Yoshiaki21
@title: yoshiaki-comfy
@nickname: yoshiaki-comfy
@description: Personal ComfyUI custom node pack.
"""

import logging
import os
import sys

modules_path = os.path.join(os.path.dirname(__file__), "modules")
sys.path.append(modules_path)

import yoshiaki_wildcard.config as config
logging.info(f"### Loading: yoshiaki-comfy ({config.version})")

try:
    import folder_paths  # noqa: F401
    import nodes  # noqa: F401
    import yaml  # noqa: F401
except Exception as e:
    logging.error("[yoshiaki-comfy] Failed to import due to missing dependencies (see requirements.txt).")
    raise e

import yoshiaki_wildcard.server  # noqa: F401  (registers server routes + on-prompt hook)

from yoshiaki_wildcard.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS  # noqa: E402

nodes.EXTENSION_WEB_DIRS["yoshiaki-comfy"] = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'js')

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
