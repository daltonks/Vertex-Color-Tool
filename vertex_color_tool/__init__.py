bl_info = {
    "name": "Vertex Color Tool",
    "blender": (5, 0, 0),
    "category": "Mesh",
    "version": (1, 4, 0),
    "author": "BobHop & Dalton Spillman",
    "description": "Paint vertex colors on meshes in edit and object mode, with eyedropper sampling, scene palette, and per-vertex or per-face application"
}

from array import array
import colorsys
import sys

import bpy
import bmesh
from bpy_extras import view3d_utils
from mathutils.bvhtree import BVHTree

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


def get_target_corner_indices(obj, mesh, apply_mode, original_mode, bm=None):
    """Returns a list of corner indices to be colored."""
    if original_mode == 'OBJECT':
        return list(range(len(mesh.loops))), "object"

    # Use BMesh when available — it's the authoritative selection source in edit mode
    if bm is not None:
        if apply_mode == 'FACE':
            indices = []
            for f in bm.faces:
                if f.select:
                    indices.extend(mesh.polygons[f.index].loop_indices)
            if indices:
                return indices, "faces"
            # No fully-selected faces (e.g. vertex/edge select mode with partial selection).
            # Fall back to vertex-based painting so individual selections still work.

        # VERTEX mode (and FACE fallback): collect verts from any selected element
        sel_verts = set()
        for v in bm.verts:
            if v.select:
                sel_verts.add(v.index)
        for e in bm.edges:
            if e.select:
                sel_verts.update(v.index for v in e.verts)
        for f in bm.faces:
            if f.select:
                sel_verts.update(v.index for v in f.verts)
        return sorted(l.index for l in mesh.loops if l.vertex_index in sel_verts), "vertices"

    # Fallback: read from mesh data (object mode)
    if apply_mode == 'FACE':
        selected_face_indices = [p.index for p in mesh.polygons if p.select]
        if not selected_face_indices:
            return [], "faces"
        indices = []
        for f_idx in selected_face_indices:
            indices.extend(mesh.polygons[f_idx].loop_indices)
        return indices, "faces"

    selected_vert_indices = {v.index for v in mesh.vertices if v.select}
    selected_face_indices = [p.index for p in mesh.polygons if p.select]
    for f_idx in selected_face_indices:
        selected_vert_indices.update(mesh.polygons[f_idx].vertices)
    return sorted(l.index for l in mesh.loops if l.vertex_index in selected_vert_indices), "vertices"


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


def find_view3d_window_region(context, mouse_x, mouse_y):
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type != 'WINDOW':
                continue
            if region.x <= mouse_x < region.x + region.width and region.y <= mouse_y < region.y + region.height:
                return area, region, area.spaces.active.region_3d
    return None, None, None


def _bvh_raycast(obj, ray_origin, ray_direction, mesh=None):
    """Ray cast against an object using a BVH tree. Returns (dist_sq, face_index, location_local) or None."""
    if mesh is None:
        mesh = obj.data
    if not mesh.polygons or not mesh.vertices:
        return None
    matrix_world = obj.matrix_world
    matrix_inv = matrix_world.inverted()
    origin_local = matrix_inv @ ray_origin
    dir_local = (matrix_inv.to_3x3() @ ray_direction).normalized()
    bvh = BVHTree.FromPolygons(
        [v.co.copy() for v in mesh.vertices],
        [tuple(p.vertices) for p in mesh.polygons],
    )
    location_local, _, face_index, _ = bvh.ray_cast(origin_local, dir_local)
    if location_local is None or face_index is None or face_index < 0:
        return None
    dist_sq = (matrix_world @ location_local - ray_origin).length_squared
    return dist_sq, face_index, location_local


def _sample_closest_loop_color(mesh, color_attr, face_index, hit_local):
    """Return the color of the loop whose vertex is closest to hit_local."""
    polygon = mesh.polygons[face_index]
    loop_indices = list(polygon.loop_indices)
    if not loop_indices:
        return None

    colors = array('f', [0.0]) * (len(color_attr.data) * 4)
    color_attr.data.foreach_get("color", colors)

    best_li = min(
        loop_indices,
        key=lambda li: (mesh.vertices[mesh.loops[li].vertex_index].co - hit_local).length_squared
    )
    base = best_li * 4
    if base + 3 >= len(colors):
        return None
    return (colors[base], colors[base + 1], colors[base + 2], colors[base + 3])


def _sample_closest_loop_color_bmesh(obj, face_index, hit_local):
    """Sample color from BMesh directly (required in edit mode, where obj.data color data is stale)."""
    bm = bmesh.from_edit_mesh(obj.data)
    color_layer = bm.loops.layers.float_color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if color_layer is None:
        color_layer = bm.loops.layers.color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if color_layer is None:
        return None
    bm.faces.ensure_lookup_table()
    if face_index >= len(bm.faces):
        return None
    face = bm.faces[face_index]
    best_loop = min(face.loops, key=lambda l: (l.vert.co - hit_local).length_squared)
    c = best_loop[color_layer]
    return (c[0], c[1], c[2], c[3])



def pick_color_with_raycast(context, mouse_x, mouse_y):
    area, region, region_3d = find_view3d_window_region(context, mouse_x, mouse_y)
    if region is None or region_3d is None:
        return None, "Cursor is not inside a 3D Viewport"

    coord = (mouse_x - region.x, mouse_y - region.y)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, coord)
    ray_direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, coord)

    depsgraph = context.evaluated_depsgraph_get()
    best_hit = None  # (dist_sq, obj, mesh, face_index, location_local, from_eval)

    # Edit-mode objects: scene.ray_cast skips them, so use BVH
    if context.mode == 'EDIT_MESH':
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            obj.update_from_editmode()
            # Try the base mesh (accurate BMesh color sampling)
            hit = _bvh_raycast(obj, ray_origin, ray_direction)
            if hit is not None:
                dist_sq, face_index, location_local = hit
                if best_hit is None or dist_sq < best_hit[0]:
                    best_hit = (dist_sq, obj, obj.data, face_index, location_local, False)

            # Also try the evaluated mesh (modifier-generated geometry like mirror/array)
            eval_obj = obj.evaluated_get(depsgraph)
            eval_mesh = eval_obj.to_mesh()
            if eval_mesh is not None and len(eval_mesh.polygons) > len(obj.data.polygons):
                hit = _bvh_raycast(obj, ray_origin, ray_direction, mesh=eval_mesh)
                if hit is not None:
                    dist_sq, face_index, location_local = hit
                    if best_hit is None or dist_sq < best_hit[0]:
                        best_hit = (dist_sq, obj, eval_mesh, face_index, location_local, True)

    # All other visible objects
    result, location, _, face_index, hit_obj, matrix = context.scene.ray_cast(depsgraph, ray_origin, ray_direction)
    if result and hit_obj and hit_obj.type == 'MESH' and hit_obj.mode != 'EDIT':
        dist_sq = (location - ray_origin).length_squared
        if best_hit is None or dist_sq < best_hit[0]:
            location_local = matrix.inverted() @ location
            eval_obj = hit_obj.evaluated_get(depsgraph)
            best_hit = (dist_sq, hit_obj, eval_obj.data, face_index, location_local, False)

    if best_hit is not None:
        _, obj, mesh, face_index, location_local, from_eval = best_hit
        if obj.mode == 'EDIT' and not from_eval:
            color = _sample_closest_loop_color_bmesh(obj, face_index, location_local)
        else:
            color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
            color = None
            if color_attr is not None and color_attr.domain == 'CORNER' and len(color_attr.data) > 0:
                color = _sample_closest_loop_color(mesh, color_attr, face_index, location_local)
        if color is not None:
            return (obj, color), None
        return None, f"'{obj.name}' has no vertex colors to sample"

    return None, "No painted mesh under cursor"


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
        self.sample_at_cursor(context, event.mouse_x, event.mouse_y)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.finish(context)
            return {'CANCELLED'}

        if event.type == self._trigger_key and event.value == 'RELEASE':
            self.finish(context)
            return {'FINISHED'}

        if event.type == 'MOUSEMOVE':
            self.sample_at_cursor(context, event.mouse_x, event.mouse_y)

        return {'RUNNING_MODAL'}

    def finish(self, context):
        if context.workspace is not None:
            context.workspace.status_text_set(None)

    def sample_at_cursor(self, context, mouse_x, mouse_y):
        result, error_message = pick_color_with_raycast(context, mouse_x, mouse_y)
        if result is None:
            return

        source_obj, color_value = result
        context.scene.vertex_color_value = color_value
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


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


def _raycast_get_paint_targets(context, mouse_x, mouse_y):
    """
    Return [(obj, loop_indices)] for the geometry under the cursor, or (None, error_str).
    Requires a face hit — no nearest-element fallback.
    """
    area, region, region_3d = find_view3d_window_region(context, mouse_x, mouse_y)
    if region is None or region_3d is None:
        return None, "Cursor is not inside a 3D Viewport"

    coord = (mouse_x - region.x, mouse_y - region.y)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, coord)
    ray_direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, coord)

    if context.mode == 'EDIT_MESH':
        # Find the nearest face hit across all edit-mode objects
        best = None  # (dist_sq, obj, face_index, location_local)
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            obj.update_from_editmode()
            hit = _bvh_raycast(obj, ray_origin, ray_direction)
            if hit and (best is None or hit[0] < best[0]):
                best = (hit[0], obj, hit[1], hit[2])

        if best is None:
            return None, "No mesh face under cursor"

        _, obj, face_index, location_local = best
        mesh = obj.data
        polygon = mesh.polygons[face_index]
        vertex_sel, edge_sel, face_sel = context.tool_settings.mesh_select_mode

        if face_sel:
            loop_indices = list(polygon.loop_indices)

        elif vertex_sel:
            nearest_vi = min(
                polygon.vertices,
                key=lambda vi: (mesh.vertices[vi].co - location_local).length_squared,
            )
            loop_indices = [l.index for l in mesh.loops if l.vertex_index == nearest_vi]

        else:  # edge select
            verts = list(polygon.vertices)
            pairs = [(verts[i], verts[(i + 1) % len(verts)]) for i in range(len(verts))]
            v0, v1 = min(
                pairs,
                key=lambda p: (
                    (mesh.vertices[p[0]].co + mesh.vertices[p[1]].co) / 2 - location_local
                ).length_squared,
            )
            edge_vis = {v0, v1}
            loop_indices = [l.index for l in mesh.loops if l.vertex_index in edge_vis]

        return [(obj, loop_indices)], None

    else:  # Object mode
        depsgraph = context.evaluated_depsgraph_get()
        result, _, _, _, hit_obj, _ = context.scene.ray_cast(depsgraph, ray_origin, ray_direction)
        if not result or hit_obj is None or hit_obj.type != 'MESH':
            return None, "No mesh face under cursor"
        return [(hit_obj, list(range(len(hit_obj.data.loops))))], None


class MESH_OT_assign_vertex_color(bpy.types.Operator):
    """Paint the active color onto selected geometry. With nothing selected, paints the face under the cursor instead"""
    bl_idname = "mesh.assign_vertex_color"
    bl_label = "Paint Selection"
    bl_options = {'REGISTER', 'UNDO'}

    mouse_x: bpy.props.IntProperty()
    mouse_y: bpy.props.IntProperty()

    def _paint_raycast(self, context):
        """Paint at current mouse position via raycast, respecting current mode."""
        was_in_edit = context.mode == 'EDIT_MESH'
        targets, _ = _raycast_get_paint_targets(context, self.mouse_x, self.mouse_y)
        if targets is None:
            return
        try:
            if was_in_edit:
                bpy.ops.object.mode_set(mode='OBJECT')
            color_value = context.scene.vertex_color_value
            for obj, loop_indices in targets:
                mesh = obj.data
                color_attr = resolve_color_attribute(mesh)
                idx = mesh.color_attributes.find(color_attr.name)
                mesh.color_attributes.active_color_index = idx
                mesh.color_attributes.render_color_index = idx
                paint_color_indices(color_attr, loop_indices, color_value)
                mesh.update()
        finally:
            if was_in_edit:
                bpy.ops.object.mode_set(mode='EDIT')

    def invoke(self, context, event):
        self.mouse_x = event.mouse_x
        self.mouse_y = event.mouse_y

        original_mode = context.mode
        was_in_edit = original_mode == 'EDIT_MESH'

        use_raycast = (
            (original_mode == 'OBJECT' and not context.selected_objects) or
            (was_in_edit and not _has_selection_edit(context))
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

        # Raycast-based paint when nothing is selected
        use_raycast = (
            (original_mode == 'OBJECT' and not context.selected_objects) or
            (was_in_edit and not _has_selection_edit(context))
        )
        if use_raycast:
            if not self.mouse_x and not self.mouse_y:
                self.report({'WARNING'}, "Nothing selected to paint")
                return {'CANCELLED'}
            targets, error = _raycast_get_paint_targets(context, self.mouse_x, self.mouse_y)
            if targets is None:
                self.report({'WARNING'}, error)
                return {'CANCELLED'}
            try:
                if was_in_edit:
                    bpy.ops.object.mode_set(mode='OBJECT')
                color_value = context.scene.vertex_color_value
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
                self.report({'INFO'}, f"Painted {total} corner(s) on '{targets[0][0].name}'")
            finally:
                if was_in_edit:
                    bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}

        try:
            objects = target_mesh_objects(context)
            if not objects:
                self.report({'WARNING'}, "No mesh objects selected")
                return {'CANCELLED'}

            color_value = context.scene.vertex_color_value
            apply_mode = context.scene.vertex_color_apply_mode

            # Extract loop indices from BMesh before leaving edit mode
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

            total_loops_affected = 0

            for obj, prebuilt in work:
                mesh = obj.data
                color_attr = resolve_color_attribute(mesh)

                # Set as active for UI/Renderer
                idx = mesh.color_attributes.find(color_attr.name)
                mesh.color_attributes.active_color_index = idx
                mesh.color_attributes.render_color_index = idx

                indices = prebuilt if prebuilt is not None else get_target_corner_indices(obj, mesh, apply_mode, original_mode)[0]

                if not indices:
                    continue

                paint_color_indices(color_attr, indices, color_value)
                total_loops_affected += len(indices)
                mesh.update()

            if total_loops_affected == 0:
                self.report({'WARNING'}, "No geometry selected to paint")
            else:
                self.report({'INFO'}, f"Painted {total_loops_affected} corner(s) across {len(objects)} object(s)")

        finally:
            # Always return to the mode the user started in
            if was_in_edit:
                bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}


class VertexColorPaletteEntry(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(subtype='COLOR', size=4, min=0.0, max=1.0)


# Global ref-count: color -> number of meshes using it
# Per-mesh snapshot: mesh name -> set of colors last seen in that mesh
_color_refcounts = {}
_mesh_colors = {}
_palette_initialized = False


def _quantize_color(r, g, b, a):
    return (round(r, 2), round(g, 2), round(b, 2), round(a, 2))


def _collect_mesh_colors(mesh):
    """Return the set of quantized colors in a mesh's Color attribute."""
    color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if color_attr is None or color_attr.domain != 'CORNER' or len(color_attr.data) == 0:
        return set()
    n = len(color_attr.data)
    colors = array('f', [0.0]) * (n * 4)
    color_attr.data.foreach_get("color", colors)
    q = _quantize_color
    return {q(colors[i], colors[i+1], colors[i+2], colors[i+3]) for i in range(0, n * 4, 4)}


def _collect_bmesh_colors(mesh):
    """Return the set of quantized colors from BMesh (for edit-mode meshes)."""
    bm = bmesh.from_edit_mesh(mesh)
    color_layer = bm.loops.layers.float_color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if color_layer is None:
        color_layer = bm.loops.layers.color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if color_layer is None:
        return set()
    q = _quantize_color
    return {q(c[0], c[1], c[2], c[3])
            for face in bm.faces for loop in face.loops for c in (loop[color_layer],)}


def _write_palette(wm):
    """Write live colors to the UI CollectionProperty, sorted by hue."""
    palette = wm.vertex_color_palette
    sorted_colors = sorted(
        _color_refcounts,
        key=lambda c: colorsys.rgb_to_hsv(c[0], c[1], c[2]),
    )
    palette.clear()
    for color in sorted_colors:
        entry = palette.add()
        entry.color = color


def _update_mesh(mesh_name, new_colors):
    """Update ref-counts for a single mesh. Returns True if the palette changed."""
    old_colors = _mesh_colors.get(mesh_name, set())
    if len(old_colors) == len(new_colors) and old_colors == new_colors:
        return False

    added = new_colors - old_colors
    removed = old_colors - new_colors

    changed = False
    for color in removed:
        _color_refcounts[color] -= 1
        if _color_refcounts[color] <= 0:
            del _color_refcounts[color]
            changed = True

    for color in added:
        if color not in _color_refcounts:
            changed = True
        _color_refcounts[color] = _color_refcounts.get(color, 0) + 1

    _mesh_colors[mesh_name] = new_colors
    return changed


def _rebuild_palette(scene):
    """Full scene scan — used when opening the palette or on file load."""
    wm = bpy.context.window_manager
    if not hasattr(wm, 'vertex_color_palette'):
        return
    _color_refcounts.clear()
    _mesh_colors.clear()
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        if obj.mode == 'EDIT':
            colors = _collect_bmesh_colors(obj.data)
        else:
            colors = _collect_mesh_colors(obj.data)
        _mesh_colors[obj.data.name] = colors
        for color in colors:
            _color_refcounts[color] = _color_refcounts.get(color, 0) + 1
    _write_palette(wm)


def _on_depsgraph_update(scene, depsgraph):
    global _palette_initialized
    wm = bpy.context.window_manager
    if not hasattr(wm, 'vertex_color_palette'):
        return
    if not _palette_initialized:
        _palette_initialized = True
        _rebuild_palette(scene)
        return
    changed_mesh = None
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Mesh) and update.is_updated_geometry:
            changed_mesh = update.id
            break

    if changed_mesh is not None:
        # In edit mode, mesh color data is stale — read from BMesh instead
        is_edit = (bpy.context.mode == 'EDIT_MESH'
                   and any(obj.data == changed_mesh for obj in bpy.context.objects_in_mode_unique_data))
        new_colors = _collect_bmesh_colors(changed_mesh) if is_edit else _collect_mesh_colors(changed_mesh)
        if _update_mesh(changed_mesh.name, new_colors):
            _write_palette(wm)


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
    """Browse all unique vertex colors currently in the scene"""
    bl_idname = "mesh.scene_color_palette"
    bl_label = "Scene Palette"

    def invoke(self, context, event):
        _rebuild_palette(context.scene)
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
            op = col.operator("mesh.select_palette_color", text="Use")
            op.index = i

    def execute(self, context):
        return {'FINISHED'}


def _draw_vertex_color_header(self, context):
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


addon_keymaps = []


def register():
    bpy.utils.register_class(VertexColorPaletteEntry)
    bpy.utils.register_class(MESH_OT_pick_vertex_color)
    bpy.utils.register_class(MESH_OT_assign_vertex_color)
    bpy.utils.register_class(MESH_OT_select_palette_color)
    bpy.utils.register_class(MESH_OT_scene_color_palette)
    bpy.types.WindowManager.vertex_color_palette = bpy.props.CollectionProperty(
        type=VertexColorPaletteEntry,
    )
    bpy.types.VIEW3D_HT_header.append(_draw_vertex_color_header)
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)

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
        default='VERTEX',
    )
    bpy.types.Scene.vertex_color_value = bpy.props.FloatVectorProperty(
        name="Color",
        description="The color to paint onto selected geometry",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0)
    )

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Use Ctrl+Shift on Windows/Linux, Cmd+Shift on macOS
        use_oskey = sys.platform == 'darwin'
        use_ctrl = not use_oskey

        km = kc.keymaps.new(name="Mesh", space_type='EMPTY')
        kmi = km.keymap_items.new("mesh.assign_vertex_color", 'V', 'PRESS', oskey=use_oskey, ctrl=use_ctrl, shift=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new("mesh.pick_vertex_color", 'C', 'PRESS', oskey=use_oskey, ctrl=use_ctrl, shift=True)
        addon_keymaps.append((km, kmi))

        km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
        kmi = km.keymap_items.new("mesh.assign_vertex_color", 'V', 'PRESS', oskey=use_oskey, ctrl=use_ctrl, shift=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new("mesh.pick_vertex_color", 'C', 'PRESS', oskey=use_oskey, ctrl=use_ctrl, shift=True)
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    global _palette_initialized
    _palette_initialized = False
    _color_refcounts.clear()
    _mesh_colors.clear()
    bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    bpy.types.VIEW3D_HT_header.remove(_draw_vertex_color_header)
    bpy.utils.unregister_class(MESH_OT_scene_color_palette)
    bpy.utils.unregister_class(MESH_OT_select_palette_color)
    bpy.utils.unregister_class(MESH_OT_pick_vertex_color)
    bpy.utils.unregister_class(MESH_OT_assign_vertex_color)
    bpy.utils.unregister_class(VertexColorPaletteEntry)
    del bpy.types.WindowManager.vertex_color_palette
    del bpy.types.Scene.vertex_color_apply_mode
    del bpy.types.Scene.vertex_color_value


if __name__ == "__main__":
    register()
