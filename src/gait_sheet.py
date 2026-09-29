"""歩行の確認用: 真横の固定カメラで1周期を等間隔に描画し out/sheet/*.png に出す。
引数: [コマ数(既定8)] [開始フレーム(既定1)] [間隔フレーム(既定2)]
つなげて1枚にするには: magick montage out/sheet/*.png -tile 4x -geometry +2+2 out/gait_sheet.png"""
import bpy
from common import *

scene = bpy.context.scene
args = script_args()
n = int(args[0]) if len(args) > 0 else 8
start = int(args[1]) if len(args) > 1 else 1
step = int(args[2]) if len(args) > 2 else 2

arm = bpy.data.objects["CommandWolf"]
target = bpy.data.objects.new("SheetTarget", None)
target.parent = arm
target.location = (0, 0.3, 1.5)
scene.collection.objects.link(target)
cam_data = bpy.data.cameras.new("SheetCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 8.0
cam = bpy.data.objects.new("SheetCam", cam_data)
cam.parent = arm
cam.location = (12, 0.3, 1.5)
cam.rotation_euler = (1.5708, 0, 1.5708)     # -X 方向(=右側面)を見る
scene.collection.objects.link(cam)
scene.camera = cam

r = scene.render
r.image_settings.file_format = "PNG"
r.resolution_x, r.resolution_y = 640, 360
os.makedirs(os.path.join(OUT, "sheet"), exist_ok=True)
for i in range(n):
    f = start + i * step
    scene.frame_set(f)
    r.filepath = os.path.join(OUT, "sheet", f"f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print(f"[sheet] {r.filepath}")
