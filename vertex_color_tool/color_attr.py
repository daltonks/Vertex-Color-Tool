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

    n = len(target_attr.data)
    vert_indices = array('i', [0]) * n
    mesh.loops.foreach_get("vertex_index", vert_indices)

    corner_colors = array('f', [0.0]) * (n * 4)
    for i, vi in enumerate(vert_indices):
        src = vi * 4
        dst = i * 4
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


