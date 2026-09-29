"""緑一面の草原フィールドを生成して out/field.blend に保存する。"""
import bpy
from common import *

FIELD_SIZE = 400  # m

scene = reset_scene()
scene.unit_settings.system = "METRIC"

# --- 地面 ---
bpy.ops.mesh.primitive_plane_add(size=FIELD_SIZE, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Field"

mat = bpy.data.materials.new("Grass")
mat.use_nodes = True
nt = mat.node_tree
bsdf = principled(mat)
bsdf.inputs["Roughness"].default_value = 0.95

# 大小2段のノイズで草の色むらをつける
tex = nt.nodes.new("ShaderNodeTexCoord")
n_big = nt.nodes.new("ShaderNodeTexNoise"); n_big.inputs["Scale"].default_value = 0.08
n_small = nt.nodes.new("ShaderNodeTexNoise"); n_small.inputs["Scale"].default_value = 1.5
mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "FLOAT"; mix.inputs[0].default_value = 0.3
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (0.04, 0.22, 0.03, 1)
ramp.color_ramp.elements[1].color = (0.16, 0.42, 0.06, 1)
nt.links.new(tex.outputs["Object"], n_big.inputs["Vector"])
nt.links.new(tex.outputs["Object"], n_small.inputs["Vector"])
nt.links.new(n_big.outputs["Fac"], mix.inputs[2])
nt.links.new(n_small.outputs["Fac"], mix.inputs[3])
nt.links.new(mix.outputs[0], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
ground.data.materials.append(mat)

# --- 空と太陽 ---
world = bpy.data.worlds.new("Sky")
world.use_nodes = True
scene.world = world
sky = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
sky.inputs["Color"].default_value = (0.45, 0.65, 0.95, 1)
sky.inputs["Strength"].default_value = 1.0

sun_data = bpy.data.lights.new("Sun", "SUN")
sun_data.energy = 4.0
sun = bpy.data.objects.new("Sun", sun_data)
sun.rotation_euler = (0.9, 0.2, 0.6)
scene.collection.objects.link(sun)

save("out/field.blend")
