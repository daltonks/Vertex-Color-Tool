# Vertex Color Tool

A Blender add-on for painting precise vertex colors (RGBA) in Edit and Object mode.

## Requirements

- Blender **5.1.0** or later

## Installation

1. Download or clone this repository.
2. In Blender, go to **Edit > Preferences > Add-ons > Install from Disk**.
3. Select the `vertex_color_tool` folder.
4. Enable **Vertex Color Tool** in the add-on list.

The panel appears in the 3D Viewport sidebar under the **Tool** tab.

## Features

### Paint

Select geometry and press the shortcut (or use the panel) to fill the selection with the active color. Supports vertex, edge, and face selection modes. When nothing is selected, hold the shortcut to paint under the cursor with continuous raycast tracking.

### Eyedropper

Hold the shortcut to sample the vertex color under the cursor. The sampled color (including alpha) becomes the active color. Move the mouse while holding to continuously sample.

### Gradient

Paint a linear gradient between two colors across selected geometry. Click once to set the start point, move to set the direction, and click again to confirm. A live preview updates as you move. Press Escape or right-click to cancel and restore the original colors.

## Keyboard shortcuts

| Action | Windows / Linux | macOS |
|---|---|---|
| Paint | `Ctrl+Shift+V` | `Cmd+Shift+V` |
| Eyedropper | `Ctrl+Shift+C` | `Cmd+Shift+C` |
| Gradient | `Ctrl+Shift+G` | `Cmd+Shift+G` |

Shortcuts work in both Edit and Object mode. A quick-reference popup is available via the info button in the panel.

## How it works

- Colors are stored in a **Face Corner** (loop) domain attribute named `Color` using **Float Color** data.
- If a mesh has existing color attributes in a different format (Point domain, Byte Color, differently named), the add-on automatically migrates the data and consolidates to a single canonical attribute.
- Multi-object editing is supported: in Edit mode, all objects being edited are painted simultaneously.

## Authors

BobHop & Dalton Spillman
