"""Palette state: additive color tracking across all meshes in the scene."""

from array import array

import bpy
import bmesh

from .color_attr import CANONICAL_COLOR_ATTRIBUTE_NAME

_palette_colors = []   # list of quantized color tuples, insertion order
_palette_set = set()   # for fast membership checks
_scanned = False

suppressing_updates = False
palette_snapshot = {}  # index -> color_tuple, for the edit operator


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


def _sort_key(c):
    """Sort by perceived lightness first, then hue, then saturation.

    Groups visually similar colors together — all darks together, all brights
    together, with hue ordering within each lightness level.
    """
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(c[0], c[1], c[2])
    # Perceived lightness (0-1), quantized into bands so similar
    # lightness levels group together
    lightness = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    lightness_band = round(lightness, 1)
    return (-lightness_band, (h + 0.05) % 1.0, -s)


def write_to_ui(wm):
    """Sync _palette_colors to the UI CollectionProperty, sorted for visual clarity."""
    global suppressing_updates
    suppressing_updates = True
    try:
        palette = wm.vertex_color_palette
        sorted_colors = sorted(_palette_colors, key=_sort_key)
        palette.clear()
        palette_snapshot.clear()
        for i, color in enumerate(sorted_colors):
            entry = palette.add()
            entry.color = color
            palette_snapshot[i] = color
    finally:
        suppressing_updates = False


def reconcile(scene):
    """Full rebuild from scene meshes. Preserves order for existing colors."""
    scene_colors = set()
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        if obj.mode == 'EDIT':
            scene_colors |= collect_from_bmesh(obj.data)
        else:
            scene_colors |= collect_from_mesh(obj.data)

    if scene_colors == _palette_set:
        return False

    kept = [c for c in _palette_colors if c in scene_colors]
    new = scene_colors - _palette_set
    _palette_colors[:] = kept + list(new)
    _palette_set.clear()
    _palette_set.update(scene_colors)
    return True


def ensure_scanned(scene):
    """Scan the scene once on first access."""
    global _scanned
    if _scanned:
        return
    _scanned = True
    if reconcile(scene):
        wm = bpy.context.window_manager
        if hasattr(wm, 'vertex_color_palette'):
            write_to_ui(wm)


def add_colors(colors):
    """Add colors to the palette. Updates UI if any are new."""
    new = colors - _palette_set
    if not new:
        return
    _palette_set.update(new)
    _palette_colors.extend(new)
    wm = bpy.context.window_manager
    if hasattr(wm, 'vertex_color_palette'):
        write_to_ui(wm)


def remove_color(color):
    """Remove a single color from the palette."""
    _palette_set.discard(color)
    try:
        _palette_colors.remove(color)
    except ValueError:
        pass



def reset():
    """Clear all palette state (used on unregister)."""
    global _scanned
    _scanned = False
    _palette_colors.clear()
    _palette_set.clear()
    palette_snapshot.clear()


def on_file_loaded(*_args):
    """Handler for load_post — clear state so next access re-scans."""
    global _scanned
    _scanned = False
    _palette_colors.clear()
    _palette_set.clear()
    palette_snapshot.clear()


def on_undo_redo(scene):
    """Handler for undo_post/redo_post — full reconciliation."""
    if reconcile(scene):
        wm = bpy.context.window_manager
        if hasattr(wm, 'vertex_color_palette'):
            write_to_ui(wm)
