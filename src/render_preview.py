"""開いた .blend を数フレーム描画して out/preview*.png に出す。
引数: [frame ...]  省略時は現在フレーム1枚。"""
import bpy
from common import *

scene = bpy.context.scene

if not any(o.type == "CAMERA" for o in scene.objects):
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    cam.location = (12, -16, 3)
    cam.rotation_euler = (1.48, 0, 0.64)
    scene.collection.objects.link(cam)
    scene.camera = cam

scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x, scene.render.resolution_y = 960, 540
scene.render.image_settings.file_format = "PNG"

frames = [int(a) for a in script_args()] or [scene.frame_current]
for f in frames:
    scene.frame_set(f)
    scene.render.filepath = os.path.join(OUT, f"preview_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[rendered] {scene.render.filepath}")
