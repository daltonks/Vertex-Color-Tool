import sys

import bpy


def draw_header(self, context):
    """Appended to VIEW3D_HT_header — draws the vertex color controls inline."""
    layout = self.layout
    scn = context.scene

    row = layout.row(align=True)
    row.separator()
    mode_icon = 'FACESEL' if scn.vertex_color_apply_mode == 'FACE' else 'VERTEXSEL'
    row.prop(scn, "vertex_color_apply_mode", text="", icon=mode_icon)
    row.prop(scn, "vertex_color_value", text="")
    row.operator("mesh.pick_vertex_color", text="", icon='EYEDROPPER')
    row.operator("mesh.scene_color_palette", text="", icon='COLOR')
    row.operator("mesh.assign_vertex_color", text="", icon='CHECKMARK')


def register_properties():
    bpy.types.Scene.vertex_color_apply_mode = bpy.props.EnumProperty(
        name="Apply Mode",
        description="How color is applied to geometry",
        items=[
            ('VERTEX', "Vertex Style",
             "Color blends smoothly across faces sharing a vertex. "
             "Select vertices or edges to paint them"),
            ('FACE', "Face Corner",
             "Color is applied per face corner, creating sharp boundaries between faces. "
             "Select whole faces for sharp fills, or individual vertices/edges for partial painting"),
        ],
        default='FACE',
    )
    bpy.types.Scene.vertex_color_value = bpy.props.FloatVectorProperty(
        name="Color",
        description="The color to paint onto selected geometry",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )


def unregister_properties():
    del bpy.types.Scene.vertex_color_apply_mode
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


def unregister_keymaps(keymaps_list):
    for km, kmi in keymaps_list:
        km.keymap_items.remove(kmi)
    keymaps_list.clear()
