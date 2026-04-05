import bpy

from .raycast import pick_color


class MESH_OT_pick_vertex_color(bpy.types.Operator):
    """Sample a vertex color from the mesh under the cursor. Hold the key to continuously sample while moving the mouse"""
    bl_idname = "mesh.pick_vertex_color"
    bl_label = "Eyedropper"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.report({'INFO'}, "Use the shortcut or click in the 3D Viewport to sample a vertex color")
        return {'CANCELLED'}

    def invoke(self, context, event):
        if context.window_manager is None:
            self.report({'ERROR'}, "No window manager available")
            return {'CANCELLED'}

        self._trigger_key = event.type
        self._sample(context, event.mouse_x, event.mouse_y)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._finish(context)
            return {'CANCELLED'}

        if event.type == self._trigger_key and event.value == 'RELEASE':
            self._finish(context)
            return {'FINISHED'}

        if event.type == 'MOUSEMOVE':
            self._sample(context, event.mouse_x, event.mouse_y)

        return {'RUNNING_MODAL'}

    def _finish(self, context):
        if context.workspace is not None:
            context.workspace.status_text_set(None)

    def _sample(self, context, mouse_x, mouse_y):
        result, _ = pick_color(context, mouse_x, mouse_y)
        if result is None:
            return
        _, color_value = result
        context.scene.vertex_color_value = color_value
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
