"""Numerical rendering regressions and hostile-input validation."""
import json
import unittest
from unittest.mock import patch
import numpy as np
import layout_engine as le
from compositor import compose
from pipeline import run
from sources import expand_sources


def solid(color, w=10, h=10):
    a=np.empty((h,w,len(color)),np.float32);a[:]=color;return a


def item(source, **kwargs):
    return dict(uid=source,source=source,x=0,y=0,w=10,h=10,z=0,fit='stretch',opacity=1,visible=True,anchorX=.5,anchorY=.5,**kwargs)


def render(frames, images, w=10, h=10, bg='#000000', filter='nearest'):
    return compose({'canvas':{'w':w,'h':h,'background':bg},'frames':sorted(frames,key=lambda f:f['z'])},images,filter)[0]


class Rendering(unittest.TestCase):
    def test_opaque_overlap_and_layer_order(self):
        red=item('r');blue=item('b');blue.update(x=5,z=1)
        a=render([red,blue],{'r':solid([1,0,0]),'b':solid([0,0,1])},w=15)
        np.testing.assert_array_equal(a[:,0:5],np.broadcast_to([1,0,0],(10,5,3)))
        np.testing.assert_array_equal(a[:,5:],np.broadcast_to([0,0,1],(10,10,3)))

    def test_opacity_over_existing_layer(self):
        b=item('b');b.update(opacity=.25,z=1)
        a=render([item('r'),b],{'r':solid([1,0,0]),'b':solid([0,0,1])})
        np.testing.assert_allclose(a,np.broadcast_to([.75,0,.25],a.shape))

    def test_rgba_and_opacity_multiply(self):
        f=item('a');f['opacity']=.5
        a=render([f],{'a':solid([1,0,0,.5])},bg='#0000ff')
        np.testing.assert_allclose(a,np.broadcast_to([.25,0,.75],a.shape))

    def test_contain_keeps_background_in_letterbox(self):
        f=item('r');f['fit']='contain'
        a=render([f],{'r':solid([1,0,0],w=20,h=10)})
        np.testing.assert_array_equal(a[0],0)
        np.testing.assert_array_equal(a[2:7],np.broadcast_to([1,0,0],(5,10,3)))
        np.testing.assert_array_equal(a[7:],0)

    def test_cover_anchor_selects_left_or_right(self):
        source=solid([1,0,0],w=20);source[:,10:]=[0,0,1]
        f=item('s');f.update(fit='cover',anchorX=0)
        a=render([f],{'s':source})
        np.testing.assert_array_equal(a,np.broadcast_to([1,0,0],a.shape))
        f['anchorX']=1;a=render([f],{'s':source})
        np.testing.assert_array_equal(a,np.broadcast_to([0,0,1],a.shape))

    def test_negative_position_and_offscreen_do_not_wrap(self):
        f=item('r');f.update(x=-5,y=-5)
        a=render([f],{'r':solid([1,0,0])})
        np.testing.assert_array_equal(a[:5,:5],np.broadcast_to([1,0,0],(5,5,3)))
        np.testing.assert_array_equal(a[5:],0);np.testing.assert_array_equal(a[:,5:],0)
        f['x']=20;np.testing.assert_array_equal(render([f],{'r':solid([1,0,0])}),0)

    def test_large_clipped_frame_allocates_only_visible_target(self):
        f=item('r');f.update(w=32768,h=32768)
        a=render([f],{'r':solid([1,0,0])},w=2,h=2)
        np.testing.assert_array_equal(a,np.broadcast_to([1,0,0],a.shape))

    def test_float_precision_is_preserved(self):
        a=render([item('s')],{'s':solid([.123456,.234567,.345678])})
        np.testing.assert_allclose(a,np.broadcast_to([.123456,.234567,.345678],a.shape),atol=1e-7)
        self.assertEqual(a.dtype,np.float32);self.assertTrue(a.flags.c_contiguous)

    def test_missing_item_is_empty_frame(self):
        a=render([item('missing')],{},bg='#ffffff')
        np.testing.assert_array_equal(a,1)

    def test_lanczos_alpha_has_no_hidden_red_fringe(self):
        a=solid([1,0,0,0],w=10);a[:,5:]=[0,1,0,1]
        f=item('s');f['w']=20
        out=render([f],{'s':a},w=20,filter='lanczos')
        np.testing.assert_array_equal(out[:,:,0],0)
        self.assertTrue(np.all(out>=0));self.assertTrue(np.all(out<=1))

    def test_all_filters_accept_clipped_crop(self):
        a=np.random.default_rng(8).random((17,31,3),dtype=np.float32)
        f=item('s');f.update(x=-3,y=-7,w=33,h=22,fit='cover')
        for filt in ('nearest','bilinear','bicubic','lanczos'):
            out=render([f],{'s':a},w=25,h=12,filter=filt)
            self.assertEqual(out.shape,(12,25,3));self.assertTrue(np.isfinite(out).all())


class InputsAndLayout(unittest.TestCase):
    def test_slots_sort_numerically_and_batch_expansion_is_stable(self):
        inventory,_=expand_sources({'image_10':[solid([1,0,0])[None]],'image_2':[np.stack([solid([0,1,0]),solid([0,0,1])])], 'image_0':None})
        self.assertEqual([s['id'] for s in inventory],['in3:0','in3:1','in11:0'])

    def test_uint8_grayscale_and_nested_lists(self):
        inventory,images=expand_sources({'image_0':[[np.full((2,3,1),255,np.uint8)]]})
        self.assertEqual(images['in1:0'].shape,(2,3,3));np.testing.assert_array_equal(images['in1:0'],1)

    def test_nan_and_bad_shapes_are_rejected(self):
        for a in [np.full((2,2,3),np.nan),np.zeros((2,2)),np.zeros((2,2,2))]:
            with self.assertRaises(ValueError):expand_sources({'image_0':a})

    def test_invalid_layout_numeric_fields(self):
        for value in [0,-1,float('nan'),float('inf'),True,'100']:
            d=le.defaults();d['canvas']['w']=value
            with self.assertRaises(le.LayoutError):le.normalize_layout(json.dumps(d))

    def test_wrong_version_and_duplicate_uids(self):
        with self.assertRaises(le.LayoutError):le.normalize_layout('{"v":2}')
        d=le.defaults();d['items']=[item('s'),item('s')]
        with self.assertRaises(le.LayoutError):le.normalize_layout(d)

    def test_deleted_item_is_not_readded_every_execution(self):
        s={'image_0':solid([1,0,0])[None]};r=run(s,['']);d=r.layout;d['items']=[]
        next=run(s,[json.dumps(d)]);self.assertEqual(next.layout['items'],[])

    def test_hidden_items_are_not_rendered(self):
        s={'image_0':solid([1,0,0])[None]};d=run(s,['']).layout;d['items'][0]['visible']=False
        r=run(s,[json.dumps(d)]);self.assertEqual(r.payload['resolved']['frames'],[])

    def test_drop_orphan_policy_removes_item(self):
        s={'image_0':solid([1,0,0])[None]};d=run(s,['']).layout;d['orphans']='drop'
        r=run({},[json.dumps(d)]);self.assertEqual(r.layout['items'],[])

    def test_pixel_guard_prevents_numpy_allocation(self):
        with patch('compositor.np.empty',side_effect=AssertionError('allocation attempted')):
            with self.assertRaises(le.LayoutError):compose({'canvas':{'w':32768,'h':32768,'background':'#000000'},'frames':[]},{})

    def test_auto_height_and_packed_aspect_ratio(self):
        d=le.defaults();d.update(mode='packed');d['canvas'].update(w=400,heightMode='auto');d['grid'].update(padding=10,gap=5,rowHeight=50)
        s={'image_0':[solid([1,0,0],w=200,h=100)[None],solid([0,1,0],w=50,h=100)[None]]}
        r=run(s,[json.dumps(d)]);f=r.payload['resolved']['frames'];self.assertEqual((f[0]['w'],f[0]['h']),(100,50));self.assertEqual((f[1]['w'],f[1]['h']),(25,50));self.assertEqual(r.canvas.shape[:2],(70,400))

    def test_thumbnails_do_not_persist_in_layout(self):
        r=run({'image_0':solid([1,0,0])[None]},[''])
        self.assertTrue(r.payload['thumbnails']['in1:0'].startswith('data:image/png;base64,'));self.assertNotIn('thumbnails',r.layout)

if __name__=='__main__':unittest.main()
