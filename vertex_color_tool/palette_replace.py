"""Replace a quantized color across all meshes in the scene."""

from array import array

import bpy
import bmesh

from .color_attr import CANONICAL_COLOR_ATTRIBUTE_NAME
from . import palette_state as state


def replace_color_in_meshes(old_color, new_color):
    """Replace all corners matching old_color with new_color across all meshes."""
    state.suppressing_updates = True
    try:
        nr, ng, nb, na = new_color
        q = state.quantize

        for mesh in bpy.data.meshes:
            is_edit = any(obj.mode == 'EDIT' for obj in bpy.data.objects
                          if obj.type == 'MESH' and obj.data == mesh)

            if is_edit:
                _replace_bmesh(mesh, old_color, nr, ng, nb, na, q)
            else:
                _replace_mesh(mesh, old_color, nr, ng, nb, na, q)

        # Update palette: remove old, add new
        new_q = q(nr, ng, nb, na)
        state.remove_color(old_color)
        state.add_colors({new_q})
    finally:
        state.suppressing_updates = False


def _replace_bmesh(mesh, old_color, nr, ng, nb, na, q):
    bm = bmesh.from_edit_mesh(mesh)
    layer = bm.loops.layers.float_color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if layer is None:
        layer = bm.loops.layers.color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if layer is None:
        return
    changed = False
    for face in bm.faces:
        for loop in face.loops:
            c = loop[layer]
            if q(c[0], c[1], c[2], c[3]) == old_color:
                c[0], c[1], c[2], c[3] = nr, ng, nb, na
                changed = True
    if changed:
        bmesh.update_edit_mesh(mesh)


def _replace_mesh(mesh, old_color, nr, ng, nb, na, q):
    color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if color_attr is None or color_attr.domain != 'CORNER':
        return

    n = len(color_attr.data)
    buf = array('f', [0.0]) * (n * 4)
    color_attr.data.foreach_get("color", buf)

    changed = False
    for i in range(0, n * 4, 4):
        if q(buf[i], buf[i + 1], buf[i + 2], buf[i + 3]) == old_color:
            buf[i] = nr
            buf[i + 1] = ng
            buf[i + 2] = nb
            buf[i + 3] = na
            changed = True

    if changed:
        color_attr.data.foreach_set("color", buf)
        mesh.update()
