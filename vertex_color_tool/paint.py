from array import array


def paint_color_indices(color_attr, indices, color_value):
    """Write color_value into the given corner indices of a color attribute."""
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


def paint_gradient_indices(color_attr, indices, mesh, obj_matrix,
                           start_world, end_world, color_a, color_b):
    """Write a linear gradient between two colors onto the given corner indices.

    The gradient axis runs from *start_world* to *end_world* in world space.
    Each corner's vertex position is projected onto that axis to produce a 0-1
    interpolation factor between *color_a* and *color_b*.
    """
    axis = end_world - start_world
    length_sq = axis.dot(axis)
    if length_sq < 1e-10:
        paint_color_indices(color_attr, indices, color_a)
        return

    n_loops = len(mesh.loops)
    vert_indices = array('i', [0]) * n_loops
    mesh.loops.foreach_get("vertex_index", vert_indices)

    n_verts = len(mesh.vertices)
    vert_cos = array('f', [0.0]) * (n_verts * 3)
    mesh.vertices.foreach_get("co", vert_cos)

    colors = array('f', [0.0]) * (len(color_attr.data) * 4)
    color_attr.data.foreach_get("color", colors)

    ra, ga, ba, aa = color_a
    dr = color_b[0] - ra
    dg = color_b[1] - ga
    db = color_b[2] - ba
    da = color_b[3] - aa

    ax, ay, az = axis.x, axis.y, axis.z
    sx, sy, sz = start_world.x, start_world.y, start_world.z
    m = obj_matrix

    for idx in indices:
        vi = vert_indices[idx]
        base_v = vi * 3
        lx = vert_cos[base_v]
        ly = vert_cos[base_v + 1]
        lz = vert_cos[base_v + 2]

        wx = m[0][0] * lx + m[0][1] * ly + m[0][2] * lz + m[0][3]
        wy = m[1][0] * lx + m[1][1] * ly + m[1][2] * lz + m[1][3]
        wz = m[2][0] * lx + m[2][1] * ly + m[2][2] * lz + m[2][3]

        t = ((wx - sx) * ax + (wy - sy) * ay + (wz - sz) * az) / length_sq
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0

        base = idx * 4
        colors[base] = ra + dr * t
        colors[base + 1] = ga + dg * t
        colors[base + 2] = ba + db * t
        colors[base + 3] = aa + da * t

    color_attr.data.foreach_set("color", colors)


def get_target_corner_indices(obj, mesh, original_mode, bm=None):
    """Return (indices, description) for the corners that should be painted.

    In object mode, all corners are targeted. In edit mode, corners are
    collected from all selected vertices, edges, and faces.
    """
    if original_mode == 'OBJECT':
        return list(range(len(mesh.loops))), "object"

    if bm is not None:
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
        return _loops_for_selected_verts(mesh, sel_verts), "vertices"

    # Fallback: read from mesh data (object mode)
    sel_verts = {v.index for v in mesh.vertices if v.select}
    for p in mesh.polygons:
        if p.select:
            sel_verts.update(p.vertices)
    return _loops_for_selected_verts(mesh, sel_verts), "vertices"


def _loops_for_selected_verts(mesh, sel_verts):
    """Return sorted loop indices whose vertex is in sel_verts."""
    n = len(mesh.loops)
    vert_indices = array('i', [0]) * n
    mesh.loops.foreach_get("vertex_index", vert_indices)
    return sorted(i for i, vi in enumerate(vert_indices) if vi in sel_verts)
