"""ComfyUI V3 wrapper. All rendering logic remains independently testable."""
from __future__ import annotations
import torch
from comfy_api.latest import io
from .pipeline import PAYLOAD_KEY, run

MAX_INPUT_SLOTS = 32

class MagikImageGrid(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id='MagikImageGrid', display_name='Magik Image Grid',
            category='Magik/Image/Display',
            description='Compose images and every image in their batches. Use uniform grid, packed rows or overlapping custom collage. Run once to load image inventory into the editor.',
            inputs=[
                io.Autogrow.Input('images', template=io.Autogrow.TemplatePrefix(
                    input=io.Image.Input('image', optional=True), prefix='image_', min=1, max=MAX_INPUT_SLOTS)),
                io.String.Input('layout', default='', multiline=True, socketless=True),
            ],
            outputs=[io.Image.Output('IMAGE')], is_input_list=True, is_output_node=True)

    @classmethod
    def execute(cls, images, layout):
        result = run(images, layout)
        tensor = torch.from_numpy(result.canvas).unsqueeze(0)
        return io.NodeOutput(tensor, ui={PAYLOAD_KEY: [result.payload]})
