"""草原 + コマンドウルフ + 追従カメラのデモシーンを out/demo.blend に保存する。
引数: [総フレーム数(既定240)] [歩容(trot|gallop, 既定gallop)] [進行方向x] [進行方向y]
例: build_demo.py -- 240 gallop 1 0   (右への横ステップ)"""
import math
import bpy
from common import *
from field import make_field
import wolf

args = script_args()
FRAMES = int(args[0]) if args else 240
GAIT = args[1] if len(args) > 1 else "gallop"
DIRECTION = (float(args[2]), float(args[3])) if len(args) > 3 else None

scene = reset_scene()
make_field(scene)
arm = wolf.make_rig(scene)
wolf.make_model(scene, arm)
wolf.animate(scene, arm, FRAMES, GAIT, DIRECTION)

# --- 追従カメラ: アーマチュアの子にして一緒に走らせ、狙い先は胴体付近 ---
target = bpy.data.objects.new("CamTarget", None)
target.parent = arm
target.location = (0, 0.3, 1.7)
scene.collection.objects.link(target)

cam_data = bpy.data.cameras.new("FollowCam")
cam_data.lens = 32
cam = bpy.data.objects.new("FollowCam", cam_data)
cam.parent = arm
scene.collection.objects.link(cam)
tc = cam.constraints.new("TRACK_TO")
tc.target, tc.track_axis, tc.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
scene.camera = cam
# 側面 → 正面斜め → 後方斜め とゆっくり回り込む
for frac, loc in ((0.0, (9, 1, 2.2)), (0.4, (6.5, 8, 1.7)), (0.75, (-6, 7, 2.2)), (1.0, (-8, -4, 3.0))):
    cam.location = loc
    cam.keyframe_insert("location", frame=1 + int(frac * (FRAMES - 1)))

# --- 描画設定 ---
r = scene.render
r.engine = "BLENDER_EEVEE_NEXT"
r.resolution_x, r.resolution_y = 1280, 720
scene.eevee.taa_render_samples = 24
try:
    scene.view_settings.view_transform = "Standard"
except TypeError:
    pass
save("out/demo.blend")
