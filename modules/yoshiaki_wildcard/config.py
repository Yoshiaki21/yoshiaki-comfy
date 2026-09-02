import configparser
import os

version = "V1.0.0"

my_path = os.path.dirname(__file__)
config_path = os.path.abspath(os.path.join(my_path, "..", "..", "yoshiaki-wildcard.ini"))
default_wildcards_path = os.path.abspath(os.path.join(my_path, "..", "..", "wildcards"))

_cached_config = None


def read_config():
    """
    Only setting: `custom_wildcards`, an optional override directory.

    When unset (or the path doesn't exist), the pack's own `wildcards/`
    folder is used. When set to an existing directory, that directory is
    searched INSTEAD of `wildcards/` (custom-only mode) -- same semantics
    as ComfyUI-Impact-Pack's `custom_wildcards` setting.
    """
    try:
        parser = configparser.ConfigParser()
        parser.read(config_path)
        section = parser["default"]

        raw_custom = section.get("custom_wildcards", "").strip("'\"")
        custom_is_set = bool(raw_custom) and os.path.isdir(raw_custom)

        return {
            "custom_wildcards": raw_custom if custom_is_set else default_wildcards_path,
            "custom_wildcards_is_set": custom_is_set,
        }
    except Exception:
        return {
            "custom_wildcards": default_wildcards_path,
            "custom_wildcards_is_set": False,
        }


def get_config():
    global _cached_config
    if _cached_config is None:
        _cached_config = read_config()
    return _cached_config


def reload_config():
    """Re-read yoshiaki-wildcard.ini from disk (used by the /refresh route)."""
    global _cached_config
    _cached_config = None
    return get_config()
