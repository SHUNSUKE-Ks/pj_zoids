"""開いた .blend の動きを検査する(足滑り・めり込み)。歩容を足したら毎回回す。
使い方: .\tools\bl.ps1 -Blend out\demo.blend src\check_motion.py"""
import bpy
from common import *
from species import command_wolf as zoid
from zoidkit.checks import foot_slide_report, print_report

scene = bpy.context.scene
arm = bpy.data.objects[zoid.NAME]
ok = print_report(foot_slide_report(scene, arm, zoid.LEGS, zoid.CONTACT_Z))
if not ok:
    sys.exit(1)
