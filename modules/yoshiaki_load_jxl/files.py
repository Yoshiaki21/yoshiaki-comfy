"""
The image file list (.jxl / .png / .jpg / .jpeg) of the ComfyUI input folder and the path check shared by the
node and the server routes (spec 2.1 / 3.2).
"""

import os

import folder_paths

JXL_EXT = ".jxl"
# JXL carries the XMP metadata; PNG/JPEG are loaded as images only (2026-11-28).
IMAGE_EXTS = (JXL_EXT, ".png", ".jpg", ".jpeg")


class InvalidPathError(ValueError):
    """The name points outside the input folder (or is not a relative path)."""


def input_dir():
    return os.path.realpath(folder_paths.get_input_directory())


def is_supported(name):
    return isinstance(name, str) and name.lower().endswith(IMAGE_EXTS)


def is_jxl(name):
    return isinstance(name, str) and name.lower().endswith(JXL_EXT)


def list_image_files():
    """Relative paths ('/' separated) of every supported image under the input folder, sorted by name."""
    root = input_dir()
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        for name in filenames:
            if not is_supported(name):
                continue
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            files.append(rel.replace(os.sep, "/"))
    return sorted(files)


def resolve(name):
    """Absolute path of `name` inside the input folder.

    Raises InvalidPathError for absolute paths, drive letters, `..` components or
    anything that resolves (symlinks included) outside the input folder.
    Existence is not checked.
    """
    if not isinstance(name, str) or not name or "\x00" in name:
        raise InvalidPathError("empty or invalid file name")
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or os.path.isabs(name) or os.path.splitdrive(name)[0] \
            or (len(normalized) >= 2 and normalized[1] == ":"):
        raise InvalidPathError(f"absolute paths are not allowed: {name}")
    if any(part == ".." for part in normalized.split("/")):
        raise InvalidPathError(f"'..' is not allowed: {name}")

    root = input_dir()
    path = os.path.realpath(os.path.join(root, *[p for p in normalized.split("/") if p]))
    try:
        inside = os.path.commonpath([root, path]) == root
    except ValueError:  # different drives on Windows
        inside = False
    if not inside or path == root:
        raise InvalidPathError(f"path is outside the input folder: {name}")
    return path


def stat_key(path):
    """Cache key that changes when the file is replaced or rewritten."""
    st = os.stat(path)
    return (path, st.st_mtime_ns, st.st_size)
