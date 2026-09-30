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
try:                                   # モーションブラー(速い部分だけぶれて速さが出る)
    r.use_motion_blur = True
    r.motion_blur_shutter = 0.5
except AttributeError:
    print("[video] motion blur の設定項目がこの版にない")
r.filepath =os.path.join(ROOT, args[0] if args else "out/zoids_demo.mp4")
bpy.ops.render.render(animation=True)
print(f"[video] {r.filepath}")
