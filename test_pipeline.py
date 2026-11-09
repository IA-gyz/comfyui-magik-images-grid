import importlib.util
import json
import os
import sys
import types
import unittest

import numpy as np

import layout_engine as le
import pipeline as pl

HERE = os.path.dirname(os.path.abspath(__file__))


def rnd(*shape, seed=0):
    return np.random.default_rng(seed).random(shape, dtype=np.float32)


def slots():
    return {
        "image_0": [rnd(1, 64, 64, 3)],
        "image_1": [rnd(1, 80, 48, 3, seed=1), rnd(2, 48, 80, 3, seed=2)],
    }


class Fnv(unittest.TestCase):
    def test_known_vectors(self):
        self.assertEqual(pl.fnv1a32(""), "811c9dc5")
        self.assertEqual(pl.fnv1a32("a"), "e40c292c")
        self.assertEqual(pl.fnv1a32("foobar"), "bf9cf968")

    def test_utf8(self):
        self.assertNotEqual(pl.fnv1a32("é"), pl.fnv1a32("e"))


class Run(unittest.TestCase):
    def test_first_run_populates_layout_and_payload(self):
        res = pl.run(slots(), [""])
        p = res.payload
        self.assertEqual(res.canvas.shape, (1000, 1500, 3))
        self.assertEqual(len(p["inventory"]), 4)
        self.assertEqual(len(p["layout"]["items"]), 4)
        self.assertEqual(len(p["resolved"]["frames"]), 4)
        self.assertEqual(p["diff"]["added"], ["in1:0", "in2:0", "in2:1", "in2:2"])
        self.assertEqual(p["received"], pl.fnv1a32(""))
        json.dumps(p)  # JSON-safe for the websocket

    def test_second_run_is_stable_and_reports_no_diff(self):
        first_run = pl.run(slots(), [""])
        text = json.dumps(first_run.layout)
        second = pl.run(slots(), [text])
        self.assertEqual(second.payload["received"], pl.fnv1a32(text))
        self.assertEqual(second.payload["diff"], {"added": [], "removed": [], "changed": []})
        self.assertEqual([i["uid"] for i in second.layout["items"]], [i["uid"] for i in first_run.layout["items"]])
        np.testing.assert_allclose(second.canvas, first_run.canvas)

    def test_changed_content_and_removed_socket_are_reported(self):
        text = json.dumps(pl.run(slots(), [""]).layout)
        s2 = {"image_0": [rnd(1, 64, 64, 3, seed=9)], "image_1": None}
        res = pl.run(s2, [text])
        self.assertEqual(res.payload["diff"]["changed"], ["in1:0"])
        self.assertEqual(res.payload["diff"]["removed"], ["in2:0", "in2:1", "in2:2"])
        self.assertEqual(len(res.payload["missing"]), 3)
        self.assertTrue(any("placeholder" in w for w in res.payload["warnings"]))

    def test_orphan_error_policy_raises(self):
        lay = pl.run(slots(), [""]).layout
        lay["orphans"] = "error"
        with self.assertRaises(le.LayoutError):
            pl.run({"image_0": [rnd(1, 64, 64, 3)]}, [json.dumps(lay)])

    def test_malformed_layout_falls_back_with_warning(self):
        res = pl.run(slots(), ["{not json"])
        self.assertTrue(any("malformed" in w for w in res.payload["warnings"]))
        self.assertEqual(len(res.layout["items"]), 4)

    def test_no_images_warns_but_renders_background(self):
        res = pl.run({"image_0": []}, [""])
        self.assertTrue(any("No images" in w for w in res.payload["warnings"]))
        self.assertEqual(res.canvas.shape, (1000, 1500, 3))

    def test_all_modes_render(self):
        for mode in ("uniform", "packed", "custom"):
            lay, _ = le.normalize_layout(None)
            lay["mode"] = mode
            lay["canvas"].update({"w": 400, "h": 300})
            res = pl.run(slots(), [json.dumps(lay)])
            self.assertEqual(res.canvas.shape, (300, 400, 3), mode)
            self.assertEqual(res.payload["layout"]["mode"], mode)

    def test_auto_height_reports_effective_canvas(self):
        lay, _ = le.normalize_layout(None)
        lay["canvas"].update({"w": 400, "h": 300, "heightMode": "auto"})
        res = pl.run(slots(), [json.dumps(lay)])
        self.assertEqual(res.canvas.shape[0], res.payload["resolved"]["canvas"]["h"])
        self.assertEqual(res.payload["layout"]["canvas"]["h"], 300)  # nominal height stays as stored

    def test_max_pixels_guard(self):
        lay, _ = le.normalize_layout(None)
        lay["render"]["maxPixels"] = 1024
        with self.assertRaises(le.LayoutError):
            pl.run(slots(), [json.dumps(lay)])

    def test_non_string_layout_value_is_tolerated(self):
        self.assertEqual(pl.run(slots(), [None]).payload["received"], pl.fnv1a32(""))


class NodeSmoke(unittest.TestCase):
    """Loads the package against stubbed comfy_api/torch. Checks wiring only, not real ComfyUI signatures."""

    def setUp(self):
        self.saved = {k: sys.modules.get(k) for k in ("comfy_api", "comfy_api.latest", "comfy_api.latest._ui", "torch")}
        calls = self.calls = {}

        class Schema:
            def __init__(self, **kw):
                calls["schema"] = kw

        class Field:
            def __init__(self, *a, **kw):
                self.a, self.kw = a, kw

        class Autogrow:
            class Input(Field): pass
            class TemplatePrefix(Field): pass

        class NodeOutput:
            def __init__(self, *args, ui=None, **kw):
                self.args, self.ui = args, ui

        io = types.SimpleNamespace(
            ComfyNode=type("ComfyNode", (), {}), Schema=Schema, Autogrow=Autogrow,
            Image=types.SimpleNamespace(Input=Field, Output=Field),
            String=types.SimpleNamespace(Input=Field), NodeOutput=NodeOutput,
        )

        class ComfyExtension:  # noqa: D401
            pass

        latest = types.ModuleType("comfy_api.latest")
        latest.io, latest.ComfyExtension = io, ComfyExtension
        ui_mod = types.ModuleType("comfy_api.latest._ui")
        ui_mod._UIOutput = type("_UIOutput", (), {})
        torch = types.ModuleType("torch")

        class FakeTensor:
            def __init__(self, a): self.a = a
            def unsqueeze(self, d): return FakeTensor(self.a[None])

        torch.from_numpy = FakeTensor
        pkg = types.ModuleType("comfy_api")
        pkg.latest = latest
        sys.modules.update({"comfy_api": pkg, "comfy_api.latest": latest, "comfy_api.latest._ui": ui_mod, "torch": torch})

        for name in [n for n in sys.modules if n.startswith("Magik_Images_Grid")]:
            del sys.modules[name]
        spec = importlib.util.spec_from_file_location(
            "Magik_Images_Grid", os.path.join(HERE, "__init__.py"), submodule_search_locations=[HERE])
        self.pkg = importlib.util.module_from_spec(spec)
        sys.modules["Magik_Images_Grid"] = self.pkg
        spec.loader.exec_module(self.pkg)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        for name in [n for n in sys.modules if n.startswith("Magik_Images_Grid")]:
            del sys.modules[name]

    def test_schema_and_registration(self):
        node = self.pkg.nodes.MagikImageGrid
        node.define_schema()
        s = self.calls["schema"]
        self.assertEqual(s["node_id"], "MagikImageGrid")
        self.assertEqual(s["category"], "Magik/Image/Display")
        self.assertTrue(s["is_input_list"])
        self.assertTrue(s["is_output_node"])
        self.assertEqual([i.a[0] for i in s["inputs"]], ["images", "layout"])
        tmpl = s["inputs"][0].kw["template"]
        self.assertEqual(tmpl.kw["prefix"], "image_")
        self.assertTrue(s["inputs"][1].kw["socketless"])
        self.assertEqual(self.pkg.WEB_DIRECTORY, "./js")
        import asyncio
        ext = asyncio.run(self.pkg.comfy_entrypoint())
        self.assertEqual(asyncio.run(ext.get_node_list()), [node])

    def test_execute_returns_tensor_and_wrapped_ui(self):
        out = self.pkg.nodes.MagikImageGrid.execute(slots(), [""])
        self.assertEqual(out.args[0].a.shape, (1, 1000, 1500, 3))
        d = out.ui
        self.assertEqual(list(d), [pl.PAYLOAD_KEY])
        self.assertIsInstance(d[pl.PAYLOAD_KEY], list)       # list-wrapped: ComfyUI merges ui values as lists
        self.assertEqual(len(d[pl.PAYLOAD_KEY][0]["inventory"]), 4)


if __name__ == "__main__":
    unittest.main(verbosity=1)
