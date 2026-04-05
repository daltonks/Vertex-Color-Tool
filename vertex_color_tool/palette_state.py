"""Palette state: ref-counted color tracking across all meshes in the scene."""

import colorsys
from array import array

import bpy
import bmesh

from .color_attr import CANONICAL_COLOR_ATTRIBUTE_NAME

# color_tuple -> int (number of meshes using it)
_color_refcounts = {}
# mesh_name -> set of color_tuples
_mesh_colors = {}

_initialized = False
suppressing_updates = False

# index -> color_tuple, captured when the palette popup opens or UI rebuilds
palette_snapshot = {}


def quantize(r, g, b, a):
    return (round(r, 2), round(g, 2), round(b, 2), round(a, 2))


def collect_from_mesh(mesh):
    """Collect quantized colors from a mesh's Color attribute data."""
    color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if color_attr is None or color_attr.domain != 'CORNER' or len(color_attr.data) == 0:
        return set()
    n = len(color_attr.data)
    buf = array('f', [0.0]) * (n * 4)
    color_attr.data.foreach_get("color", buf)
    q = quantize
    return {q(buf[i], buf[i + 1], buf[i + 2], buf[i + 3]) for i in range(0, n * 4, 4)}


def collect_from_bmesh(mesh):
    """Collect quantized colors from a BMesh (for edit-mode meshes)."""
    bm = bmesh.from_edit_mesh(mesh)
    layer = bm.loops.layers.float_color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if layer is None:
        layer = bm.loops.layers.color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if layer is None:
        return set()
    q = quantize
    return {q(c[0], c[1], c[2], c[3])
            for face in bm.faces for loop in face.loops for c in (loop[layer],)}


def write_to_ui(wm):
    """Sync _color_refcounts to the UI CollectionProperty, sorted by hue."""
    global suppressing_updates
    suppressing_updates = True
    try:
        palette = wm.vertex_color_palette
        sorted_colors = sorted(
            _color_refcounts,
            key=lambda c: colorsys.rgb_to_hsv(c[0], c[1], c[2]),
        )
        palette.clear()
        palette_snapshot.clear()
        for i, color in enumerate(sorted_colors):
            entry = palette.add()
            entry.color = color
            palette_snapshot[i] = color
    finally:
        suppressing_updates = False


def update_single_mesh(mesh_name, new_colors):
    """Diff a mesh's colors against the previous snapshot. Returns True if the palette changed."""
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


def meshes_using_color(color):
    """Return list of mesh names that contain the given quantized color."""
    return [name for name, colors in _mesh_colors.items() if color in colors]


def update_bookkeeping(mesh_names, old_color, new_quantized):
    """Update _mesh_colors and _color_refcounts after a color replacement."""
    for mesh_name in mesh_names:
        colors = _mesh_colors.get(mesh_name)
        if colors and old_color in colors:
            colors.discard(old_color)
            colors.add(new_quantized)

    old_count = _color_refcounts.pop(old_color, 0)
    if old_count > 0:
        _color_refcounts[new_quantized] = _color_refcounts.get(new_quantized, 0) + old_count


def rebuild(scene):
    """Full scene scan — populates ref-counts from scratch."""
    wm = bpy.context.window_manager
    if not hasattr(wm, 'vertex_color_palette'):
        return
    _color_refcounts.clear()
    _mesh_colors.clear()
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        colors = collect_from_bmesh(obj.data) if obj.mode == 'EDIT' else collect_from_mesh(obj.data)
        _mesh_colors[obj.data.name] = colors
        for color in colors:
            _color_refcounts[color] = _color_refcounts.get(color, 0) + 1
    write_to_ui(wm)


def reset():
    """Clear all palette state (used on unregister)."""
    global _initialized
    _initialized = False
    _color_refcounts.clear()
    _mesh_colors.clear()
    palette_snapshot.clear()


def on_depsgraph_update(scene, depsgraph):
    """Handler for bpy.app.handlers.depsgraph_update_post."""
    global _initialized
    if suppressing_updates:
        return

    wm = bpy.context.window_manager
    if not hasattr(wm, 'vertex_color_palette'):
        return

    if not _initialized:
        _initialized = True
        rebuild(scene)
        return

    changed_mesh = None
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Mesh) and update.is_updated_geometry:
            changed_mesh = update.id
            break

    if changed_mesh is None:
        return

    is_edit = (bpy.context.mode == 'EDIT_MESH'
               and any(obj.data == changed_mesh for obj in bpy.context.objects_in_mode_unique_data))
    new_colors = collect_from_bmesh(changed_mesh) if is_edit else collect_from_mesh(changed_mesh)
    if update_single_mesh(changed_mesh.name, new_colors):
        write_to_ui(wm)
