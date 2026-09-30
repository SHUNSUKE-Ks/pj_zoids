"""キャノピーの開閉確認: 閉/開 の2状態で頭部を寄りで撮り out/canopy_*.png に出す。"""
import bpy
from common import *
from species import command_wolf as zoid

for label, ang in (("closed", 0.0), ("open", 0.9)):
    scene = reset_scene()
    arm = zoid.build(scene)
    zoid.animate(scene, arm, 1, "gallop", None, canopy=ang)
    aim = bpy.data.objects.new("Aim", None)
    scene.collection.objects.link(aim)
    c = aim.constraints.new("COPY_LOCATION")
    c.target, c.subtarget, c.head_tail = arm, "head", 0.4
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 50
    cam = bpy.data.objects.new("Cam", cd)
    cam.parent = aim
    cam.location = (3.2, 2.2, 1.4)
    scene.collection.objects.link(cam)
    tc = cam.constraints.new("TRACK_TO")
    tc.target, tc.track_axis, tc.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
    scene.camera = cam
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.rotation_euler = (0.8, 0.2, 0.6)
    scene.collection.objects.link(sun)
    scene.world = bpy.data.worlds.new("W")
    scene.world.use_nodes = True
    r = scene.render
    r.engine = "BLENDER_EEVEE_NEXT"
    r.resolution_x = r.resolution_y = 480
    r.filepath = os.path.join(OUT, f"canopy_{label}.png")
    scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"[canopy] {r.filepath}")
