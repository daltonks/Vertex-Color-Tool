"""Palette UI operators and property group."""

import bpy

from . import palette_state as state
from .palette_replace import replace_color_in_meshes


def _on_palette_color_changed(self, context):
    if state.suppressing_updates:
        return

    palette = context.window_manager.vertex_color_palette
    index = next((i for i, entry in enumerate(palette) if entry == self), -1)
    if index < 0:
        return

    old_color = state.palette_snapshot.get(index)
    if old_color is None:
        return

    new_color = state.quantize(*self.color)
    if old_color == new_color:
        return

    replace_color_in_meshes(old_color, tuple(self.color))
    state.palette_snapshot[index] = new_color


class VertexColorPaletteEntry(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(
        subtype='COLOR', size=4, min=0.0, max=1.0,
        update=_on_palette_color_changed,
    )


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


class MESH_OT_scene_color_palette(bpy.types.Operator):
    """Browse and edit all unique vertex colors currently in the scene. Changing a color updates every mesh that uses it"""
    bl_idname = "mesh.scene_color_palette"
    bl_label = "Scene Palette"

    def invoke(self, context, event):
        state.rebuild(context.scene)
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
            col.operator_context = 'EXEC_DEFAULT'
            op = col.operator("mesh.select_palette_color", text="Use")
            op.index = i

    def execute(self, context):
        return {'FINISHED'}
