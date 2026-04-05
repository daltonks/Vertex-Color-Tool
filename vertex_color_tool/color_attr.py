from array import array

DEFAULT_COLOR_ATTRIBUTE_NAMES = ("Color", "Attribute", "Col")
CANONICAL_COLOR_ATTRIBUTE_NAME = "Color"


def _color_attr_sort_key(color_attr):
    return (
        color_attr.name != CANONICAL_COLOR_ATTRIBUTE_NAME,
        color_attr.name not in DEFAULT_COLOR_ATTRIBUTE_NAMES,
        color_attr.domain != 'CORNER',
        color_attr.data_type != 'FLOAT_COLOR',
        color_attr.name,
    )


def _copy_point_to_corner(mesh, source_attr, target_attr):
    point_colors = array('f', [0.0]) * (len(source_attr.data) * 4)
    source_attr.data.foreach_get("color", point_colors)

    corner_colors = array('f', [0.0]) * (len(target_attr.data) * 4)
    for loop in mesh.loops:
        src = loop.vertex_index * 4
        dst = loop.index * 4
        corner_colors[dst:dst + 4] = point_colors[src:src + 4]

    target_attr.data.foreach_set("color", corner_colors)


def _copy_corner_to_corner(source_attr, target_attr):
    if len(source_attr.data) != len(target_attr.data):
        target_attr.data.foreach_set("color", [1.0, 1.0, 1.0, 1.0] * len(target_attr.data))
        return

    colors = array('f', [0.0]) * (len(source_attr.data) * 4)
    source_attr.data.foreach_get("color", colors)
    target_attr.data.foreach_set("color", colors)


def _pick_source_attribute(mesh):
    active = mesh.color_attributes.active_color
    if active is not None:
        return active

    render_index = mesh.color_attributes.render_color_index
    if render_index != -1:
        return mesh.color_attributes[render_index]

    attrs = list(mesh.color_attributes)
    if not attrs:
        return None

    attrs.sort(key=_color_attr_sort_key)
    return attrs[0]


def resolve_color_attribute(mesh):
    """Ensure the mesh has exactly one Color attribute in CORNER/FLOAT_COLOR form.

    Migrates data from existing attributes if needed, then removes extras.
    """
    source_attr = _pick_source_attribute(mesh)
    color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)

    if (color_attr is not None
            and color_attr.domain == 'CORNER'
            and color_attr.data_type == 'FLOAT_COLOR'):
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
                _copy_corner_to_corner(source_attr, target_attr)
            elif source_attr.domain == 'POINT':
                _copy_point_to_corner(mesh, source_attr, target_attr)

    for name in [a.name for a in mesh.color_attributes if a.name != CANONICAL_COLOR_ATTRIBUTE_NAME]:
        attr = mesh.color_attributes.get(name)
        if attr is not None:
            mesh.color_attributes.remove(attr)

    return target_attr


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
        return sorted(l.index for l in mesh.loops if l.vertex_index in sel_verts), "vertices"

    # Fallback: read from mesh data (object mode)
    sel_verts = {v.index for v in mesh.vertices if v.select}
    for p in mesh.polygons:
        if p.select:
            sel_verts.update(p.vertices)
    return sorted(l.index for l in mesh.loops if l.vertex_index in sel_verts), "vertices"
