"""
Read the XMP packet of a JPEG XL file by walking its ISOBMFF boxes
(spec: docs/yoshiaki/JXL_Load_Node_指示書.md 4.1).

`pillow_jxl.Decoder()` also returns the boxes, but it decodes the whole image.
This walks the box headers and `seek`s over the image data (`jxlc` / `jxlp`),
so only the XMP payload is ever read into memory.

No ComfyUI / pillow imports here so the logic can be tested on its own.
"""

import logging
import os
import struct

CONTAINER_SIGNATURE = b"\x00\x00\x00\x0cJXL \r\n\x87\n"
CODESTREAM_SIGNATURE = b"\xff\x0a"

# An XMP packet larger than this is not something YoshiakiSaveImageJXL writes;
# refuse it instead of reading an arbitrary amount of a broken file into memory.
MAX_XMP_BYTES = 64 * 1024 * 1024

_LOG_PREFIX = "[YoshiakiLoadImageJXL]"


def iter_boxes(f, file_size):
    """Yields (box_type, payload_offset, payload_size) for every box of a container.

    Stops (without raising) at the first header that is truncated, smaller than
    its own header, or that runs past the end of the file.
    """
    pos = 0
    while pos + 8 <= file_size:
        f.seek(pos)
        header = f.read(8)
        if len(header) < 8:
            return
        size, box_type = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            large = f.read(8)
            if len(large) < 8:
                return
            size = struct.unpack(">Q", large)[0]
            header_len = 16
        elif size == 0:
            size = file_size - pos
        if size < header_len or pos + size > file_size:
            return
        yield box_type, pos + header_len, size - header_len
        pos += size


def _brotli_decompress(data):
    try:
        import brotli
    except ImportError:
        logging.warning(f"{_LOG_PREFIX} found a compressed XMP box (brob) but the 'brotli' package "
                        "is not installed; skipping it")
        return None
    try:
        return brotli.decompress(data)
    except Exception as e:
        logging.warning(f"{_LOG_PREFIX} failed to decompress brob XMP box: {e}")
        return None


def read_xmp_from_file(f, file_size):
    """XMP bytes of an open binary file, or None when there is none."""
    f.seek(0)
    head = f.read(len(CONTAINER_SIGNATURE))
    if head[:2] == CODESTREAM_SIGNATURE:
        return None  # bare codestream: no boxes, no XMP
    if head != CONTAINER_SIGNATURE:
        return None  # not a JPEG XL container

    brob_candidate = None
    for box_type, offset, size in iter_boxes(f, file_size):
        if box_type == b"xml ":
            if size > MAX_XMP_BYTES:
                logging.warning(f"{_LOG_PREFIX} XMP box is too large ({size} bytes); ignored")
                return None
            f.seek(offset)
            return f.read(size)
        if box_type == b"brob" and brob_candidate is None and 4 <= size <= MAX_XMP_BYTES:
            f.seek(offset)
            if f.read(4) == b"xml ":
                brob_candidate = (offset + 4, size - 4)

    # Only use a compressed XMP box when there is no plain one anywhere.
    if brob_candidate is not None:
        offset, size = brob_candidate
        f.seek(offset)
        return _brotli_decompress(f.read(size))
    return None


def read_xmp(path):
    """XMP bytes of the JPEG XL file at `path`, or None when there is none."""
    with open(path, "rb") as f:
        return read_xmp_from_file(f, os.fstat(f.fileno()).st_size)
