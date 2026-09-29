"""評価用: 静止姿勢(レスト)を 側面/斜め前/正面/上面 から撮り out/review/*.png に出す。
つなげて1枚にするには: magick montage out/review/*.png -tile 2x -geometry +2+2 out/review_sheet.png"""
import math
import bpy
from common import *

scene = bpy.context.scene
arm = bpy.data.objects["CommandWolf"]
arm.data.pose_position = "REST"
scene.frame_set(1)
arm.animation_data_clear()
arm.location = (0, 0, 0)

# 背景の岩や木は評価の邪魔なので隠す
for name in ("Rocks", "TrunkS", "Leaves"):
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = True

SHOTS = {  # 名前: (カメラ位置, 正射影の幅 or None)
    "1_side": ((12, 0.4, 1.8), 8.5),
    "2_front34": ((7.5, 8.5, 3.6), None),
    "3_front": ((0, 12, 1.9), 5.5),
    "4_top": ((0, 0.4, 14), 8.5),
}
aim = bpy.data.objects.new("ReviewAim", None)
aim.location = (0, 0.4, 1.6)
scene.collection.objects.link(aim)

r = scene.render
r.image_settings.file_format = "PNG"
r.resolution_x, r.resolution_y = 960, 540
os.makedirs(os.path.join(OUT, "review"), exist_ok=True)
for name, (loc, ortho) in SHOTS.items():
    cd = bpy.data.cameras.new(name)
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.lens = 40
    cam = bpy.data.objects.new(name, cd)
    cam.location = loc
    scene.collection.objects.link(cam)
    tc = cam.constraints.new("TRACK_TO")
    tc.target, tc.track_axis = aim, "TRACK_NEGATIVE_Z"
    tc.up_axis = "UP_Y" if name != "4_top" else "UP_X"
    scene.camera = cam
    r.filepath = os.path.join(OUT, "review", f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[review] {r.filepath}")
