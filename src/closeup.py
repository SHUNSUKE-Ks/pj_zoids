"""部位の寄り: 指定した骨の周りを真横(右側)から正投影で撮り、out/closeup/*.png に出す。
引数: 骨の名前 フレーム...   例: closeup.py -- FR_shin 1 3 5 7 9 11 13 15
つなげて1枚にするには: magick montage out/closeup/*.png -tile 4x -geometry +2+2 out/closeup_sheet.png"""
import bpy
from common import *

scene = bpy.context.scene
args = script_args()
bone = args[0]
frames = [int(a) for a in args[1:]] or [1]
arm = bpy.data.objects["CommandWolf"]

aim = bpy.data.objects.new("CloseAim", None)
scene.collection.objects.link(aim)
c = aim.constraints.new("COPY_LOCATION")          # 骨の中心を追う
c.target, c.subtarget, c.head_tail = arm, bone, 0.5
cd = bpy.data.cameras.new("CloseCam")
cd.type, cd.ortho_scale = "ORTHO", 2.6
cam = bpy.data.objects.new("CloseCam", cd)
cam.parent = aim
cam.location = (10, 0, 0)
cam.rotation_euler = (1.5708, 0, 1.5708)          # -X 方向(右側面)を見る
scene.collection.objects.link(cam)
scene.camera = cam

r = scene.render
r.image_settings.file_format = "PNG"
r.resolution_x = r.resolution_y = 480
os.makedirs(os.path.join(OUT, "closeup"), exist_ok=True)
for f in frames:
    scene.frame_set(f)
    r.filepath = os.path.join(OUT, "closeup", f"{bone}_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[closeup] {r.filepath}")
