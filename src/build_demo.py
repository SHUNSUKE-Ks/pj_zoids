"""草原 + コマンドウルフ + 追従カメラのデモシーンを out/demo.blend に保存する。
引数: [総フレーム数(既定240)] [歩容(trot|gallop, 既定gallop)] [進行方向x] [進行方向y]
例: build_demo.py -- 240 gallop 1 0   (右への横ステップ)"""
import math
import bpy
from mathutils import Vector
from common import *
from field import make_field
from species import command_wolf as zoid

args = script_args()
FRAMES = int(args[0]) if args else 240
GAIT = args[1] if len(args) > 1 else "gallop"
DIRECTION = (float(args[2]), float(args[3])) if len(args) > 3 else None

scene = reset_scene()
make_field(scene)
arm = zoid.build(scene)
g = zoid.animate(scene, arm, FRAMES, GAIT, DIRECTION)

# --- カメラ(H19): 低い位置・広角。前半は並走、後半は止めて目の前を走り抜けさせる ---
target = bpy.data.objects.new("CamTarget", None)       # 狙い先は胴体付近(ウルフと一緒に動く)
target.parent = arm
target.location = (0, 0.6, 1.4)
scene.collection.objects.link(target)

cam_data = bpy.data.cameras.new("FollowCam")
cam_data.lens = 24
cam = bpy.data.objects.new("FollowCam", cam_data)
scene.collection.objects.link(cam)
tc = cam.constraints.new("TRACK_TO")
tc.target, tc.track_axis, tc.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
scene.camera = cam

fwd = g.direction
right = Vector((fwd.y, -fwd.x, 0))


def wolf_pos(f):
    return fwd * (g.speed * (f - 1) / zoid.FPS)


CUT = int(FRAMES * 0.55)
for f in range(1, CUT):                                 # 並走: 斜め前・低い位置。少し遅れて付いていく
    cam.location = wolf_pos(f - 3) + right * 5.5 + fwd * 3.5 + Vector((0, 0, 0.9 + 0.04 * math.sin(f * 0.7)))
    cam.keyframe_insert("location", frame=f)
fixed = wolf_pos(FRAMES - 25) + right * 3.2 + Vector((0, 0, 0.6))   # 走り抜け: 進路の脇に据え置き
for f in (CUT, FRAMES):
    cam.location = fixed
    cam.keyframe_insert("location", frame=f)
for fc in cam.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = "CONSTANT" if int(kp.co.x) == CUT - 1 else "LINEAR"

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
