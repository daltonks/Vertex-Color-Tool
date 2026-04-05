bl_info = {
    "name": "Vertex Color Tool",
    "blender": (5, 0, 0),
    "category": "Mesh",
    "version": (1, 3, 0),
    "author": "BobHop & Dalton Spillman",
    "description": "Apply RGBA color to selected vertices and faces"
}

from array import array

import bpy

DEFAULT_COLOR_ATTRIBUTE_NAMES = ("Color", "Attribute", "Col")
CANONICAL_COLOR_ATTRIBUTE_NAME = "Color"


def color_attr_sort_key(color_attr):
    return (
        color_attr.name != CANONICAL_COLOR_ATTRIBUTE_NAME,
        color_attr.name not in DEFAULT_COLOR_ATTRIBUTE_NAMES,
        color_attr.domain != 'CORNER',
        color_attr.data_type != 'FLOAT_COLOR',
        color_attr.name,
    )


def copy_point_attr_to_corner_attr(mesh, source_attr, target_attr):
    point_colors = array('f', [0.0]) * (len(source_attr.data) * 4)
    source_attr.data.foreach_get("color", point_colors)

    corner_colors = array('f', [0.0]) * (len(target_attr.data) * 4)
    for loop in mesh.loops:
        source_base = loop.vertex_index * 4
        target_base = loop.index * 4
        corner_colors[target_base] = point_colors[source_base]
        corner_colors[target_base + 1] = point_colors[source_base + 1]
        corner_colors[target_base + 2] = point_colors[source_base + 2]
        corner_colors[target_base + 3] = point_colors[source_base + 3]

    target_attr.data.foreach_set("color", corner_colors)


def copy_corner_attr_to_corner_attr(source_attr, target_attr):
    if len(source_attr.data) != len(target_attr.data):
        target_attr.data.foreach_set("color", [1.0, 1.0, 1.0, 1.0] * len(target_attr.data))
        return

    colors = array('f', [0.0]) * (len(source_attr.data) * 4)
    source_attr.data.foreach_get("color", colors)
    target_attr.data.foreach_set("color", colors)


def pick_source_color_attribute(mesh):
    active_attr = mesh.color_attributes.active_color
    if active_attr is not None:
        return active_attr

    render_index = mesh.color_attributes.render_color_index
    if render_index != -1:
        return mesh.color_attributes[render_index]

    color_attrs = list(mesh.color_attributes)
    if not color_attrs:
        return None

    color_attrs.sort(key=color_attr_sort_key)
    return color_attrs[0]


def resolve_color_attribute(mesh):
    """
    Normalize the mesh to exactly one Color attribute in CORNER/FLOAT_COLOR form.
    Reuses or migrates existing color data before removing conflicting attributes.
    """
    source_attr = pick_source_color_attribute(mesh)
    color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)

    if color_attr is not None and color_attr.domain == 'CORNER' and color_attr.data_type == 'FLOAT_COLOR':
        target_attr = color_attr
    else:
        if color_attr is not None:
            mesh.color_attributes.remove(color_attr)
        target_attr = mesh.color_attributes.new(
            name=CANONICAL_COLOR_ATTRIBUTE_NAME,
            type='FLOAT_COLOR',
            domain='CORNER',
        )
        target_attr.data.foreach_set("color", [1.0, 1.0, 1.0, 1.0] * len(target_attr.data))

        if source_attr is not None:
            if source_attr.domain == 'CORNER':
                copy_corner_attr_to_corner_attr(source_attr, target_attr)
            elif source_attr.domain == 'POINT':
                copy_point_attr_to_corner_attr(mesh, source_attr, target_attr)

    removable_names = [
        color_attr.name
        for color_attr in mesh.color_attributes
        if color_attr.name != CANONICAL_COLOR_ATTRIBUTE_NAME
    ]
    for attr_name in removable_names:
        color_attr = mesh.color_attributes.get(attr_name)
        if color_attr is not None:
            mesh.color_attributes.remove(color_attr)

    return target_attr


def get_target_corner_indices(obj, mesh, apply_mode, original_mode):
    """Returns a list of corner indices to be colored."""
    if original_mode == 'OBJECT':
        return list(range(len(mesh.loops))), "object"

    # In Edit Mode, we need to check selection
    selected_face_indices = [p.index for p in mesh.polygons if p.select]
    selected_vert_indices = {v.index for v in mesh.vertices if v.select}

    if apply_mode == 'FACE':
        if not selected_face_indices:
            return [], "faces"
        indices = []
        for f_idx in selected_face_indices:
            indices.extend(mesh.polygons[f_idx].loop_indices)
        return indices, "faces"

    # VERTEX mode: find all loops attached to selected vertices or faces
    if selected_face_indices:
        # Expand selection to all vertices of selected faces
        for f_idx in selected_face_indices:
            selected_vert_indices.update(mesh.polygons[f_idx].vertices)

    return sorted(
        {
            loop.index
            for loop in mesh.loops
            if loop.vertex_index in selected_vert_indices
        }
    ), "vertices"


def target_mesh_objects(context):
    if context.mode == 'EDIT_MESH':
        return [obj for obj in context.objects_in_mode_unique_data if obj.type == 'MESH']

    objects = []
    seen_meshes = set()
    for obj in context.selected_objects:
        if obj.type != 'MESH':
            continue
        mesh_ptr = obj.data.as_pointer()
        if mesh_ptr in seen_meshes:
            continue
        seen_meshes.add(mesh_ptr)
        objects.append(obj)
    return objects


def paint_color_indices(color_attr, indices, color_value):
    if len(indices) == len(color_attr.data):
        color_attr.data.foreach_set("color", array('f', color_value) * len(color_attr.data))
        return

    colors = array('f', [0.0]) * (len(color_attr.data) * 4)
    color_attr.data.foreach_get("color", colors)

    r, g, b, a = color_value
    for index in indices:
        base = index * 4
        colors[base] = r
        colors[base + 1] = g
        colors[base + 2] = b
        colors[base + 3] = a

    color_attr.data.foreach_set("color", colors)


class MESH_OT_pick_vertex_color(bpy.types.Operator):
    """Load the stored Color attribute from the current selection"""
    bl_idname = "mesh.pick_vertex_color"
    bl_label = "Use Selected Color"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = target_mesh_objects(context)
        if not objects:
            self.report({'ERROR'}, "No selected mesh objects")
            return {'CANCELLED'}

        original_mode = context.mode
        was_in_edit = original_mode == 'EDIT_MESH'

        try:
            if was_in_edit:
                bpy.ops.object.mode_set(mode='OBJECT')

            apply_mode = context.scene.vertex_color_apply_mode

            for obj in objects:
                mesh = obj.data
                color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
                if color_attr is None or color_attr.domain != 'CORNER':
                    continue

                indices, selection_source = get_target_corner_indices(
                    obj, mesh, apply_mode, original_mode
                )
                if not indices:
                    continue

                context.scene.vertex_color_value = color_attr.data[indices[0]].color
                self.report(
                    {'INFO'},
                    f"Loaded color from selected {selection_source} on '{obj.name}'"
                )
                return {'FINISHED'}

            self.report({'WARNING'}, "No painted Color data found on the current selection")
            return {'CANCELLED'}
        finally:
            if was_in_edit:
                bpy.ops.object.mode_set(mode='EDIT')


class MESH_OT_assign_vertex_color(bpy.types.Operator):
    """Apply an RGBA color to selected geometry"""
    bl_idname = "mesh.assign_vertex_color"
    bl_label = "Apply Color"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        original_mode = context.mode
        was_in_edit = original_mode == 'EDIT_MESH'

        try:
            objects = target_mesh_objects(context)
            if not objects:
                self.report({'ERROR'}, "No selected mesh objects")
                return {'CANCELLED'}

            if was_in_edit:
                bpy.ops.object.mode_set(mode='OBJECT')

            color_value = context.scene.vertex_color_value
            apply_mode = context.scene.vertex_color_apply_mode
            
            total_loops_affected = 0
            
            for obj in objects:
                mesh = obj.data
                color_attr = resolve_color_attribute(mesh)
                
                # Set as active for UI/Renderer
                idx = mesh.color_attributes.find(color_attr.name)
                mesh.color_attributes.active_color_index = idx
                mesh.color_attributes.render_color_index = idx

                indices, _ = get_target_corner_indices(obj, mesh, apply_mode, original_mode)
                
                if not indices:
                    continue

                paint_color_indices(color_attr, indices, color_value)
                total_loops_affected += len(indices)
                mesh.update()

            if total_loops_affected == 0:
                self.report({'WARNING'}, "No geometry selected to color")
            else:
                self.report({'INFO'}, f"Colored {total_loops_affected} loops across {len(objects)} object(s)")

        finally:
            # Always return to the mode the user started in
            if was_in_edit:
                bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}


class MESH_PT_vertex_color_panel(bpy.types.Panel):
    bl_label = "Vertex Color Tool"
    bl_idname = "MESH_PT_vertex_color"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        scn = context.scene

        row = layout.row(align=True)
        if scn.vertex_color_apply_mode == 'FACE':
            row.label(text="", icon='FACESEL')
        else:
            row.label(text="", icon='VERTEXSEL')
        row.prop(scn, "vertex_color_apply_mode", text="")
        
        row = layout.row()
        row.label(text="Color:")
        row.prop(scn, "vertex_color_value", text="")
        row.operator("mesh.pick_vertex_color", text="", icon='EYEDROPPER')

        layout.operator("mesh.assign_vertex_color", text="Apply to Selection", icon='CHECKMARK')


def register():
    bpy.utils.register_class(MESH_OT_pick_vertex_color)
    bpy.utils.register_class(MESH_OT_assign_vertex_color)
    bpy.utils.register_class(MESH_PT_vertex_color_panel)

    bpy.types.Scene.vertex_color_apply_mode = bpy.props.EnumProperty(
        name="Apply Mode",
        items=[
            ('VERTEX', "Vertex Style (Smooth)", "Color all loops sharing selected vertices"),
            ('FACE', "Face Corner (Sharp)", "Color only loops within selected faces"),
        ],
        default='VERTEX',
    )
    bpy.types.Scene.vertex_color_value = bpy.props.FloatVectorProperty(
        name="Vertex Color",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0)
    )


def unregister():
    bpy.utils.unregister_class(MESH_OT_pick_vertex_color)
    bpy.utils.unregister_class(MESH_OT_assign_vertex_color)
    bpy.utils.unregister_class(MESH_PT_vertex_color_panel)
    del bpy.types.Scene.vertex_color_apply_mode
    del bpy.types.Scene.vertex_color_value


if __name__ == "__main__":
    register()
