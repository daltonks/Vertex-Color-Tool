import bpy
from array import array

from mathutils import Vector
from bpy_extras import view3d_utils

from .color_attr import resolve_color_attribute
from .paint import get_target_corner_indices, paint_gradient_indices
from .raycast import find_view3d_region, invalidate_color_cache


def _resolve_gradient_targets(context):
    """Build (obj, loop_indices) pairs from the current selection.

    Returns (targets, was_in_edit) or (None, was_in_edit) when nothing
    is selected.  Unlike the paint operator this never falls back to
    ray-cast — a gradient always needs a pre-existing selection.
    """
    original_mode = context.mode
    was_in_edit = original_mode == 'EDIT_MESH'

    if was_in_edit:
        objects = [o for o in context.objects_in_mode_unique_data if o.type == 'MESH']
    else:
        seen = set()
        objects = []
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            ptr = obj.data.as_pointer()
            if ptr not in seen:
                seen.add(ptr)
                objects.append(obj)

    if not objects:
        return None, was_in_edit

    if was_in_edit:
        import bmesh
        targets = []
        for obj in objects:
            obj.update_from_editmode()
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            indices, _ = get_target_corner_indices(obj, obj.data, original_mode, bm)
            if indices:
                targets.append((obj, indices))
    else:
        targets = []
        for obj in objects:
            indices = get_target_corner_indices(obj, obj.data, original_mode)[0]
            if indices:
                targets.append((obj, indices))

    return targets or None, was_in_edit


def _ref_center(targets):
    """World-space center of all target objects' bounding boxes."""
    total = Vector((0.0, 0.0, 0.0))
    count = 0
    for obj, _ in targets:
        for corner in obj.bound_box:
            total += obj.matrix_world @ Vector(corner)
            count += 1
    if count == 0:
        return Vector((0.0, 0.0, 0.0))
    return total / count


class MESH_OT_vertex_color_gradient(bpy.types.Operator):
    """Paint a linear gradient between two colors across selected geometry.\n"""  \
    """Click to set start, move mouse for direction, click again to confirm"""
    bl_idname = "mesh.vertex_color_gradient"
    bl_label = "Paint Gradient"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        targets, was_in_edit = _resolve_gradient_targets(context)
        if targets is None:
            self.report({'WARNING'}, "No mesh geometry selected")
            return {'CANCELLED'}

        self._was_in_edit = was_in_edit

        if was_in_edit:
            bpy.ops.object.mode_set(mode='OBJECT')

        # Resolve colour attributes and snapshot current colours.
        self._targets = []
        self._original_colors = {}
        for obj, indices in targets:
            mesh = obj.data
            color_attr = resolve_color_attribute(mesh)
            idx = mesh.color_attributes.find(color_attr.name)
            mesh.color_attributes.active_color_index = idx
            mesh.color_attributes.render_color_index = idx

            buf = array('f', [0.0]) * (len(color_attr.data) * 4)
            color_attr.data.foreach_get("color", buf)
            self._original_colors[obj.as_pointer()] = array('f', buf)
            self._targets.append((obj, indices))

        area, region, region_3d = find_view3d_region(
            context, event.mouse_x, event.mouse_y,
        )
        if region is None:
            self._restore_and_finish(context, cancel=True)
            self.report({'WARNING'}, "Cursor is not inside a 3D Viewport")
            return {'CANCELLED'}

        self._region = region
        self._region_3d = region_3d
        self._depth_ref = _ref_center(self._targets)
        self._start_2d = None

        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(
            "Click to set gradient start · ESC to cancel",
        )
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------ modal
    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._restore_and_finish(context, cancel=True)
            return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            coord = Vector((
                event.mouse_x - self._region.x,
                event.mouse_y - self._region.y,
            ))
            if self._start_2d is None:
                self._start_2d = coord
                context.workspace.status_text_set(
                    "Move to set direction · Click to confirm · ESC to cancel",
                )
                return {'RUNNING_MODAL'}

            self._apply_gradient(context, coord)
            self._restore_and_finish(context, cancel=False)
            return {'FINISHED'}

        if event.type == 'MOUSEMOVE' and self._start_2d is not None:
            coord = Vector((
                event.mouse_x - self._region.x,
                event.mouse_y - self._region.y,
            ))
            self._apply_gradient(context, coord)

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------- internals
    def _apply_gradient(self, context, end_2d):
        region = self._region
        r3d = self._region_3d
        ref = self._depth_ref

        start_world = view3d_utils.region_2d_to_location_3d(
            region, r3d, self._start_2d, ref,
        )
        end_world = view3d_utils.region_2d_to_location_3d(
            region, r3d, end_2d, ref,
        )

        color_a = tuple(context.scene.vertex_color_value)
        color_b = tuple(context.scene.vertex_color_gradient_end)

        for obj, indices in self._targets:
            mesh = obj.data
            color_attr = mesh.color_attributes.get("Color")
            if color_attr is None:
                continue

            original = self._original_colors.get(obj.as_pointer())
            if original is not None:
                color_attr.data.foreach_set("color", original)

            paint_gradient_indices(
                color_attr, indices, mesh, obj.matrix_world,
                start_world, end_world, color_a, color_b,
            )
            mesh.update()

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _restore_and_finish(self, context, *, cancel):
        if cancel:
            for obj, _ in self._targets:
                mesh = obj.data
                color_attr = mesh.color_attributes.get("Color")
                if color_attr is None:
                    continue
                original = self._original_colors.get(obj.as_pointer())
                if original is not None:
                    color_attr.data.foreach_set("color", original)
                    mesh.update()
        else:
            invalidate_color_cache()

        context.workspace.status_text_set(None)
        if self._was_in_edit:
            bpy.ops.object.mode_set(mode='EDIT')

        self._original_colors = None
        self._targets = None
