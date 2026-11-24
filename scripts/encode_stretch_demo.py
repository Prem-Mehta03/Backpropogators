"""Blender batch encoder for the local trace demonstration frame manifest."""

import json
from pathlib import Path
import sys

import bpy

source, output = map(Path, sys.argv[sys.argv.index("--") + 1:])
scene = bpy.context.scene
editor = scene.sequence_editor_create()
frames = json.loads(source.read_text(encoding="utf-8"))
start = 1
for entry in frames:
    slide = editor.strips.new_image(Path(entry["file"]).stem, entry["file"], 1, start)
    start += entry["frames"]
    slide.frame_final_end = start
scene.frame_start, scene.frame_end = 1, start - 1
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.render.image_settings.media_type = "VIDEO"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
scene.render.filepath = str(output)
scene.render.use_file_extension = False
scene.view_settings.view_transform = "Standard"
bpy.ops.render.render(animation=True)
