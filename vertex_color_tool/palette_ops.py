"""Palette UI operators and property group."""

import bpy
import bpy.utils.previews

from . import palette_state as state
from .palette_replace import replace_color_in_meshes

_preview_collection = None
_ICON_SIZE = 32


def _linear_to_srgb(c):
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _get_color_icon(color_tuple):
    """Get or create a preview icon filled with the given color."""
    key = str(color_tuple)
    if key in _preview_collection:
        return _preview_collection[key].icon_id

    preview = _preview_collection.new(key)
    preview.image_size = (_ICON_SIZE, _ICON_SIZE)
    r = _linear_to_srgb(color_tuple[0])
    g = _linear_to_srgb(color_tuple[1])
    b = _linear_to_srgb(color_tuple[2])
    a = color_tuple[3]
    pixel = [r, g, b, a]
    preview.image_pixels_float = pixel * (_ICON_SIZE * _ICON_SIZE)
    return preview.icon_id


class VertexColorPaletteEntry(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(subtype='COLOR', size=4, min=0.0, max=1.0)


class MESH_OT_use_palette_color(bpy.types.Operator):
    """Set this as the active color to paint with"""
    bl_idname = "mesh.use_palette_color"
    bl_label = "Use Palette Color"
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty()

    def execute(self, context):
        palette = context.window_manager.vertex_color_palette
        if 0 <= self.index < len(palette):
            context.scene.vertex_color_value = palette[self.index].color
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


class MESH_OT_edit_palette_color(bpy.types.Operator):
    """Replace the currently selected color across every mesh in the scene"""
    bl_idname = "mesh.edit_palette_color"
    bl_label = "Edit Selected Color"
    bl_options = {'REGISTER', 'UNDO'}

    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )

    def invoke(self, context, event):
        self.color = context.scene.vertex_color_value
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        old_color = state.quantize(*context.scene.vertex_color_value)
        new_color = state.quantize(*self.color)
        if old_color == new_color:
            return {'CANCELLED'}

        replace_color_in_meshes(old_color, tuple(self.color))
        context.scene.vertex_color_value = self.color
        _preview_collection.pop(str(old_color), None)
        state.write_to_ui(context.window_manager)
        return {'FINISHED'}

    def draw(self, context):
        self.layout.prop(self, "color", text="")



class MESH_OT_trim_palette(bpy.types.Operator):
    """Sync the palette with the scene, removing colors no longer used by any mesh"""
    bl_idname = "mesh.trim_palette"
    bl_label = "Refresh Palette"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if state.reconcile(context.scene):
            _preview_collection.clear()
            state.write_to_ui(context.window_manager)
        return {'FINISHED'}


class MESH_OT_vertex_color_shortcuts(bpy.types.Operator):
    """Show keyboard shortcuts for the Vertex Color Tool"""
    bl_idname = "mesh.vertex_color_shortcuts"
    bl_label = "Shortcuts"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=250)

    def draw(self, context):
        import sys
        mod = "Cmd" if sys.platform == 'darwin' else "Ctrl"
        layout = self.layout
        layout.label(text=f"{mod}+Shift+V — Paint")
        layout.label(text=f"{mod}+Shift+C — Eyedropper")

    def execute(self, context):
        return {'FINISHED'}




class MESH_PT_vertex_color_tool(bpy.types.Panel):
    """Vertex color painting controls and scene palette"""
    bl_idname = "MESH_PT_vertex_color_tool"
    bl_label = "Vertex Color Tool"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        scn = context.scene

        if not hasattr(scn, 'vertex_color_value'):
            return

        row = layout.row(align=True)
        row.prop(scn, "vertex_color_value", text="")
        row.operator("mesh.edit_palette_color", text="", icon='GREASEPENCIL')
        row.operator("mesh.vertex_color_shortcuts", text="", icon='INFO')

        state.ensure_scanned(context.scene)
        palette = context.window_manager.vertex_color_palette

        if not palette:
            layout.label(text="No colors in palette")
            return

        grid = layout.grid_flow(columns=6, even_columns=True, align=True)
        for i, entry in enumerate(palette):
            icon_id = _get_color_icon(tuple(entry.color))
            op = grid.operator("mesh.use_palette_color", text="", icon_value=icon_id)
            op.index = i

        layout.operator("mesh.trim_palette", icon='FILE_REFRESH')





def register_previews():
    global _preview_collection
    _preview_collection = bpy.utils.previews.new()


def unregister_previews():
    global _preview_collection
    if _preview_collection is not None:
        bpy.utils.previews.remove(_preview_collection)
        _preview_collection = None
