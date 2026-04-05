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


def resolve_color_attribute(mesh, requested_name):
    """
    Finds or creates a compatible FLOAT_COLOR CORNER attribute.
    Ensures existing non-compatible attributes are not overwritten/deleted.
    """
    attribute_name = requested_name or DEFAULT_COLOR_ATTRIBUTE_NAMES[0]
    color_attr = mesh.color_attributes.get(attribute_name)

    # 1. If it exists and matches our needs, use it
    if color_attr is not None and color_attr.domain == 'CORNER' and color_attr.data_type == 'FLOAT_COLOR':
        return color_attr

    # 2. If name is taken by a different domain/type, find a fallback or unique name
    if color_attr is not None:
        # Check fallbacks
        for name in DEFAULT_COLOR_ATTRIBUTE_NAMES:
            fallback = mesh.color_attributes.get(name)
            if fallback and fallback.domain == 'CORNER' and fallback.data_type == 'FLOAT_COLOR':
                return fallback

        # If still blocked, create a unique name to avoid deleting user data.
        suffix = 1
        base_name = f"{attribute_name}_VC"
        attribute_name = base_name
        while mesh.color_attributes.get(attribute_name) is not None:
            suffix += 1
            attribute_name = f"{base_name}_{suffix}"

    # 3. Create new attribute
    new_attr = mesh.color_attributes.new(name=attribute_name, type='FLOAT_COLOR', domain='CORNER')
    
    # Initialize with white
    new_attr.data.foreach_set("color", [1.0, 1.0, 1.0, 1.0] * len(new_attr.data))
    
    return new_attr


def get_target_loop_indices(obj, mesh, apply_mode, original_mode):
    """Returns a list of loop indices to be colored."""
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

    return [l.index for l in mesh.loops if l.vertex_index in selected_vert_indices], "vertices"


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
            attr_target_name = context.scene.vertex_color_attribute_name.strip()
            apply_mode = context.scene.vertex_color_apply_mode
            
            total_loops_affected = 0
            
            for obj in objects:
                mesh = obj.data
                color_attr = resolve_color_attribute(mesh, attr_target_name)
                
                # Set as active for UI/Renderer
                idx = mesh.color_attributes.find(color_attr.name)
                mesh.color_attributes.active_color_index = idx
                mesh.color_attributes.render_color_index = idx

                indices, _ = get_target_loop_indices(obj, mesh, apply_mode, original_mode)
                
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

        col = layout.column(align=True)
        col.prop(scn, "vertex_color_apply_mode", text="Mode")
        col.prop(scn, "vertex_color_attribute_name", text="Name")

        layout.separator()
        
        row = layout.row()
        row.label(text="Color:")
        row.prop(scn, "vertex_color_value", text="")

        box = layout.box()
        if scn.vertex_color_apply_mode == 'FACE':
            box.label(text="Mode: Face Corner (Sharp)", icon='FACESEL')
        else:
            box.label(text="Mode: Vertex Style (Smooth)", icon='VERTEXSEL')

        layout.operator("mesh.assign_vertex_color", text="Apply to Selection", icon='CHECKMARK')


def register():
    bpy.utils.register_class(MESH_OT_assign_vertex_color)
    bpy.utils.register_class(MESH_PT_vertex_color_panel)

    bpy.types.Scene.vertex_color_apply_mode = bpy.props.EnumProperty(
        name="Apply Mode",
        items=[
            ('VERTEX', "Vertex Style", "Color all loops sharing selected vertices"),
            ('FACE', "Face Corner", "Color only loops within selected faces"),
        ],
        default='VERTEX',
    )
    bpy.types.Scene.vertex_color_attribute_name = bpy.props.StringProperty(
        name="Attribute Name",
        default="Color",
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
    bpy.utils.unregister_class(MESH_OT_assign_vertex_color)
    bpy.utils.unregister_class(MESH_PT_vertex_color_panel)
    del bpy.types.Scene.vertex_color_apply_mode
    del bpy.types.Scene.vertex_color_attribute_name
    del bpy.types.Scene.vertex_color_value


if __name__ == "__main__":
    register()
