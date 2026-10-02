"""開いた .blend のゾイド(アーマチュア + 部品 + アニメーション)を .glb に書き出す。
外部AIやゲームエンジンへの引き渡し用。
使い方: .\tools\bl.ps1 -Blend out\demo.blend src\export_glb.py [-- 出力パス(既定 out/CommandWolf.glb) [アーマチュア名]]"""
import bpy
from common import *

args = script_args()
out = os.path.join(ROOT, args[0]) if args else os.path.join(OUT, "CommandWolf.glb")
arm_name = args[1] if len(args) > 1 else "CommandWolf"
arm = bpy.data.objects[arm_name]

bpy.ops.object.select_all(action="DESELECT")
arm.select_set(True)
for ob in arm.children:
    if ob.type == "MESH":
        ob.select_set(True)
bpy.context.view_layer.objects.active = arm

bpy.ops.export_scene.gltf(
    filepath=out,
    export_format="GLB",
    use_selection=True,
    export_animations=True,
    export_yup=True,            # glTF の決まり(Y が上)に変換する
)
print(f"[export] {out}  部品 {sum(1 for o in arm.children if o.type == 'MESH')} 個")
