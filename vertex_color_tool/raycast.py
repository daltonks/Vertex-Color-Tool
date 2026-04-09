from array import array

import bmesh
from bpy_extras import view3d_utils
from mathutils.bvhtree import BVHTree

from .color_attr import CANONICAL_COLOR_ATTRIBUTE_NAME


_vert_loop_cache = {}  # mesh_ptr -> (n_loops, dict)


def _loops_for_vertex(mesh, vertex_index):
    """Return loop indices for a given vertex, using a cached lookup table."""
    key = mesh.as_pointer()
    n = len(mesh.loops)
    cached = _vert_loop_cache.get(key)
    if cached is not None and cached[0] == n:
        lut = cached[1]
    else:
        from collections import defaultdict
        lut = defaultdict(list)
        for loop in mesh.loops:
            lut[loop.vertex_index].append(loop.index)
        _vert_loop_cache[key] = (n, lut)
    return list(lut.get(vertex_index, ()))


def find_view3d_region(context, mouse_x, mouse_y):
    """Return (area, region, region_3d) for the 3D viewport under the cursor."""
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type != 'WINDOW':
                continue
            if (region.x <= mouse_x < region.x + region.width
                    and region.y <= mouse_y < region.y + region.height):
                return area, region, area.spaces.active.region_3d
    return None, None, None


def _get_cached_bvh(mesh, cache):
    """Look up or build a BVH for a mesh, using cache if provided."""
    if cache is None:
        return build_bvh(mesh)
    key = mesh.as_pointer()
    if key not in cache:
        cache[key] = build_bvh(mesh)
    return cache[key]


def build_bvh(mesh):
    """Build a BVH tree from a mesh. Cache-friendly — call once and reuse."""
    if not mesh.polygons or not mesh.vertices:
        return None
    return BVHTree.FromPolygons(
        [v.co.copy() for v in mesh.vertices],
        [tuple(p.vertices) for p in mesh.polygons],
    )


def bvh_raycast(obj, ray_origin, ray_direction, mesh=None, bvh=None):
    """Ray-cast against an object via BVH. Returns (dist_sq, face_index, location_local) or None."""
    if mesh is None:
        mesh = obj.data
    if bvh is None:
        bvh = build_bvh(mesh)
    if bvh is None:
        return None
    mat = obj.matrix_world
    mat_inv = mat.inverted()
    origin = mat_inv @ ray_origin
    direction = (mat_inv.to_3x3() @ ray_direction).normalized()
    loc, _, face_index, _ = bvh.ray_cast(origin, direction)
    if loc is None or face_index is None or face_index < 0:
        return None
    return (mat @ loc - ray_origin).length_squared, face_index, loc


_color_buf_cache = {}  # mesh_ptr -> (len, array)


def _get_color_buffer(color_attr, mesh_ptr):
    """Return the cached color buffer for a mesh, rebuilding if stale."""
    n = len(color_attr.data)
    cached = _color_buf_cache.get(mesh_ptr)
    if cached is not None and cached[0] == n:
        return cached[1]
    buf = array('f', [0.0]) * (n * 4)
    color_attr.data.foreach_get("color", buf)
    _color_buf_cache[mesh_ptr] = (n, buf)
    return buf


def invalidate_color_cache():
    """Clear cached mesh data (call after painting or undo)."""
    _color_buf_cache.clear()
    _vert_loop_cache.clear()


def _sample_color_mesh(mesh, color_attr, face_index, hit_local):
    """Sample the closest loop color from mesh data."""
    polygon = mesh.polygons[face_index]
    loop_indices = list(polygon.loop_indices)
    if not loop_indices:
        return None

    colors = _get_color_buffer(color_attr, mesh.as_pointer())

    best = min(
        loop_indices,
        key=lambda li: (mesh.vertices[mesh.loops[li].vertex_index].co - hit_local).length_squared,
    )
    base = best * 4
    if base + 3 >= len(colors):
        return None
    return (colors[base], colors[base + 1], colors[base + 2], colors[base + 3])


def _sample_color_bmesh(obj, face_index, hit_local):
    """Sample color from BMesh (required in edit mode where mesh data is stale)."""
    bm = bmesh.from_edit_mesh(obj.data)
    layer = bm.loops.layers.float_color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if layer is None:
        layer = bm.loops.layers.color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if layer is None:
        return None
    bm.faces.ensure_lookup_table()
    if face_index >= len(bm.faces):
        return None
    face = bm.faces[face_index]
    best = min(face.loops, key=lambda l: (l.vert.co - hit_local).length_squared)
    c = best[layer]
    return (c[0], c[1], c[2], c[3])


def pick_color(context, mouse_x, mouse_y, bvh_cache=None):
    """Sample a vertex color under the cursor.

    Returns ((obj, color_tuple), None) on success, or (None, error_string) on failure.
    bvh_cache is an optional dict (mesh_ptr -> BVHTree) reused across calls.
    """
    area, region, region_3d = find_view3d_region(context, mouse_x, mouse_y)
    if region is None or region_3d is None:
        return None, "Cursor is not inside a 3D Viewport"

    coord = (mouse_x - region.x, mouse_y - region.y)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, coord)
    ray_direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, coord)

    depsgraph = context.evaluated_depsgraph_get()
    best_hit = None  # (dist_sq, obj, mesh, face_index, location_local, from_eval)

    if context.mode == 'EDIT_MESH':
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            obj.update_from_editmode()

            bvh = _get_cached_bvh(obj.data, bvh_cache)
            hit = bvh_raycast(obj, ray_origin, ray_direction, bvh=bvh)
            if hit is not None:
                dist_sq, face_index, loc = hit
                if best_hit is None or dist_sq < best_hit[0]:
                    best_hit = (dist_sq, obj, obj.data, face_index, loc, False)

            eval_obj = obj.evaluated_get(depsgraph)
            eval_mesh = eval_obj.to_mesh()
            if eval_mesh is not None and len(eval_mesh.polygons) > len(obj.data.polygons):
                eval_bvh = _get_cached_bvh(eval_mesh, bvh_cache)
                hit = bvh_raycast(obj, ray_origin, ray_direction, mesh=eval_mesh, bvh=eval_bvh)
                if hit is not None:
                    dist_sq, face_index, loc = hit
                    if best_hit is None or dist_sq < best_hit[0]:
                        best_hit = (dist_sq, obj, eval_mesh, face_index, loc, True)

    result, location, _, face_index, hit_obj, matrix = context.scene.ray_cast(
        depsgraph, ray_origin, ray_direction,
    )
    if result and hit_obj and hit_obj.type == 'MESH' and hit_obj.mode != 'EDIT':
        dist_sq = (location - ray_origin).length_squared
        if best_hit is None or dist_sq < best_hit[0]:
            loc = matrix.inverted() @ location
            eval_obj = hit_obj.evaluated_get(depsgraph)
            best_hit = (dist_sq, hit_obj, eval_obj.data, face_index, loc, False)

    if best_hit is not None:
        _, obj, mesh, face_index, loc, from_eval = best_hit
        if obj.mode == 'EDIT' and not from_eval:
            color = _sample_color_bmesh(obj, face_index, loc)
        else:
            color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
            color = None
            if color_attr is not None and color_attr.domain == 'CORNER' and len(color_attr.data) > 0:
                color = _sample_color_mesh(mesh, color_attr, face_index, loc)
        if color is not None:
            return (obj, color), None
        return None, f"'{obj.name}' has no vertex colors to sample"

    return None, "No painted mesh under cursor"


def get_paint_targets(context, mouse_x, mouse_y, bvh_cache=None):
    """Return [(obj, loop_indices)] for geometry under the cursor, or (None, error_string)."""
    area, region, region_3d = find_view3d_region(context, mouse_x, mouse_y)
    if region is None or region_3d is None:
        return None, "Cursor is not inside a 3D Viewport"

    coord = (mouse_x - region.x, mouse_y - region.y)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, coord)
    ray_direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, coord)

    if context.mode == 'EDIT_MESH':
        best = None
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            obj.update_from_editmode()
            bvh = _get_cached_bvh(obj.data, bvh_cache)
            hit = bvh_raycast(obj, ray_origin, ray_direction, bvh=bvh)
            if hit and (best is None or hit[0] < best[0]):
                best = (hit[0], obj, hit[1], hit[2])

        if best is None:
            return None, "No mesh face under cursor"

        _, obj, face_index, loc = best
        mesh = obj.data
        polygon = mesh.polygons[face_index]
        vertex_sel, edge_sel, face_sel = context.tool_settings.mesh_select_mode

        if face_sel:
            loop_indices = list(polygon.loop_indices)
        elif vertex_sel:
            nearest_vi = min(
                polygon.vertices,
                key=lambda vi: (mesh.vertices[vi].co - loc).length_squared,
            )
            loop_indices = _loops_for_vertex(mesh, nearest_vi)
        else:
            verts = list(polygon.vertices)
            pairs = [(verts[i], verts[(i + 1) % len(verts)]) for i in range(len(verts))]
            v0, v1 = min(
                pairs,
                key=lambda p: (
                    (mesh.vertices[p[0]].co + mesh.vertices[p[1]].co) / 2 - loc
                ).length_squared,
            )
            loop_indices = _loops_for_vertex(mesh, v0) + _loops_for_vertex(mesh, v1)

        return [(obj, loop_indices)], None

    else:
        depsgraph = context.evaluated_depsgraph_get()
        result, _, _, _, hit_obj, _ = context.scene.ray_cast(depsgraph, ray_origin, ray_direction)
        if not result or hit_obj is None or hit_obj.type != 'MESH':
            return None, "No mesh face under cursor"
        return [(hit_obj, list(range(len(hit_obj.data.loops))))], None
