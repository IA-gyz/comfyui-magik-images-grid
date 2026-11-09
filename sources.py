"""Expand IMAGE batches/list inputs; stable identity is socket number + batch position."""
from __future__ import annotations
import base64
import hashlib
import io
import re
import numpy as np
from PIL import Image

MAX_SOURCES = 4096
THUMBNAIL_LIMIT = 256
THUMBNAIL_EDGE = 128


def first(value, default=None):
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return default if value is None else value


def _arrays(value):
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            yield from _arrays(v)
        return
    if hasattr(value, "detach"):
        value = value.detach().cpu().float().numpy()
    a = np.asarray(value)
    if a.ndim == 4:
        for image in a:
            yield image
    elif a.ndim == 3:
        yield a
    else:
        raise ValueError(f"Expected IMAGE [B,H,W,C] or [H,W,C], received {a.shape}.")


def _image(a):
    if min(a.shape[:2]) < 1 or a.shape[-1] not in (1, 3, 4):
        raise ValueError(f"Invalid image shape {a.shape}; channels must be 1, 3 or 4.")
    if a.dtype == np.uint8:
        a = a.astype(np.float32) / 255
    elif np.issubdtype(a.dtype, np.floating):
        a = a.astype(np.float32, copy=False)
    else:
        raise ValueError(f"Unsupported image dtype {a.dtype}; use float [0,1] or uint8.")
    if not np.isfinite(a).all():
        raise ValueError("Input image contains NaN or infinity.")
    if np.any(a < 0) or np.any(a > 1):
        a = np.clip(a, 0, 1)
    if a.shape[-1] == 1:
        a = np.repeat(a, 3, axis=-1)
    return np.ascontiguousarray(a)


def expand_sources(inputs):
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise ValueError("Autogrow images must be a dictionary of socket values.")
    inventory, images = [], {}
    def slot_number(name):
        match = re.fullmatch(r"image_(\d+)", str(name))
        if not match:
            raise ValueError(f"Unrecognized image socket {name!r}.")
        return int(match.group(1))
    for socket in sorted(inputs, key=slot_number):
        position = 0
        for a in _arrays(inputs[socket]):
            if len(inventory) >= MAX_SOURCES:
                raise ValueError(f"At most {MAX_SOURCES} source images can be composed in one run.")
            a = _image(a)
            sid = f"in{slot_number(socket) + 1}:{position}"
            h, w = a.shape[:2]
            digest = hashlib.blake2b(memoryview(a).cast("B"), digest_size=12).hexdigest()
            entry = {"id": sid, "socket": socket, "index": position, "w": w, "h": h,
                     "hash": digest, "label": f"Input {slot_number(socket)+1} · image {position+1}"}
            inventory.append(entry)
            images[sid] = a
            position += 1
    return inventory, images


def diff_inventory(previous, current):
    old = {s["id"]: s for s in previous}
    new = {s["id"]: s for s in current}
    return {"added": [s for s in new if s not in old],
            "removed": [s for s in old if s not in new],
            "changed": [s for s in new if s in old and
                        any(new[s].get(k) != old[s].get(k) for k in ("w", "h", "hash"))]}


def thumbnails(images):
    """Bound websocket size; thumbnails are ephemeral, never stored in layout JSON."""
    result = {}
    for sid, a in list(images.items())[:THUMBNAIL_LIMIT]:
        stride = max(1, int(np.ceil(max(a.shape[:2]) / (THUMBNAIL_EDGE * 2))))
        preview = a[::stride, ::stride]
        im = Image.fromarray(np.rint(preview * 255).astype(np.uint8))
        im.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        im.save(buffer, format="PNG")
        result[sid] = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    return result
