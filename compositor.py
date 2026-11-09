"""Float32 RGB composition; crop before resizing to bound intermediate allocations."""
from __future__ import annotations
import numpy as np
from PIL import Image
if __package__:
    from .layout_engine import LayoutError, MAX_PIXELS, MAX_DIMENSION
else:
    from layout_engine import LayoutError, MAX_PIXELS, MAX_DIMENSION

FILTERS = {name: getattr(Image.Resampling, name.upper()) for name in ('nearest','bilinear','bicubic','lanczos')}


def compose(resolved, images, resample='lanczos', max_pixels=MAX_PIXELS):
    c = resolved['canvas']
    w, h = c['w'], c['h']
    if min(w,h) < 1 or max(w,h) > MAX_DIMENSION or w*h > min(MAX_PIXELS,max_pixels):
        raise LayoutError("Canvas exceeds the rendering memory guard.")
    bg = [int(c['background'][n:n+2], 16)/255 for n in (1,3,5)]
    canvas = np.empty((h,w,3), dtype=np.float32)
    canvas[:] = bg
    report = {'missing': [], 'upscaled': []}
    for f in resolved['frames']:
        sid = f['source']
        if sid not in images:
            report['missing'].append(f['uid'])
            # Missing image occupies its frame but draws nothing over the background/lower layers.
            continue
        a = images[sid]
        sh, sw = a.shape[:2]
        fw, fh, x, y = f['w'], f['h'], f['x'], f['y']
        if f['fit'] == 'stretch':
            dw, dh = fw, fh
        else:
            scale = (min if f['fit'] == 'contain' else max)(fw/sw, fh/sh)
            dw, dh = max(1,round(sw*scale)), max(1,round(sh*scale))
        if dw > sw or dh > sh:
            report['upscaled'].append(f['uid'])
        dx = x + round((fw-dw)*f['anchorX'])
        dy = y + round((fh-dh)*f['anchorY'])
        left, top = max(0,x,dx), max(0,y,dy)
        right, bottom = min(w,x+fw,dx+dw), min(h,y+fh,dy+dh)
        if right <= left or bottom <= top or f['opacity'] == 0:
            continue
        size = (right-left,bottom-top)
        box = ((left-dx)*sw/dw, (top-dy)*sh/dh, (right-dx)*sw/dw, (bottom-dy)*sh/dh)
        filt = FILTERS[resample]
        def resized(channel):
            im = Image.fromarray(np.ascontiguousarray(channel, dtype=np.float32))
            return np.asarray(im.resize(size, resample=filt, box=box), dtype=np.float32)
        alpha = np.clip(resized(a[:,:,3]),0,1) if a.shape[2] == 4 else None
        target = canvas[top:bottom,left:right]
        coverage = f['opacity'] if alpha is None else alpha * f['opacity']
        for ch in range(3):
            # Resize premultiplied colors to prevent halos at transparent edges.
            channel = a[:,:,ch] if alpha is None else a[:,:,ch]*a[:,:,3]
            color = np.clip(resized(channel),0,1)
            if alpha is not None:
                color = np.minimum(color, alpha)
            target[:,:,ch] *= 1-coverage
            target[:,:,ch] += color*f['opacity']
    np.clip(canvas,0,1,out=canvas)
    return canvas, report
