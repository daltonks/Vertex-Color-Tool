bl_info = {
    "name": "Vertex Color Tool",
    "blender": (5, 1, 0),
    "category": "Mesh",
    "version": (1, 4, 0),
    "author": "BobHop & Dalton Spillman",
    "description": "Paint vertex colors on meshes in edit and object mode, "
                   "with eyedropper sampling, scene palette, and per-vertex "
                   "or per-face application",
}

if "bpy" in locals():
    import importlib
    from . import color_attr, raycast, palette_state, palette_replace, palette_ops
    from . import op_eyedropper, op_gradient, op_paint, ui
    importlib.reload(color_attr)
    importlib.reload(raycast)
    importlib.reload(palette_state)
    importlib.reload(palette_replace)
    importlib.reload(palette_ops)
    importlib.reload(op_eyedropper)
    importlib.reload(op_gradient)
    importlib.reload(op_paint)
    importlib.reload(ui)

import bpy

from .op_eyedropper import MESH_OT_pick_vertex_color
from .op_gradient import MESH_OT_vertex_color_gradient
from .op_paint import MESH_OT_assign_vertex_color
from .palette_ops import (
    MESH_OT_edit_palette_color,
    MESH_OT_trim_palette,
    MESH_OT_use_palette_color,
    MESH_OT_vertex_color_shortcuts,
    MESH_PT_vertex_color_tool,
    VertexColorPaletteEntry,
    register_previews,
    unregister_previews,
)
from .palette_state import (
    on_file_loaded,
    on_undo_redo,
    reset as reset_palette,
)
from .ui import (
    register_keymaps,
    register_properties,
    unregister_keymaps,
    unregister_properties,
)

_addon_keymaps = []

_classes = (
    VertexColorPaletteEntry,
    MESH_OT_pick_vertex_color,
    MESH_OT_vertex_color_gradient,
    MESH_OT_assign_vertex_color,
    MESH_OT_use_palette_color,
    MESH_OT_edit_palette_color,
    MESH_OT_trim_palette,
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

    bpy.types.WindowManager.vertex_color_palette = bpy.props.CollectionProperty(
        type=VertexColorPaletteEntry,
    )
    bpy.app.handlers.load_post.append(on_file_loaded)
    bpy.app.handlers.undo_post.append(on_undo_redo)
    bpy.app.handlers.redo_post.append(on_undo_redo)
    register_previews()

    register_properties()
    register_keymaps(_addon_keymaps)


def unregister():
    unregister_keymaps(_addon_keymaps)
    unregister_properties()

    reset_palette()
    if on_file_loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_file_loaded)
    if on_undo_redo in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(on_undo_redo)
    if on_undo_redo in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.remove(on_undo_redo)
    unregister_previews()

    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

    if hasattr(bpy.types.WindowManager, 'vertex_color_palette'):
        del bpy.types.WindowManager.vertex_color_palette


if __name__ == "__main__":
    register()
