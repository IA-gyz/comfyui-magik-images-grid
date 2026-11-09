# Magik Image Grid

ComfyUI V3 node for composing images with different resolutions into one RGB image.
Choose a uniform grid, rows that preserve source proportions, or a custom collage
with overlapping images. Every image in every connected batch is included on its
first appearance; you can subsequently hide or remove items deliberately.

## Install

1. Extract the archive into your ComfyUI `custom_nodes` directory. The result must
   be `custom_nodes/Magik_Images_Grid/__init__.py`, without an extra nested folder.
2. Restart ComfyUI and reload the browser. If the editor does not appear, perform
   a hard reload in Firefox (`Ctrl+Shift+R`).
3. Add **Magik Image Grid** from **Magik / Image / Display**.

Targets the V3 API used by ComfyUI 0.38.0 (`comfy_api.latest`), including Autogrow.
This package does not register a legacy V1 node. NumPy, Pillow and Torch are
normally already installed with ComfyUI. If a dependency is missing, install
`requirements.txt` using the same Python environment that runs ComfyUI:

```bash
/path/to/comfyui/venv/bin/python -m pip install -r /path/to/Magik_Images_Grid/requirements.txt
```

Do not install a separate Torch build for this node; use ComfyUI's existing one.

## First composition

1. Connect one or more IMAGE outputs. Image sockets grow as connections are added,
   up to 32 sockets. Each socket can receive a batch or a list of batches.
2. Set canvas width, height and background, and choose the layout mode.
3. Run the workflow once. The editor receives the image inventory and thumbnails.
4. Arrange the layout, then run again to render the new composition.
5. Connect **IMAGE** to a **Save Image** or **Preview Image** node to view/save the
   full-quality result. The editor itself displays thumbnails, not a saved output.

`examples/collage.json` is a ready-made overlapping layout for four images in
the first input batch. Import it after connecting that batch, or adjust its source
ids to your inputs.

The node is marked as an output node so it can run and populate its editor even
without a downstream Save Image node. It does not save compositions automatically.
If there are no connected images, it produces a background-only image.

Changes to editor settings are saved in workflow JSON and passed to the backend
on the next execution. Loading a workflow restores the layout immediately;
thumbnail images are refreshed on execution and are not embedded in workflows.

## Layout modes

| Mode | Behavior |
| --- | --- |
| Uniform grid | Equal-sized frames. Columns is the maximum number per row, capped by visible item count. Fixed height divides the available height among rows. Auto height uses square frames. |
| Packed rows | Uses the specified row height and each image's original aspect ratio. Wraps to the next row; a source too wide for one row is reduced to fit. Rows are left aligned, not justified. |
| Custom collage | Absolute pixel positions and frame sizes. Overlap is allowed; higher layers draw last. Frames outside the canvas are clipped. |

**Freeze layout** copies the currently computed frames into custom coordinates.
Dragging or resizing does the same on the first actual movement. Simply selecting
an item does not change mode. Switching back to an automatic mode recomputes
positions without destroying the stored custom coordinates; freezing again
replaces them with the latest automatic arrangement.

**Auto height** computes the bottommost visible frame plus padding. It does not
shift negative coordinates or automatically change width. Fixed height remains
stored as the nominal setting while auto height is enabled. An empty layout uses
that nominal height.

## Editor controls

- Click an image or layer to select it.
- Drag its frame to move it. The bottom-right handle resizes it.
- Aspect lock preserves the frame's proportions during handle resizing; hold
  Shift to bypass it temporarily. Numeric width/height fields remain independent.
- Snap applies to pointer movement and resizing, in output pixels.
- Arrow keys nudge by 1 pixel; Shift + arrow keys nudge by 10 pixels. Click a frame
  first to focus the editor. Text fields retain their normal keyboard behavior.
- **To front / To back** change draw order. The layer list shows topmost first.
- **Duplicate** creates a second use of the same source, offset by 20 pixels.
- **Remove** deletes the selected layout item. It stays removed on later runs
  while the source remains connected. **Add source** can restore it or create
  another instance. **Visible** keeps an item stored while excluding it from output.
- Undo/redo retain up to 60 editor changes for the current browser session.
  `Ctrl+Z`, `Ctrl+Shift+Z` and `Ctrl+Y` operate when the editor canvas is focused.
- `Ctrl+D` duplicates; Delete/Backspace removes; Escape clears selection.
- View zoom changes only the preview. It does not change output resolution.
- **Export JSON / Import JSON** save or load layout settings. Imported layouts use
  the current source inventory. Source ids must correspond to your connected
  socket and batch positions; absent sources follow the missing-image policy.
- **Reset layout** resets settings and creates one item per current source.

## Image fit and compositing

| Setting | Meaning |
| --- | --- |
| Contain | Preserves aspect ratio and fits the whole image inside its frame. Unused space shows lower layers/background. |
| Cover / crop | Preserves aspect ratio, fills the frame and crops excess image content. |
| Stretch | Fills the frame without preserving aspect ratio. |
| Anchor X / Y | Placement of unused/cropped space: 0 = left/top, 0.5 = center, 1 = right/bottom. |
| Opacity | Blends the image over previous layers. RGBA source alpha multiplies item opacity. |

Output is contiguous float32 `[1, H, W, 3]`, in `[0,1]`, on CPU. Rendering retains
floating-point color values rather than converting output to 8-bit pixels. RGBA
sources use premultiplied-alpha resampling to avoid transparent-edge color halos;
the result is flattened against the RGB background. There is no alpha output,
rotation, or multi-selection in this version.

Choose nearest, bilinear, bicubic or Lanczos resampling. Preview thumbnails use
browser scaling, so their filtering may differ slightly from final output.

## Source identities and missing images

`image_0` generates ids `in1:0`, `in1:1`, etc.; `image_1` generates `in2:0`, etc.
Input sockets sort numerically, then all nested list entries and batch images are
flattened in their original order. Socket names, rather than dictionary insertion
order, determine identity. Reordering a batch intentionally changes which image
occupies a positional id. A content hash detects changed pixels but does not track
semantic image identity across batch reorderings.

New sources automatically receive one item. A previously removed item is not
recreated just because the same source executes again. Sources that disappear
from inventory and later return are treated as new appearances.

Missing-image policies:

- **Keep empty frame:** retain geometry and show a striped editor placeholder;
  rendering draws nothing in that frame, leaving lower layers/background visible.
- **Drop item:** remove missing items from the stored layout.
- **Stop with error:** fail when a visible item references a missing source.

The backend reports added, removed and changed sources, missing frames, upscaled
items and warnings. Edits made while execution is running are preserved by the
frontend merge: current geometry/settings win, while inventory and genuinely new
sources are updated. ComfyUI executions are assumed to be delivered in queue order.

## Limits and performance

- 32 growing IMAGE sockets; up to 4096 source images and 8192 layout items per run.
- Canvas dimensions up to 32768 pixels per axis; default/hard ceiling is 64 million
  pixels. Lower **Max megapixels** to set a smaller output allocation limit.
- Frame coordinates range from -32768 to +32768; frame dimensions are 1–32768.
- Source thumbnails cover the first 256 images, with a longest edge of 128 pixels.
  Remaining images use labeled mockups. All sources still render at full quality.
- Layout JSON is limited to 8 MB. Invalid numerical settings fail with an
  actionable error. Malformed JSON falls back to defaults with a warning.
- Input float values outside `[0,1]` are clipped. NaN/infinity and invalid image
  shapes are rejected. Standalone tests also support uint8 and one-channel images.

Rendering uses CPU/Pillow, not CUDA. Torch inputs are detached, copied to CPU if
necessary, and converted to float32. There is no persistent server-side cache.
Source hashing and CPU transfers add work each execution. Mixed-size sources are
kept as separate arrays rather than padded into a common input batch.

The output buffer uses 12 bytes/pixel: 4096×4096 is 192 MiB; a 64-million-pixel
canvas is about 732 MiB. Peak RAM also includes source images, CPU conversion,
resampling and alpha buffers. **Max megapixels limits output size, not total RAM.**
Clipped frames resize only their visible source region, avoiding giant off-canvas
intermediate output images. Thumbnail conversion downsamples before making 8-bit
pixels to keep thumbnail allocation small.

## Code map and layout contract

| File | Responsibility |
| --- | --- |
| `__init__.py` | V3 extension registration and `WEB_DIRECTORY`. |
| `nodes.py` | Autogrow schema, Torch output wrapping and raw dictionary UI return. |
| `pipeline.py` | Source expansion → diff → sync → resolve → compose → UI payload. |
| `sources.py` | Tensor/array conversion, batch flattening, hashing and thumbnails. |
| `layout_engine.py` | Schema validation, item synchronization and frame geometry. |
| `compositor.py` | Float32 fit/crop, clipping, resampling and alpha blending. |
| `js/layout.js` | Validated editor model, matching geometry, execution merge and hashing. |
| `js/editor.js` | DOM controls, pointer interactions and undo/redo. |
| `js/magik_grid.js` | ComfyUI extension hooks and hidden layout widget integration. |
| `js/editor.css` | Scoped styles and responsive panel layout. |

Layout schema `v=1` contains `mode`, `canvas`, `grid`, `render`, `orphans`, `sources`
and `items`. Each item stores `uid`, `source`, `x`, `y`, `w`, `h`, `z`, `fit`,
`opacity`, `visible`, `anchorX`, `anchorY`. Units are output pixels; anchors are
fractions. The original `layout` STRING widget remains at its original serializer
position but is visually hidden. The added DOM widget is not serialized.

The UI event key is `magik_image_grid`, holding a one-element payload list. Payload
fields: `v`, `received`, `layout`, `resolved`, `inventory`, `diff`, `missing`,
`upscaled`, `warnings`, `thumbnails`. `received` is FNV-1a 32-bit over the exact
submitted layout's UTF-8 bytes, encoded as eight hexadecimal characters. An exact
hash match accepts the backend layout; a mismatch merges into current editor
state to preserve in-flight edits. Backend and frontend use ties-to-even rounding
for matching integer frames.

## Verification

From this folder, the backend tests run without ComfyUI or Torch:

```bash
python -m unittest discover -s . -v
npm test
```

`npm test` needs Node.js but no package installation. Optional DOM tests need the
development dependencies:

```bash
npm install
npm run test:dom
```

The package was checked with 36 Python tests, 11 JavaScript tests (including 60
cross-language geometry fixtures), DOM interaction tests, and real Chromium
pointer/resize/responsive checks. The V3 schema and dictionary UI return were
checked against ComfyUI 0.38.0 source. **A complete live ComfyUI workflow was not
available in the build environment**, so installation in your runtime is the
remaining integration check.
