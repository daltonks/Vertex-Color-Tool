import sys

import bpy


class MESH_OT_vertex_color_shortcuts(bpy.types.Operator):
    """Show keyboard shortcuts for the Vertex Color Tool"""
    bl_idname = "mesh.vertex_color_shortcuts"
    bl_label = "Shortcuts"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=250)

    def draw(self, context):
        mod = "Cmd" if sys.platform == 'darwin' else "Ctrl"
        layout = self.layout
        layout.label(text=f"{mod}+Shift+V — Paint")
        layout.label(text=f"{mod}+Shift+C — Eyedropper")
        layout.label(text=f"{mod}+Shift+G — Gradient")

    def execute(self, context):
        return {'FINISHED'}


class MESH_PT_vertex_color_tool(bpy.types.Panel):
    """Vertex color painting controls"""
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
        row.operator("mesh.vertex_color_shortcuts", text="", icon='INFO')

        grad_row = layout.row(align=True)
        grad_row.prop(scn, "vertex_color_gradient_end", text="")
        grad_row.operator("mesh.vertex_color_gradient", text="Gradient", icon='SMOOTHCURVE')


def register_properties():
    bpy.types.Scene.vertex_color_value = bpy.props.FloatVectorProperty(
        name="Color",
        description="The color to paint onto selected geometry",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )
    bpy.types.Scene.vertex_color_gradient_end = bpy.props.FloatVectorProperty(
        name="Gradient End",
        description="The second color used by the gradient tool",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
    )


def unregister_properties():
    del bpy.types.Scene.vertex_color_gradient_end
    del bpy.types.Scene.vertex_color_value


def register_keymaps(keymaps_list):
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    use_oskey = sys.platform == 'darwin'
    use_ctrl = not use_oskey

    for km_name in ("Mesh", "Object Mode"):
        km = kc.keymaps.new(name=km_name, space_type='EMPTY')
        kmi = km.keymap_items.new(
            "mesh.assign_vertex_color", 'V', 'PRESS',
            oskey=use_oskey, ctrl=use_ctrl, shift=True,
        )
        keymaps_list.append((km, kmi))
        kmi = km.keymap_items.new(
            "mesh.pick_vertex_color", 'C', 'PRESS',
            oskey=use_oskey, ctrl=use_ctrl, shift=True,
        )
        keymaps_list.append((km, kmi))
        kmi = km.keymap_items.new(
            "mesh.vertex_color_gradient", 'G', 'PRESS',
            oskey=use_oskey, ctrl=use_ctrl, shift=True,
        )
        keymaps_list.append((km, kmi))


def unregister_keymaps(keymaps_list):
    for km, kmi in keymaps_list:
        km.keymap_items.remove(kmi)
    keymaps_list.clear()
