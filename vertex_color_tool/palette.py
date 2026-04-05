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
    palette = wm.vertex_color_palette
    sorted_colors = sorted(
        _color_refcounts,
        key=lambda c: colorsys.rgb_to_hsv(c[0], c[1], c[2]),
    )
    palette.clear()
    for color in sorted_colors:
        entry = palette.add()
        entry.color = color


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


def on_depsgraph_update(scene, depsgraph):
    """Handler for bpy.app.handlers.depsgraph_update_post."""
    global _initialized
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
    color: bpy.props.FloatVectorProperty(subtype='COLOR', size=4, min=0.0, max=1.0)


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
            op = col.operator("mesh.select_palette_color", text="Use")
            op.index = i

    def execute(self, context):
        return {'FINISHED'}
