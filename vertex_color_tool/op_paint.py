import bpy
import bmesh

from .color_attr import (
    get_target_corner_indices,
    paint_color_indices,
    resolve_color_attribute,
)
from . import palette_state
from .raycast import get_paint_targets


def _has_selection_edit(context):
    """Return True if anything is selected in the current edit-mode objects."""
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
    """Return the mesh objects that should be painted."""
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


def _resolve_selection_targets(context):
    """Build (obj, loop_indices) pairs from the current selection. Returns (targets, was_in_edit) or None."""
    original_mode = context.mode
    was_in_edit = original_mode == 'EDIT_MESH'

    objects = _target_mesh_objects(context)
    if not objects:
        return None, was_in_edit

    apply_mode = context.scene.vertex_color_apply_mode

    if was_in_edit:
        targets = []
        for obj in objects:
            obj.update_from_editmode()
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            indices, _ = get_target_corner_indices(obj, obj.data, apply_mode, original_mode, bm)
            if indices:
                targets.append((obj, indices))
    else:
        targets = []
        for obj in objects:
            indices = get_target_corner_indices(obj, obj.data, apply_mode, original_mode)[0]
            if indices:
                targets.append((obj, indices))

    return targets or None, was_in_edit


def _paint_targets(targets, color_value, was_in_edit):
    """Paint color onto (obj, loop_indices) pairs, handling mode switches and palette update."""
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
        if total > 0:
            palette_state.add_colors({palette_state.quantize(*color_value)})
        return total
    finally:
        if was_in_edit:
            bpy.ops.object.mode_set(mode='EDIT')


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
            self._bvh_cache = {}
            self._paint_raycast(context)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

        return self.execute(context)

    def modal(self, context, event):
        if event.type == 'V' and event.value == 'RELEASE':
            self._bvh_cache = None
            return {'FINISHED'}
        if event.type == 'ESC':
            self._bvh_cache = None
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self.mouse_x = event.mouse_x
            self.mouse_y = event.mouse_y
            self._paint_raycast(context)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        was_in_edit = context.mode == 'EDIT_MESH'
        use_raycast = (
            (not was_in_edit and not context.selected_objects)
            or (was_in_edit and not _has_selection_edit(context))
        )

        if use_raycast:
            if not self.mouse_x and not self.mouse_y:
                self.report({'WARNING'}, "Nothing selected to paint")
                return {'CANCELLED'}
            cache = getattr(self, '_bvh_cache', None)
            targets, error = get_paint_targets(context, self.mouse_x, self.mouse_y, bvh_cache=cache)
            if targets is None:
                self.report({'WARNING'}, error)
                return {'CANCELLED'}
            total = _paint_targets(targets, context.scene.vertex_color_value, was_in_edit)
            self.report({'INFO'}, f"Painted {total} corner(s) on '{targets[0][0].name}'")
            return {'FINISHED'}

        targets, was_in_edit = _resolve_selection_targets(context)
        if targets is None:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        color_value = context.scene.vertex_color_value
        total = _paint_targets(targets, color_value, was_in_edit)
        if total == 0:
            self.report({'WARNING'}, "No geometry selected to paint")
        else:
            self.report({'INFO'}, f"Painted {total} corner(s) across {len(targets)} object(s)")
        return {'FINISHED'}

    def _paint_raycast(self, context):
        was_in_edit = context.mode == 'EDIT_MESH'
        cache = getattr(self, '_bvh_cache', None)
        targets, _ = get_paint_targets(context, self.mouse_x, self.mouse_y, bvh_cache=cache)
        if targets is not None:
            _paint_targets(targets, context.scene.vertex_color_value, was_in_edit)
