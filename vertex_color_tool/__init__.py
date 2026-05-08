bl_info = {
    "name": "Vertex Color Tool",
    "blender": (5, 1, 0),
    "category": "Mesh",
    "version": (1, 4, 0),
    "author": "BobHop & Dalton Spillman",
    "description": "Paint vertex colors on meshes in edit and object mode, "
                   "with eyedropper sampling and per-vertex "
                   "or per-face application",
}

if "bpy" in locals():
    import importlib
    from . import color_attr, paint, raycast
    from . import op_eyedropper, op_gradient, op_paint, ui
    importlib.reload(color_attr)
    importlib.reload(paint)
    importlib.reload(raycast)
    importlib.reload(op_eyedropper)
    importlib.reload(op_gradient)
    importlib.reload(op_paint)
    importlib.reload(ui)

import bpy

from .op_eyedropper import MESH_OT_pick_vertex_color
from .op_gradient import MESH_OT_vertex_color_gradient
from .op_paint import MESH_OT_assign_vertex_color
from .ui import (
    MESH_OT_vertex_color_shortcuts,
    MESH_PT_vertex_color_tool,
    register_keymaps,
    register_properties,
    unregister_keymaps,
    unregister_properties,
)

_addon_keymaps = []

_classes = (
    MESH_OT_pick_vertex_color,
    MESH_OT_vertex_color_gradient,
    MESH_OT_assign_vertex_color,
    MESH_OT_vertex_color_shortcuts,
    MESH_PT_vertex_color_tool,
)


def register():
    for cls in _classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            bpy.utils.unregister_class(cls)
            bpy.utils.register_class(cls)

    register_properties()
    register_keymaps(_addon_keymaps)


def unregister():
    unregister_keymaps(_addon_keymaps)
    unregister_properties()

    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


if __name__ == "__main__":
    register()
