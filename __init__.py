"""Magik Image Grid: ComfyUI custom node package (V3 / Nodes 2.0 only)."""
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io

from .nodes import MagikImageGrid

WEB_DIRECTORY = "./js"


class MagikImagesGridExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [MagikImageGrid]


async def comfy_entrypoint() -> MagikImagesGridExtension:
    return MagikImagesGridExtension()
