import bpy
import bmesh

from .color_attr import (
    get_target_corner_indices,
    paint_color_indices,
    resolve_color_attribute,
)
from .raycast import get_paint_targets, pick_color


class MESH_OT_pick_vertex_color(bpy.types.Operator):
    """Sample a vertex color from the mesh under the cursor. Hold the key to continuously sample while moving the mouse"""
    bl_idname = "mesh.pick_vertex_color"
    bl_label = "Eyedropper"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.report({'INFO'}, "Use the shortcut or click in the 3D Viewport to sample a vertex color")
        return {'CANCELLED'}

    def invoke(self, context, event):
        if context.window_manager is None:
            self.report({'ERROR'}, "No window manager available")
            return {'CANCELLED'}

        self._trigger_key = event.type
        self._sample(context, event.mouse_x, event.mouse_y)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._finish(context)
            return {'CANCELLED'}

        if event.type == self._trigger_key and event.value == 'RELEASE':
            self._finish(context)
            return {'FINISHED'}

        if event.type == 'MOUSEMOVE':
            self._sample(context, event.mouse_x, event.mouse_y)

        return {'RUNNING_MODAL'}

    def _finish(self, context):
        if context.workspace is not None:
            context.workspace.status_text_set(None)

    def _sample(self, context, mouse_x, mouse_y):
        result, _ = pick_color(context, mouse_x, mouse_y)
        if result is None:
            return
        _, color_value = result
        context.scene.vertex_color_value = color_value
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


# ---------------------------------------------------------------------------
# Helpers for the assign operator
# ---------------------------------------------------------------------------

def _has_selection_edit(context):
    vertex_sel, edge_sel, face_sel = context.tool_settings.mesh_select_mode
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        if vertex_sel and any(v.select for v in bm.verts):
            return True
        if edge_sel and any(e.select for e in bm.edges):
            return True
        if face_sel and any(f.select for f in bm.faces):
            return True
    return False


def _target_mesh_objects(context):
    if context.mode == 'EDIT_MESH':
        return [obj for obj in context.objects_in_mode_unique_data if obj.type == 'MESH']
    seen = set()
    objects = []
    for obj in context.selected_objects:
        if obj.type != 'MESH':
            continue
        ptr = obj.data.as_pointer()
        if ptr not in seen:
            seen.add(ptr)
            objects.append(obj)
    return objects


def _apply_to_targets(targets, color_value, was_in_edit):
    """Paint color onto pre-resolved (obj, loop_indices) pairs."""
    try:
        if was_in_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        total = 0
        for obj, loop_indices in targets:
            mesh = obj.data
            color_attr = resolve_color_attribute(mesh)
            idx = mesh.color_attributes.find(color_attr.name)
            mesh.color_attributes.active_color_index = idx
            mesh.color_attributes.render_color_index = idx
            paint_color_indices(color_attr, loop_indices, color_value)
            total += len(loop_indices)
            mesh.update()
        return total
    finally:
        if was_in_edit:
            bpy.ops.object.mode_set(mode='EDIT')


# ---------------------------------------------------------------------------
# Assign operator
# ---------------------------------------------------------------------------

class MESH_OT_assign_vertex_color(bpy.types.Operator):
    """Paint the active color onto selected geometry. With nothing selected, paints the face under the cursor instead"""
    bl_idname = "mesh.assign_vertex_color"
    bl_label = "Paint Selection"
    bl_options = {'REGISTER', 'UNDO'}

    mouse_x: bpy.props.IntProperty()
    mouse_y: bpy.props.IntProperty()

    def invoke(self, context, event):
        self.mouse_x = event.mouse_x
        self.mouse_y = event.mouse_y

        was_in_edit = context.mode == 'EDIT_MESH'
        use_raycast = (
            (not was_in_edit and not context.selected_objects)
            or (was_in_edit and not _has_selection_edit(context))
        )

        if use_raycast:
            self._paint_raycast(context)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

        return self.execute(context)

    def modal(self, context, event):
        if event.type == 'V' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type == 'ESC':
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self.mouse_x = event.mouse_x
            self.mouse_y = event.mouse_y
            self._paint_raycast(context)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        original_mode = context.mode
        was_in_edit = original_mode == 'EDIT_MESH'

        use_raycast = (
            (not was_in_edit and not context.selected_objects)
            or (was_in_edit and not _has_selection_edit(context))
        )
        if use_raycast:
            return self._execute_raycast(context, was_in_edit)

        return self._execute_selection(context, original_mode, was_in_edit)

    # -- internal ------------------------------------------------------------

    def _paint_raycast(self, context):
        was_in_edit = context.mode == 'EDIT_MESH'
        targets, _ = get_paint_targets(context, self.mouse_x, self.mouse_y)
        if targets is not None:
            _apply_to_targets(targets, context.scene.vertex_color_value, was_in_edit)

    def _execute_raycast(self, context, was_in_edit):
        if not self.mouse_x and not self.mouse_y:
            self.report({'WARNING'}, "Nothing selected to paint")
            return {'CANCELLED'}
        targets, error = get_paint_targets(context, self.mouse_x, self.mouse_y)
        if targets is None:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
        total = _apply_to_targets(targets, context.scene.vertex_color_value, was_in_edit)
        self.report({'INFO'}, f"Painted {total} corner(s) on '{targets[0][0].name}'")
        return {'FINISHED'}

    def _execute_selection(self, context, original_mode, was_in_edit):
        try:
            objects = _target_mesh_objects(context)
            if not objects:
                self.report({'WARNING'}, "No mesh objects selected")
                return {'CANCELLED'}

            color_value = context.scene.vertex_color_value
            apply_mode = context.scene.vertex_color_apply_mode

            if was_in_edit:
                work = []
                for obj in objects:
                    obj.update_from_editmode()
                    bm = bmesh.from_edit_mesh(obj.data)
                    bm.verts.ensure_lookup_table()
                    bm.edges.ensure_lookup_table()
                    bm.faces.ensure_lookup_table()
                    indices, _ = get_target_corner_indices(obj, obj.data, apply_mode, original_mode, bm)
                    work.append((obj, indices))
                bpy.ops.object.mode_set(mode='OBJECT')
            else:
                work = [(obj, None) for obj in objects]

            total = 0
            for obj, prebuilt in work:
                mesh = obj.data
                color_attr = resolve_color_attribute(mesh)
                idx = mesh.color_attributes.find(color_attr.name)
                mesh.color_attributes.active_color_index = idx
                mesh.color_attributes.render_color_index = idx

                indices = prebuilt if prebuilt is not None else get_target_corner_indices(
                    obj, mesh, apply_mode, original_mode,
                )[0]
                if not indices:
                    continue

                paint_color_indices(color_attr, indices, color_value)
                total += len(indices)
                mesh.update()

            if total == 0:
                self.report({'WARNING'}, "No geometry selected to paint")
            else:
                self.report({'INFO'}, f"Painted {total} corner(s) across {len(objects)} object(s)")

        finally:
            if was_in_edit:
                bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}
