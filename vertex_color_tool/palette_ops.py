"""Palette UI operators and property group."""

import bpy

from . import palette_state as state
from .palette_replace import replace_color_in_meshes


class VertexColorPaletteEntry(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(subtype='COLOR', size=4, min=0.0, max=1.0)


class MESH_OT_select_palette_color(bpy.types.Operator):
    """Set this as the active color to paint with"""
    bl_idname = "mesh.select_palette_color"
    bl_label = "Use Color"
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty()

    def execute(self, context):
        palette = context.window_manager.vertex_color_palette
        if 0 <= self.index < len(palette):
            context.scene.vertex_color_value = palette[self.index].color
        return {'FINISHED'}


class MESH_OT_edit_palette_color(bpy.types.Operator):
    """Replace this color across every mesh in the scene"""
    bl_idname = "mesh.edit_palette_color"
    bl_label = "Edit Palette Color"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty()
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )

    def invoke(self, context, event):
        palette = context.window_manager.vertex_color_palette
        if 0 <= self.index < len(palette):
            self.color = palette[self.index].color
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        old_color = state.palette_snapshot.get(self.index)
        if old_color is None:
            return {'CANCELLED'}

        new_color = state.quantize(*self.color)
        if old_color == new_color:
            return {'CANCELLED'}

        replace_color_in_meshes(old_color, tuple(self.color))
        state.write_to_ui(context.window_manager)
        return {'FINISHED'}

    def draw(self, context):
        self.layout.prop(self, "color", text="")


class MESH_OT_trim_palette(bpy.types.Operator):
    """Remove colors from the palette that are no longer used by any mesh in the scene"""
    bl_idname = "mesh.trim_palette"
    bl_label = "Trim Unused"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        state.trim(context.scene)
        return {'FINISHED'}


class MESH_OT_scene_color_palette(bpy.types.Operator):
    """Browse and edit all unique vertex colors currently in the scene. Changing a color updates every mesh that uses it"""
    bl_idname = "mesh.scene_color_palette"
    bl_label = "Scene Palette"

    def invoke(self, context, event):
        state.ensure_scanned(context.scene)
        state.write_to_ui(context.window_manager)
        return context.window_manager.invoke_popup(self, width=250)

    def draw(self, context):
        layout = self.layout
        palette = context.window_manager.vertex_color_palette

        if not palette:
            layout.label(text="No painted meshes found in this scene")
            return

        grid = layout.grid_flow(columns=5, even_columns=True, align=True)
        for i, entry in enumerate(palette):
            col = grid.column(align=True)
            col.prop(entry, "color", text="")
            col = grid.column(align=True)
            row = col.row(align=True)
            op = row.operator("mesh.select_palette_color", text="", icon='CHECKMARK')
            op.index = i
            op = row.operator("mesh.edit_palette_color", text="", icon='GREASEPENCIL')
            op.index = i

        layout.separator()
        layout.operator("mesh.trim_palette", icon='BRUSH_DATA')

    def execute(self, context):
        return {'FINISHED'}
