"""開いた .blend を mp4 に書き出す。引数: [出力パス(既定 out/zoids_demo.mp4)]"""
import bpy
from common import *

scene = bpy.context.scene
args = script_args()
r = scene.render
r.image_settings.file_format = "FFMPEG"
r.ffmpeg.format = "MPEG4"
r.ffmpeg.codec = "H264"
r.ffmpeg.constant_rate_factor = "MEDIUM"
r.filepath = os.path.join(ROOT, args[0] if args else "out/zoids_demo.mp4")
bpy.ops.render.render(animation=True)
print(f"[video] {r.filepath}")
