"""Pure execution pipeline for Magik Image Grid (no comfy_api, no torch).

nodes.py is a thin V3 wrapper around run(); keeping the logic here makes it testable
without ComfyUI.

The payload is the "A" write-back contract: the backend is authoritative for syncing
(defaults, auto-added items, uids, orphan handling) and sends the result to the widget.
`received` is an FNV-1a 32-bit hash of the exact layout string the backend was given;
the frontend compares it with its current widget value to detect edits made while the
run was in flight (match -> replace wholesale, mismatch -> merge sources/new items only).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

if __package__:  # package import inside ComfyUI, flat import in standalone tests
    from .compositor import compose
    from .layout_engine import normalize_layout, resolve, sync_items
    from .sources import diff_inventory, expand_sources, first, thumbnails
else:  # standalone tests
    from compositor import compose
    from layout_engine import normalize_layout, resolve, sync_items
    from sources import diff_inventory, expand_sources, first, thumbnails

PAYLOAD_KEY = "magik_image_grid"
PAYLOAD_VERSION = 1


def fnv1a32(text: str) -> str:
    """FNV-1a 32-bit over UTF-8 bytes, as 8 hex chars.

    JS twin (TextEncoder bytes): h = 0x811c9dc5; per byte: h ^= b; h = Math.imul(h, 0x01000193) >>> 0
    """
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


@dataclass
class PipelineResult:
    canvas: np.ndarray  # float32 [H, W, 3]
    layout: dict        # synced, normalized layout (what the widget should hold)
    payload: dict       # JSON-safe ui payload


def run(images_input: Any, layout_value: Any) -> PipelineResult:
    """Run the whole node. Raises ValueError (including LayoutError) for invalid inputs or layouts."""
    raw = first(layout_value, "")
    warnings: list[str] = []
    if not isinstance(raw, str):
        warnings.append("Non-string layout value was ignored; default layout was used.")
        raw = ""

    layout, norm_warnings = normalize_layout(raw)
    warnings += norm_warnings

    inventory, images = expand_sources(images_input)
    if not inventory:
        warnings.append("No images are connected, or the connected inputs are empty.")

    diff = diff_inventory(layout["sources"], inventory)  # must precede sync (which rewrites sources)
    layout, sync_warnings = sync_items(layout, inventory)
    warnings += sync_warnings

    resolved = resolve(layout, inventory)
    warnings += resolved["warnings"]

    canvas, report = compose(
        resolved, images, layout["render"]["resample"], layout["render"]["maxPixels"]
    )

    payload = {
        "v": PAYLOAD_VERSION,
        "received": fnv1a32(raw),
        "layout": layout,
        "resolved": {"canvas": resolved["canvas"], "frames": resolved["frames"]},
        "inventory": inventory,
        "diff": diff,
        "missing": report["missing"],
        "upscaled": report["upscaled"],
        "warnings": warnings,
        "thumbnails": thumbnails(images),
    }
    return PipelineResult(canvas=canvas, layout=layout, payload=payload)
