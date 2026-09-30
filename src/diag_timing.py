"""タイミング診断: 1周期ぶん、各脚の接地(■=接地)と、胸・腰の高さを並べて表示する。
「足が着いているのに胴が沈まない(=浮いて見える)」のような、接地と胴の動きのずれを見つける。
使い方: .\tools\bl.ps1 -Blend out\demo.blend src\diag_timing.py [-- 開始フレーム 終了フレーム]"""
import bpy
from common import *
from species import command_wolf as zoid

scene = bpy.context.scene
args = script_args()
f0 = int(args[0]) if args else 1
f1 = int(args[1]) if len(args) > 1 else f0 + 16
arm = bpy.data.objects[zoid.NAME]
pb = arm.pose.bones
names = [leg.name for leg in zoid.LEGS]

print("[diag] frame  " + " ".join(f"{n:>2}" for n in names) + "   胸(z)   腰(z)   胸-腰")
for f in range(f0, f1 + 1):
    scene.frame_set(f)
    marks = []
    for n in names:
        z = (arm.matrix_world @ pb[f"{n}_toe"].head).z
        marks.append(" ■" if z < zoid.CONTACT_Z else " ・")
    chest = (arm.matrix_world @ pb["chest"].tail).z      # 胸の前端
    hips = (arm.matrix_world @ pb["body"].head).z        # 腰の後端
    bar = "#" * int(max(0, (chest - 1.2)) * 60)
    print(f"[diag] {f:5d}  {' '.join(marks)}   {chest:.3f}   {hips:.3f}   {chest - hips:+.3f}  {bar}")
