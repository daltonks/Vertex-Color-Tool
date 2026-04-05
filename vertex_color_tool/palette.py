import colorsys
from array import array

import bpy
import bmesh

from .color_attr import CANONICAL_COLOR_ATTRIBUTE_NAME

# ---------------------------------------------------------------------------
# Palette state: ref-counted colors across all meshes
# ---------------------------------------------------------------------------

_color_refcounts = {}   # color_tuple -> int (number of meshes using it)
_mesh_colors = {}       # mesh_name -> set of color_tuples
_initialized = False

_suppressing_updates = False
_palette_snapshot = {}  # index -> color_tuple, captured when popup opens


def _quantize(r, g, b, a):
    return (round(r, 2), round(g, 2), round(b, 2), round(a, 2))


def _collect_from_mesh(mesh):
    """Collect quantized colors from a mesh's Color attribute data."""
    color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if color_attr is None or color_attr.domain != 'CORNER' or len(color_attr.data) == 0:
        return set()
    n = len(color_attr.data)
    buf = array('f', [0.0]) * (n * 4)
    color_attr.data.foreach_get("color", buf)
    q = _quantize
    return {q(buf[i], buf[i + 1], buf[i + 2], buf[i + 3]) for i in range(0, n * 4, 4)}


def _collect_from_bmesh(mesh):
    """Collect quantized colors from a BMesh (for edit-mode meshes)."""
    bm = bmesh.from_edit_mesh(mesh)
    layer = bm.loops.layers.float_color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if layer is None:
        layer = bm.loops.layers.color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
    if layer is None:
        return set()
    q = _quantize
    return {q(c[0], c[1], c[2], c[3])
            for face in bm.faces for loop in face.loops for c in (loop[layer],)}


def _write_to_ui(wm):
    """Sync _color_refcounts to the UI CollectionProperty, sorted by hue."""
    global _suppressing_updates
    _suppressing_updates = True
    try:
        palette = wm.vertex_color_palette
        sorted_colors = sorted(
            _color_refcounts,
            key=lambda c: colorsys.rgb_to_hsv(c[0], c[1], c[2]),
        )
        palette.clear()
        _palette_snapshot.clear()
        for i, color in enumerate(sorted_colors):
            entry = palette.add()
            entry.color = color
            _palette_snapshot[i] = color
    finally:
        _suppressing_updates = False


def _update_single_mesh(mesh_name, new_colors):
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


# ---------------------------------------------------------------------------
# Color replacement
# ---------------------------------------------------------------------------

def _replace_color_in_meshes(old_color, new_color):
    """Replace all corners matching old_color with new_color across all meshes."""
    global _suppressing_updates
    mesh_names = [name for name, colors in _mesh_colors.items() if old_color in colors]
    if not mesh_names:
        return

    _suppressing_updates = True
    try:
        nr, ng, nb, na = new_color
        q = _quantize

        for mesh_name in mesh_names:
            mesh = bpy.data.meshes.get(mesh_name)
            if mesh is None:
                continue

            is_edit = any(obj.mode == 'EDIT' for obj in bpy.data.objects
                          if obj.type == 'MESH' and obj.data == mesh)

            if is_edit:
                bm = bmesh.from_edit_mesh(mesh)
                layer = bm.loops.layers.float_color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
                if layer is None:
                    layer = bm.loops.layers.color.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
                if layer is None:
                    continue
                changed = False
                for face in bm.faces:
                    for loop in face.loops:
                        c = loop[layer]
                        if q(c[0], c[1], c[2], c[3]) == old_color:
                            c[0], c[1], c[2], c[3] = nr, ng, nb, na
                            changed = True
                if changed:
                    bmesh.update_edit_mesh(mesh)
            else:
                color_attr = mesh.color_attributes.get(CANONICAL_COLOR_ATTRIBUTE_NAME)
                if color_attr is None or color_attr.domain != 'CORNER':
                    continue

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

        # Update internal bookkeeping
        new_q = q(nr, ng, nb, na)
        for mesh_name in mesh_names:
            colors = _mesh_colors.get(mesh_name)
            if colors and old_color in colors:
                colors.discard(old_color)
                colors.add(new_q)

        old_count = _color_refcounts.pop(old_color, 0)
        if old_count > 0:
            _color_refcounts[new_q] = _color_refcounts.get(new_q, 0) + old_count
    finally:
        _suppressing_updates = False


# ---------------------------------------------------------------------------
# Property update callback
# ---------------------------------------------------------------------------

def _on_palette_color_changed(self, context):
    if _suppressing_updates:
        return

    palette = context.window_manager.vertex_color_palette
    index = next((i for i, entry in enumerate(palette) if entry == self), -1)
    if index < 0:
        return

    old_color = _palette_snapshot.get(index)
    if old_color is None:
        return

    new_color = _quantize(*self.color)
    if old_color == new_color:
        return

    _replace_color_in_meshes(old_color, tuple(self.color))
    _palette_snapshot[index] = new_color


# ---------------------------------------------------------------------------
# Rebuild / reset / depsgraph handler
# ---------------------------------------------------------------------------

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
        colors = _collect_from_bmesh(obj.data) if obj.mode == 'EDIT' else _collect_from_mesh(obj.data)
        _mesh_colors[obj.data.name] = colors
        for color in colors:
            _color_refcounts[color] = _color_refcounts.get(color, 0) + 1
    _write_to_ui(wm)


def reset():
    """Clear all palette state (used on unregister)."""
    global _initialized
    _initialized = False
    _color_refcounts.clear()
    _mesh_colors.clear()
    _palette_snapshot.clear()


def on_depsgraph_update(scene, depsgraph):
    """Handler for bpy.app.handlers.depsgraph_update_post."""
    global _initialized
    if _suppressing_updates:
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
    new_colors = _collect_from_bmesh(changed_mesh) if is_edit else _collect_from_mesh(changed_mesh)
    if _update_single_mesh(changed_mesh.name, new_colors):
        _write_to_ui(wm)


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class VertexColorPaletteEntry(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(
        subtype='COLOR', size=4, min=0.0, max=1.0,
        update=_on_palette_color_changed,
    )


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
    """Browse and edit all unique vertex colors currently in the scene. Changing a color updates every mesh that uses it"""
    bl_idname = "mesh.scene_color_palette"
    bl_label = "Scene Palette"

    def invoke(self, context, event):
        rebuild(context.scene)
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
            col.operator_context = 'EXEC_DEFAULT'
            op = col.operator("mesh.select_palette_color", text="Use")
            op.index = i

    def execute(self, context):
        return {'FINISHED'}
