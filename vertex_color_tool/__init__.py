bl_info = {
    "name": "Vertex Color Tool",
    "blender": (4, 5, 3),
    "category": "Mesh",
    "version": (1, 2, 0),
    "author": "BobHop",
    "description": "Apply RGBA color to face corners with corner or vertex-style application"
}

import bpy

DEFAULT_COLOR_ATTRIBUTE_NAMES = ("Color", "Attribute")


def initialize_color_data(color_attr, color_value=(1.0, 1.0, 1.0, 1.0)):
    for item in color_attr.data:
        item.color = color_value


def resolve_color_attribute(mesh, requested_name):
    attribute_name = requested_name or DEFAULT_COLOR_ATTRIBUTE_NAMES[0]

    color_attr = mesh.color_attributes.get(attribute_name)
    if color_attr is not None and color_attr.domain == 'CORNER':
        return color_attr

    if attribute_name in DEFAULT_COLOR_ATTRIBUTE_NAMES:
        for name in DEFAULT_COLOR_ATTRIBUTE_NAMES:
            fallback_attr = mesh.color_attributes.get(name)
            if fallback_attr is not None and fallback_attr.domain == 'CORNER':
                return fallback_attr

    if color_attr is not None:
        mesh.color_attributes.remove(color_attr)

    mesh.color_attributes.new(name=attribute_name, type='FLOAT_COLOR', domain='CORNER')
    color_attr = mesh.color_attributes[attribute_name]
    initialize_color_data(color_attr)
    return color_attr


def activate_color_attribute(mesh, color_attr):
    color_index = mesh.color_attributes.find(color_attr.name)
    if color_index != -1:
        mesh.color_attributes.active_color_index = color_index
        mesh.color_attributes.render_color_index = color_index


def selected_loop_indices(obj, mesh, apply_mode, mode):
    if mode == 'OBJECT':
        if obj.select_get():
            return list(range(len(mesh.loops))), "object"
        return [], "object"

    selected_face_indices = [poly.index for poly in mesh.polygons if poly.select]
    selected_vertex_indices = {v.index for v in mesh.vertices if v.select}

    if apply_mode == 'FACE':
        if selected_face_indices:
            return [
                loop_index
                for face_index in selected_face_indices
                for loop_index in mesh.polygons[face_index].loop_indices
            ], "faces"
        return [], "faces"

    if selected_face_indices:
        vertex_indices = {
            vertex_index
            for face_index in selected_face_indices
            for vertex_index in mesh.polygons[face_index].vertices
        }
        return [
            loop.index
            for loop in mesh.loops
            if loop.vertex_index in vertex_indices
        ], "faces"

    return [
        loop.index
        for loop in mesh.loops
        if loop.vertex_index in selected_vertex_indices
    ], "vertices"


def target_mesh_objects(context):
    if context.mode == 'EDIT_MESH':
        return [obj for obj in context.objects_in_mode if obj.type == 'MESH']
    return [obj for obj in context.selected_objects if obj.type == 'MESH']


class MESH_OT_assign_vertex_color(bpy.types.Operator):
    """Apply an RGBA color to selected geometry"""
    bl_idname = "mesh.assign_vertex_color"
    bl_label = "Apply Color"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = target_mesh_objects(context)
        if not objects:
            self.report({'ERROR'}, "No selected mesh objects")
            return {'CANCELLED'}

        color_value = context.scene.vertex_color_value
        attribute_name = context.scene.vertex_color_attribute_name.strip() or "Color"
        apply_mode = context.scene.vertex_color_apply_mode

        original_mode = context.mode
        was_in_edit = original_mode == 'EDIT_MESH'
        if was_in_edit:
            bpy.ops.object.mode_set(mode='OBJECT')

        total_loops = 0
        selection_source = None
        attribute_names = set()

        for obj in objects:
            mesh = obj.data
            color_attr = resolve_color_attribute(mesh, attribute_name)
            activate_color_attribute(mesh, color_attr)

            loop_indices, obj_selection_source = selected_loop_indices(
                obj, mesh, apply_mode, original_mode
            )
            if not loop_indices:
                continue

            for idx in loop_indices:
                color_attr.data[idx].color = color_value

            total_loops += len(loop_indices)
            selection_source = obj_selection_source
            attribute_names.add(color_attr.name)

        if not total_loops:
            self.report({'WARNING'}, "No selected object, vertices, or faces")
            if was_in_edit:
                bpy.ops.object.mode_set(mode='EDIT')
            return {'CANCELLED'}

        attribute_label = ", ".join(sorted(attribute_names))
        self.report(
            {'INFO'},
            (
                f"Applied corner color to {total_loops} loops on {len(objects)} object(s) "
                f"from selected {selection_source} using '{attribute_label}'"
            )
        )

        if was_in_edit:
            bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}


class MESH_PT_vertex_color_panel(bpy.types.Panel):
    """This panel applies face-corner color"""
    bl_label = "Vertex Color"
    bl_idname = "MESH_PT_vertex_color"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout

        layout.prop(context.scene, "vertex_color_apply_mode", text="Mode")
        layout.prop(context.scene, "vertex_color_attribute_name", text="Attribute")

        row = layout.row()
        row.label(text="Color:")
        row.prop(context.scene, "vertex_color_value", text="")

        help_box = layout.box()
        if context.scene.vertex_color_apply_mode == 'FACE':
            help_box.label(text="Colors only the selected face corners.", icon='FACESEL')
            help_box.label(text="Use this for sharp edge breaks.", icon='MOD_EDGESPLIT')
        else:
            help_box.label(text="Colors all loops using the selected vertices.", icon='VERTEXSEL')
            help_box.label(text="This behaves like shared vertex color.", icon='MESH_DATA')

        layout.operator("mesh.assign_vertex_color", text="Apply Color", icon='CHECKMARK')


def register():
    bpy.utils.register_class(MESH_OT_assign_vertex_color)
    bpy.utils.register_class(MESH_PT_vertex_color_panel)

    bpy.types.Scene.vertex_color_apply_mode = bpy.props.EnumProperty(
        name="Apply Mode",
        description="How selection maps onto the face-corner color layer",
        items=[
            ('VERTEX', "Vertex Style", "Color all loops using the selected vertices"),
            ('FACE', "Face Corner", "Color only the selected face corners"),
        ],
        default='VERTEX',
    )
    bpy.types.Scene.vertex_color_attribute_name = bpy.props.StringProperty(
        name="Attribute Name",
        description="Name of the face-corner color attribute to create or edit",
        default="Color",
    )
    bpy.types.Scene.vertex_color_value = bpy.props.FloatVectorProperty(
        name="Vertex Color",
        description="RGBA color to apply to the selected geometry",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0)
    )


def unregister():
    bpy.utils.unregister_class(MESH_OT_assign_vertex_color)
    bpy.utils.unregister_class(MESH_PT_vertex_color_panel)

    del bpy.types.Scene.vertex_color_apply_mode
    del bpy.types.Scene.vertex_color_attribute_name
    del bpy.types.Scene.vertex_color_value


if __name__ == "__main__":
    register()
