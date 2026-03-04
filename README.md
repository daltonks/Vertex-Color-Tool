# Vertex-Color-Tool
A minimalist Blender add-on to work with vertex color (and alpha) in Edit mode.

## Why?
As of Blender 4.5.3 LTS, working with vertex colors still requires an artistic approach in Vertex Paint mode. Applying precise vertex colors to specific vertices isn't straightforward, and the color picker doesn't work with vertex alpha. Such data can be crucial for shaders or game engines (terrain, heatmaps, weather systems etc).

This tool lets you change vertex colors in Edit mode, using simple selections and a minimalist UI. It works with RGB **and alpha** and translates well to Unity or Unreal Engine, for instance. Tested on Blender 4.5.3 LTS, should work fine with more releases.

## Usage
![Quick Tutorial](vertex_color_tool.png)

## Possible improvements
- Allow Face Corner domain (for sharp colored edges).
- Allow Byte Color data type (for compatibility).
- Toggle vertex color in 3D viewport without having to modify the material.
