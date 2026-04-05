bl_info = {
    "name": "Vertex Color Tool",
    "blender": (5, 0, 0),
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
    from . import op_eyedropper, op_paint, ui
    importlib.reload(color_attr)
    importlib.reload(raycast)
    importlib.reload(palette_state)
    importlib.reload(palette_replace)
    importlib.reload(palette_ops)
    importlib.reload(op_eyedropper)
    importlib.reload(op_paint)
    importlib.reload(ui)

import bpy

from .op_eyedropper import MESH_OT_pick_vertex_color
from .op_paint import MESH_OT_assign_vertex_color
from .palette_ops import (
    MESH_OT_edit_palette_color,
    MESH_OT_scene_color_palette,
    MESH_OT_select_palette_color,
    MESH_OT_trim_palette,
    VertexColorPaletteEntry,
)
from .palette_state import (
    on_file_loaded,
    reset as reset_palette,
)
from .ui import (
    draw_header,
    register_keymaps,
    register_properties,
    unregister_keymaps,
    unregister_properties,
)

_addon_keymaps = []

_classes = (
    VertexColorPaletteEntry,
    MESH_OT_pick_vertex_color,
    MESH_OT_assign_vertex_color,
    MESH_OT_select_palette_color,
    MESH_OT_edit_palette_color,
    MESH_OT_trim_palette,
    MESH_OT_scene_color_palette,
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
    bpy.types.VIEW3D_HT_header.append(draw_header)
    bpy.app.handlers.load_post.append(on_file_loaded)

    register_properties()
    register_keymaps(_addon_keymaps)


def unregister():
    unregister_keymaps(_addon_keymaps)
    unregister_properties()

    reset_palette()
    if on_file_loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_file_loaded)
    try:
        bpy.types.VIEW3D_HT_header.remove(draw_header)
    except ValueError:
        pass

    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

    if hasattr(bpy.types.WindowManager, 'vertex_color_palette'):
        del bpy.types.WindowManager.vertex_color_palette


if __name__ == "__main__":
    register()
