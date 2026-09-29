"""緑一面の草原。地面・空・太陽と、動きが分かる目印（岩と低ポリの木）。"""
import math, random
import bpy, bmesh
from mathutils import Matrix, Vector
from common import principled

FIELD_SIZE = 400  # m


def _mat(name, color, rough=0.9):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = principled(m)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    return m


def _grass_material():
    mat = bpy.data.materials.new("Grass")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = principled(mat)
    bsdf.inputs["Roughness"].default_value = 0.95
    tex = nt.nodes.new("ShaderNodeTexCoord")
    n_big = nt.nodes.new("ShaderNodeTexNoise"); n_big.inputs["Scale"].default_value = 0.08
    n_small = nt.nodes.new("ShaderNodeTexNoise"); n_small.inputs["Scale"].default_value = 1.5
    n_fine = nt.nodes.new("ShaderNodeTexNoise"); n_fine.inputs["Scale"].default_value = 12.0
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "FLOAT"; mix.inputs[0].default_value = 0.35
    mix2 = nt.nodes.new("ShaderNodeMix"); mix2.data_type = "FLOAT"; mix2.inputs[0].default_value = 0.3
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.03, 0.18, 0.02, 1)
    ramp.color_ramp.elements[1].color = (0.14, 0.38, 0.05, 1)
    for n in (n_big, n_small, n_fine):
        nt.links.new(tex.outputs["Object"], n.inputs["Vector"])
    nt.links.new(n_big.outputs["Fac"], mix.inputs[2])
    nt.links.new(n_small.outputs["Fac"], mix.inputs[3])
    nt.links.new(mix.outputs[0], mix2.inputs[2])
    nt.links.new(n_fine.outputs["Fac"], mix2.inputs[3])
    nt.links.new(mix2.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def _scatter(scene, seed=7):
    """走行方向(+Y)に沿って岩と木を散らす。走路(|x|<7)は空ける。"""
    rnd = random.Random(seed)
    rock_m = _mat("Rock", (0.32, 0.31, 0.29))
    trunk_m = _mat("Trunk", (0.22, 0.13, 0.07))
    leaf_m = _mat("Leaf", (0.05, 0.25, 0.06))
    bm_rock, bm_trunk, bm_leaf = bmesh.new(), bmesh.new(), bmesh.new()
    for _ in range(160):
        x = rnd.uniform(-60, 60); y = rnd.uniform(-30, 160)
        if abs(x) < 7:
            continue
        s = rnd.uniform(0.3, 1.2)
        M = Matrix.Translation((x, y, s * 0.3)) @ Matrix.Rotation(rnd.uniform(0, 6.28), 4, "Z") \
            @ Matrix.Diagonal((s * 1.3, s, s * 0.7, 1))
        bmesh.ops.create_icosphere(bm_rock, subdivisions=1, radius=1.0, matrix=M)
    for _ in range(45):
        x = rnd.uniform(-70, 70); y = rnd.uniform(-30, 170)
        if abs(x) < 9:
            continue
        h = rnd.uniform(3, 6)
        bmesh.ops.create_cone(bm_trunk, cap_ends=True, segments=6, radius1=0.22, radius2=0.16,
                              depth=h * 0.5, matrix=Matrix.Translation((x, y, h * 0.25)))
        for k in range(3):
            r = h * (0.42 - 0.09 * k)
            bmesh.ops.create_cone(bm_leaf, cap_ends=True, segments=7, radius1=r, radius2=0.0,
                                  depth=h * 0.5, matrix=Matrix.Translation((x, y, h * (0.45 + 0.22 * k))))
    for name, bm, m in (("Rocks", bm_rock, rock_m), ("TrunkS", bm_trunk, trunk_m), ("Leaves", bm_leaf, leaf_m)):
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        ob = bpy.data.objects.new(name, me); ob.data.materials.append(m)
        scene.collection.objects.link(ob)


def make_field(scene):
    scene.unit_settings.system = "METRIC"
    bpy.ops.mesh.primitive_plane_add(size=FIELD_SIZE, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "Field"
    ground.data.materials.append(_grass_material())

    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    scene.world = world
    sky = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    sky.inputs["Color"].default_value = (0.42, 0.62, 0.95, 1)
    sky.inputs["Strength"].default_value = 1.0

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 4.5
    sun_data.angle = math.radians(3)
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    scene.collection.objects.link(sun)
    _scatter(scene)
