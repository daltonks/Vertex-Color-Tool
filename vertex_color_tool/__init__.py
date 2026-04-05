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

import bpy

from .op_eyedropper import MESH_OT_pick_vertex_color
from .op_paint import MESH_OT_assign_vertex_color
from .palette import (
    MESH_OT_scene_color_palette,
    MESH_OT_select_palette_color,
    VertexColorPaletteEntry,
    on_depsgraph_update,
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
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)

    register_properties()
    register_keymaps(_addon_keymaps)


def unregister():
    unregister_keymaps(_addon_keymaps)
    unregister_properties()

    reset_palette()
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
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
