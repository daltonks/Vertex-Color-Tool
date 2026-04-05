"""Palette state: additive color tracking across all meshes in the scene."""

import colorsys
from array import array

import bpy
import bmesh

from .color_attr import CANONICAL_COLOR_ATTRIBUTE_NAME

_palette_colors = set()  # set of quantized color tuples
_scanned = False  # True after first full scene scan

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


def write_to_ui(wm):
    """Sync _palette_colors to the UI CollectionProperty, sorted by hue."""
    global suppressing_updates
    suppressing_updates = True
    try:
        palette = wm.vertex_color_palette
        sorted_colors = sorted(
            _palette_colors,
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


def ensure_scanned(scene):
    """Scan the scene if it hasn't been scanned yet. Called when palette is accessed."""
    global _scanned
    if _scanned:
        return
    _scanned = True
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        if obj.mode == 'EDIT':
            _palette_colors.update(collect_from_bmesh(obj.data))
        else:
            _palette_colors.update(collect_from_mesh(obj.data))
    wm = bpy.context.window_manager
    if hasattr(wm, 'vertex_color_palette'):
        write_to_ui(wm)


def add_colors(colors):
    """Add colors to the palette. Updates UI if any are new."""
    new = colors - _palette_colors
    if not new:
        return
    _palette_colors.update(new)
    wm = bpy.context.window_manager
    if hasattr(wm, 'vertex_color_palette'):
        write_to_ui(wm)


def remove_color(color):
    """Remove a single color from the palette."""
    _palette_colors.discard(color)


def trim(scene):
    """Remove palette colors not present in any mesh. Only scans when called."""
    scene_colors = set()
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        if obj.mode == 'EDIT':
            scene_colors |= collect_from_bmesh(obj.data)
        else:
            scene_colors |= collect_from_mesh(obj.data)
    _palette_colors.intersection_update(scene_colors)
    wm = bpy.context.window_manager
    if hasattr(wm, 'vertex_color_palette'):
        write_to_ui(wm)


def reset():
    """Clear all palette state (used on unregister)."""
    global _scanned
    _scanned = False
    _palette_colors.clear()
    palette_snapshot.clear()


def on_file_loaded(*_args):
    """Handler for load_post — clear state so next access re-scans."""
    global _scanned
    _scanned = False
    _palette_colors.clear()
    palette_snapshot.clear()


def on_undo_redo(scene):
    """Handler for undo_post/redo_post — full additive scan.

    Module-level palette state doesn't participate in Blender's undo, so
    colors removed by palette edits may reappear in meshes after undo.
    A full scan is the only reliable way to catch them.
    """
    added = False
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        if obj.mode == 'EDIT':
            new = collect_from_bmesh(obj.data) - _palette_colors
        else:
            new = collect_from_mesh(obj.data) - _palette_colors
        if new:
            _palette_colors.update(new)
            added = True

    if added:
        wm = bpy.context.window_manager
        if hasattr(wm, 'vertex_color_palette'):
            write_to_ui(wm)


