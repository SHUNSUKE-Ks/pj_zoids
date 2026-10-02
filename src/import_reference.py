"""外部の3Dモデル(生成AIの出力など)を「参考モデル」として取り込む。
大きさをそろえ、地面に置き、ゾイドの横に並べて保存する。部品やリグには使わない(形を見比べるため)。

使い方:
  .\tools\bl.ps1 -Blend out\demo.blend src\import_reference.py -- <モデルのパス> [全長m=6.0] [横のずらしm=8.0] [Z回転deg=0] [保存先=out/with_reference.blend]
対応形式: .glb .gltf .fbx .obj
"""
import math
import bpy
from mathutils import Vector
from common import *

args = script_args()
if not args:
    sys.exit("モデルのパスを指定してください")
path = os.path.join(ROOT, args[0]) if not os.path.isabs(args[0]) else args[0]
length = float(args[1]) if len(args) > 1 else 6.0
shift_x = float(args[2]) if len(args) > 2 else 8.0
rot_z = math.radians(float(args[3])) if len(args) > 3 else 0.0
save_to = args[4] if len(args) > 4 else "out/with_reference.blend"

before = set(bpy.data.objects)
ext = os.path.splitext(path)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=path)
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=path)
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=path)
else:
    sys.exit(f"未対応の形式: {ext}")
new = [o for o in bpy.data.objects if o not in before]
roots = [o for o in new if o.parent is None]

# 取り込んだものを1つの空オブジェクトの下にまとめる
holder = bpy.data.objects.new("Reference", None)
bpy.context.scene.collection.objects.link(holder)
for o in roots:
    o.parent = holder
holder.rotation_euler.z = rot_z
bpy.context.view_layer.update()

# 全体の外形(ワールド座標)を測って、水平方向の長い辺が length になるよう拡大縮小
pts = [o.matrix_world @ Vector(c) for o in new if o.type == "MESH" for c in o.bound_box]
if not pts:
    sys.exit("メッシュが含まれていません")
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
size = hi - lo
s = length / max(size.x, size.y)
holder.scale = (s, s, s)
center = (lo + hi) / 2
holder.location = (shift_x - center.x * s, -center.y * s, -lo.z * s)   # 地面に置き、横へずらす
bpy.context.view_layer.update()

print(f"[reference] {os.path.basename(path)}: オブジェクト {len(new)} 個, 元の大きさ "
      f"{size.x:.2f} x {size.y:.2f} x {size.z:.2f} → 倍率 {s:.3f}")
save(save_to)
