import sys

import bpy


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


def unregister_properties():
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
