"""Validated schema v1 and deterministic layout geometry (no ComfyUI dependency)."""
from __future__ import annotations
import copy
import json
import math
import uuid

MAX_PIXELS = 64_000_000
MAX_DIMENSION = 32768
MAX_ITEMS = 8192
MAX_LAYOUT_BYTES = 8_000_000

class LayoutError(ValueError):
    pass


def defaults():
    return {"v": 1, "mode": "uniform", "canvas": {"w": 1500, "h": 1000,
            "heightMode": "fixed", "background": "#20242c"},
            "grid": {"columns": 3, "gap": 16, "padding": 24, "rowHeight": 240},
            "orphans": "placeholder", "render": {"resample": "lanczos", "maxPixels": MAX_PIXELS},
            "sources": [], "items": []}


def number(v, name, low, high, integer=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise LayoutError(f"{name} must be a finite number.")
    if v < low or v > high:
        raise LayoutError(f"{name} must be between {low} and {high}.")
    return int(round(v)) if integer else float(v)


def choice(v, name, choices):
    if v not in choices:
        raise LayoutError(f"{name} must be one of {', '.join(choices)}.")
    return v


def normalize_layout(raw):
    warnings = []
    data = {}
    if raw:
        if isinstance(raw, str):
            if len(raw.encode('utf-8')) > MAX_LAYOUT_BYTES:
                raise LayoutError("Layout JSON exceeds 8 MB.")
            try:
                data = json.loads(raw)
            except (ValueError, RecursionError):
                warnings.append("The layout JSON is malformed; default layout was used.")
                data = {}
        elif isinstance(raw, dict):
            data = copy.deepcopy(raw)
        else:
            raise LayoutError("Layout must be JSON text or a dictionary.")
    if not isinstance(data, dict):
        raise LayoutError("Layout JSON must contain an object.")
    if data.get("v", 1) != 1:
        raise LayoutError("Unsupported layout version; expected v=1.")
    d = defaults()
    d["mode"] = choice(data.get("mode", d["mode"]), "Mode", ("uniform", "packed", "custom"))
    d["orphans"] = choice(data.get("orphans", d["orphans"]), "Missing source policy", ("placeholder", "drop", "error"))
    for key in ("canvas", "grid", "render"):
        section = data.get(key, {})
        if not isinstance(section, dict):
            raise LayoutError(f"{key} must be an object.")
        d[key].update({k: v for k, v in section.items() if k in d[key]})
    c, g, r = d["canvas"], d["grid"], d["render"]
    for k in ("w", "h"):
        c[k] = number(c[k], f"Canvas {k}", 1, MAX_DIMENSION, True)
    choice(c["heightMode"], "Height mode", ("fixed", "auto"))
    bg = c["background"]
    if not isinstance(bg, str) or len(bg) != 7 or bg[0] != '#' or any(x not in '0123456789abcdefABCDEF' for x in bg[1:]):
        raise LayoutError("Background must be a #RRGGBB color.")
    for k in ("gap", "padding"):
        g[k] = number(g[k], k, 0, MAX_DIMENSION, True)
    g["columns"] = number(g["columns"], "Columns", 1, 100, True)
    g["rowHeight"] = number(g["rowHeight"], "Packed row height", 1, MAX_DIMENSION, True)
    choice(r["resample"], "Resampling", ("nearest", "bilinear", "bicubic", "lanczos"))
    r["maxPixels"] = number(r["maxPixels"], "Pixel limit", 1, MAX_PIXELS, True)
    sources = data.get("sources", [])
    if not isinstance(sources, list) or len(sources) > MAX_ITEMS:
        raise LayoutError("Invalid source inventory.")
    d["sources"] = []
    seen = set()
    for s in sources:
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or s['id'] in seen:
            raise LayoutError("Source entries require unique string ids.")
        seen.add(s['id'])
        d["sources"].append({k: s[k] for k in ("id", "socket", "index", "w", "h", "hash", "label") if k in s})
    items = data.get("items", [])
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise LayoutError(f"Layout must have at most {MAX_ITEMS} items.")
    seen = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("source"), str):
            raise LayoutError(f"Item {i+1} requires a source id.")
        uid = item.get("uid") or uuid.uuid4().hex
        if not isinstance(uid, str) or uid in seen:
            raise LayoutError("Item uids must be unique strings.")
        seen.add(uid)
        d["items"].append({"uid": uid, "source": item["source"],
            "x": number(item.get("x", 24), "Item x", -MAX_DIMENSION, MAX_DIMENSION, True),
            "y": number(item.get("y", 24), "Item y", -MAX_DIMENSION, MAX_DIMENSION, True),
            "w": number(item.get("w", 240), "Item width", 1, MAX_DIMENSION, True),
            "h": number(item.get("h", 240), "Item height", 1, MAX_DIMENSION, True),
            "z": number(item.get("z", i), "Layer", -MAX_ITEMS, MAX_ITEMS, True),
            "fit": choice(item.get("fit", "contain"), "Fit", ("contain", "cover", "stretch")),
            "opacity": number(item.get("opacity", 1), "Opacity", 0, 1),
            "visible": bool(item.get("visible", True)),
            "anchorX": number(item.get("anchorX", .5), "Horizontal anchor", 0, 1),
            "anchorY": number(item.get("anchorY", .5), "Vertical anchor", 0, 1)})
    return d, warnings


def sync_items(layout, inventory):
    d = copy.deepcopy(layout)
    current = {s["id"] for s in inventory}
    old = {s["id"] for s in d["sources"]}
    represented = {i["source"] for i in d["items"]}
    warnings = []
    if d["orphans"] == "drop":
        count = sum(i["source"] not in current for i in d["items"])
        d["items"] = [i for i in d["items"] if i["source"] in current]
        if count:
            warnings.append(f"{count} missing items dropped.")
    # A source removed intentionally from items stays removed until it disappears from inventory.
    for s in inventory:
        if s["id"] not in old and s["id"] not in represented:
            n = len(d["items"])
            if n >= MAX_ITEMS:
                raise LayoutError(f"Layout exceeds {MAX_ITEMS} items.")
            w = min(320, s["w"])
            h = max(1, round(w * s["h"] / s["w"]))
            h = min(MAX_DIMENSION, h)
            d["items"].append({"uid": uuid.uuid4().hex, "source": s["id"],
                "x": d["grid"]["padding"] + (n % 4) * 24,
                "y": d["grid"]["padding"] + (n % 4) * 24,
                "w": w, "h": h, "z": n, "fit": "contain", "opacity": 1,
                "visible": True, "anchorX": .5, "anchorY": .5})
    d["sources"] = copy.deepcopy(inventory)
    return d, warnings


def resolve(layout, inventory):
    c, g = layout["canvas"], layout["grid"]
    sources = {s['id']: s for s in inventory}
    items = [copy.deepcopy(i) for i in layout['items'] if i['visible']]
    missing = [i for i in items if i['source'] not in sources]
    warnings = []
    if missing:
        if layout['orphans'] == 'error':
            raise LayoutError(f"{len(missing)} layout items refer to missing images.")
        if layout['orphans'] == 'drop':
            items = [i for i in items if i['source'] in sources]
            warnings.append(f"{len(missing)} missing items dropped.")
        else:
            warnings.append(f"{len(missing)} missing images kept as placeholder frames.")
    w, h = c['w'], c['h']
    pad, gap = g['padding'], g['gap']
    if layout['mode'] != 'custom' and items:
        avail = w - 2 * pad
        if avail < 1:
            raise LayoutError("Canvas width must be larger than twice the padding.")
        if layout['mode'] == 'uniform':
            cols = min(g['columns'], len(items))
            rows = math.ceil(len(items) / cols)
            cw = (avail - (cols - 1) * gap) / cols
            ch = cw if c['heightMode'] == 'auto' else (h - 2 * pad - (rows - 1) * gap) / rows
            if min(cw, ch) < 1:
                raise LayoutError("Grid cells are smaller than one pixel; increase the canvas or reduce gaps/columns.")
            for n, i in enumerate(items):
                x, y = pad + (n % cols)*(cw + gap), pad + (n // cols)*(ch + gap)
                i.update(x=round(x), y=round(y), w=max(1, round(x+cw)-round(x)), h=max(1, round(y+ch)-round(y)))
        else:
            x, y, row_h = pad, pad, 0
            for i in items:
                s = sources.get(i['source'], i)
                ih = g['rowHeight']
                iw = max(1, round(ih * s['w'] / s['h']))
                if iw > avail:
                    ih, iw = max(1, round(ih * avail / iw)), avail
                if x > pad and x + iw > w - pad:
                    x, y, row_h = pad, y + row_h + gap, 0
                i.update(x=round(x), y=round(y), w=round(iw), h=round(ih))
                x += iw + gap
                row_h = max(row_h, ih)
    if c['heightMode'] == 'auto':
        h = max(1, max((i['y'] + i['h'] for i in items), default=c['h']-pad) + pad)
    if h > MAX_DIMENSION or w*h > layout['render']['maxPixels']:
        raise LayoutError(f"Resolved canvas {w}×{h} exceeds dimension or pixel limit ({layout['render']['maxPixels']:,}).")
    if any(i['x'] < 0 or i['y'] < 0 or i['x']+i['w'] > w or i['y']+i['h'] > h for i in items):
        warnings.append("Some frames extend beyond the canvas and will be clipped.")
    return {"canvas": {"w": w, "h": h, "background": c['background']},
            "frames": sorted(items, key=lambda i: i['z']), "warnings": warnings}
