"""コマンドウルフ(アーバイン仕様) 低ポリ + リグ + 走行アニメーション。

座標: +Y が前、+X が右、+Z が上。単位はm。
モデルは静止姿勢のワールド座標で作り、ボーン別の頂点グループ + Armatureモディファイアで動かす。
足は「胴体に対して後ろへ流れる速度 = 進行速度」で計算するので、接地した足は地面で滑らない。
"""
import math
import bpy, bmesh
from mathutils import Matrix, Vector
from common import principled

FPS = 30
CYCLE = 20            # 1歩行周期のフレーム数
SPEED = 5.4           # m/s (アーマチュア本体をこの速度で前進させる)
DUTY = 0.5            # 接地時間の割合(トロット)
STRIDE = SPEED * DUTY * CYCLE / FPS   # 接地中に足が胴体に対して動く距離
L1 = L2 = 0.85        # 大腿・すねの長さ
ANKLE_Z = 0.40
LIFT = 0.55
TOE = Vector((0, 0.5, -0.3))          # 足首→つま先(静止時)

HIPS = {  # 名前: (x, y, z, 膝の曲がり方向 +1=前 / -1=後ろ)
    "FL": (-0.62, 1.15, 1.6, -1), "FR": (0.62, 1.15, 1.6, -1),
    "RL": (-0.62, -1.15, 1.6, +1), "RR": (0.62, -1.15, 1.6, +1),
}
PHASE = {"FL": 0.0, "RR": 0.0, "FR": 0.5, "RL": 0.5}   # 対角ペアで動く

COL = {  # 色, roughness, metallic
    "gray": ((0.30, 0.32, 0.35), 0.6, 0.0), "dark": ((0.04, 0.04, 0.05), 0.5, 0.3),
    "red": ((0.55, 0.05, 0.04), 0.5, 0.0), "metal": ((0.5, 0.5, 0.52), 0.3, 0.9),
    "glass": ((1.0, 0.45, 0.02), 0.2, 0.0), "light": ((0.55, 0.57, 0.6), 0.6, 0.0),
}

P = {  # 関節位置(静止姿勢)
    "neck": Vector((0, 1.15, 2.0)), "head": Vector((0, 1.9, 2.15)), "headtip": Vector((0, 3.05, 1.95)),
    "tail1": Vector((0, -1.2, 1.9)), "tail2": Vector((0, -2.0, 2.0)), "tailtip": Vector((0, -3.0, 1.85)),
    "cannon": Vector((0, -0.1, 2.55)), "cannontip": Vector((0, 0.7, 2.6)),
    "body0": Vector((0, -1.0, 1.75)), "body1": Vector((0, 1.0, 1.75)),
}
BODY_CENTER = Vector((0, 0, 1.75))


# ---------- 幾何ヘルパー ----------
def frame(head, tail, up=(1, 0, 0)):
    """head→tail を Y 軸、up に最も近い方向を X 軸とする4x4行列(原点=head)。"""
    head, tail = Vector(head), Vector(tail)
    y = (tail - head).normalized()
    x = Vector(up) - Vector(up).dot(y) * y
    if x.length < 1e-6:
        x = Vector((0, 0, 1)) - Vector((0, 0, 1)).dot(y) * y
    x.normalize()
    z = x.cross(y)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = head
    return m


def rot_about(p, axis, ang):
    p = Vector(p)
    return Matrix.Translation(p) @ Matrix.Rotation(ang, 4, axis) @ Matrix.Translation(-p)


class Parts:
    """(ボーン, マテリアル) ごとに bmesh を貯めて最後にオブジェクト化する。"""
    def __init__(self):
        self.bms = {}

    def _bm(self, bone, mat):
        return self.bms.setdefault((bone, mat), bmesh.new())

    def box(self, bone, mat, center, size, rot=None):
        M = Matrix.Translation(center)
        if rot is not None:
            M = M @ rot
        bmesh.ops.create_cube(self._bm(bone, mat), size=1.0, matrix=M @ Matrix.Diagonal((*size, 1)))

    def limb(self, bone, mat, p0, p1, wx, wz):
        """p0→p1 に沿う直方体(長さ方向がY、幅wx、厚みwz)。"""
        M = frame(p0, p1)
        M.translation = (Vector(p0) + Vector(p1)) / 2
        length = (Vector(p1) - Vector(p0)).length
        bmesh.ops.create_cube(self._bm(bone, mat), size=1.0, matrix=M @ Matrix.Diagonal((wx, length, wz, 1)))

    def cyl(self, bone, mat, center, axis, r, length, r2=None):
        q = Vector(axis).to_track_quat("Z", "Y").to_matrix().to_4x4()
        bmesh.ops.create_cone(self._bm(bone, mat), cap_ends=True, segments=14, radius1=r,
                              radius2=r if r2 is None else r2, depth=length,
                              matrix=Matrix.Translation(center) @ q)

    def cone(self, bone, mat, center, axis, r, length):
        self.cyl(bone, mat, center, axis, r, length, r2=0.0)

    def build(self, scene, arm, mats):
        for (bone, mat), bm in self.bms.items():
            me = bpy.data.meshes.new(f"{bone}_{mat}")
            bm.to_mesh(me); bm.free()
            ob = bpy.data.objects.new(f"{bone}_{mat}", me)
            ob.data.materials.append(mats[mat])
            ob.vertex_groups.new(name=bone).add(list(range(len(me.vertices))), 1.0, "REPLACE")
            md = ob.modifiers.new("Armature", "ARMATURE"); md.object = arm
            scene.collection.objects.link(ob)
            ob.parent = arm


def make_materials():
    out = {}
    for k, (c, r, m) in COL.items():
        mat = bpy.data.materials.new(f"CW_{k}")
        mat.use_nodes = True
        b = principled(mat)
        b.inputs["Base Color"].default_value = (*c, 1)
        b.inputs["Roughness"].default_value = r
        b.inputs["Metallic"].default_value = m
        if k == "glass":
            b.inputs["Emission Color"].default_value = (1.0, 0.4, 0.0, 1)
            b.inputs["Emission Strength"].default_value = 0.6
        out[k] = mat
    return out


# ---------- 脚IK ----------
def solve_leg(hip, ankle, sign):
    """YZ平面の2リンクIK。hip/ankle は Vector(x,y,z)。膝位置を返す。"""
    h2 = Vector((hip.y, hip.z)); a2 = Vector((ankle.y, ankle.z))
    d = min((a2 - h2).length, L1 + L2 - 1e-4)
    u = (a2 - h2).normalized()
    a = (L1 ** 2 - L2 ** 2 + d ** 2) / (2 * d)
    h = math.sqrt(max(L1 ** 2 - a ** 2, 0))
    n = Vector((-u.y, u.x))     # 下向きの u に対して +Y を向く
    k = h2 + a * u + sign * h * n
    return Vector((hip.x, k.x, k.y))


def rest_leg(name):
    x, y, z, s = HIPS[name]
    hip = Vector((x, y, z)); ankle = Vector((x, y, ANKLE_Z))
    return hip, solve_leg(hip, ankle, s), ankle, ankle + TOE


# ---------- モデル ----------
def make_rig(scene):
    arm_data = bpy.data.armatures.new("WolfRig")
    arm = bpy.data.objects.new("CommandWolf", arm_data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def bone(name, head, tail, parent=None):
        b = eb.new(name)
        b.head, b.tail = Vector(head), Vector(tail)
        b.matrix = frame(head, tail)
        if parent:
            b.parent = eb[parent]

    bone("root", (0, 0, 0), (0, 0.6, 0))
    bone("body", P["body0"], P["body1"], "root")
    bone("neck", P["neck"], P["head"], "body")
    bone("head", P["head"], P["headtip"], "neck")
    bone("cannon", P["cannon"], P["cannontip"], "body")
    bone("tail1", P["tail1"], P["tail2"], "body")
    bone("tail2", P["tail2"], P["tailtip"], "tail1")
    for n in HIPS:
        hip, knee, ankle, toe = rest_leg(n)
        bone(f"{n}_thigh", hip, knee, "body")
        bone(f"{n}_shin", knee, ankle, f"{n}_thigh")
        bone(f"{n}_foot", ankle, toe, f"{n}_shin")
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def make_model(scene, arm):
    mats = make_materials()
    pt = Parts()

    # 胴体
    pt.box("body", "gray", (0, 0, 1.75), (1.1, 2.5, 0.85))
    pt.box("body", "dark", (0, 0, 1.28), (0.8, 2.2, 0.25))               # 腹部フレーム
    pt.box("body", "dark", (0, -0.35, 2.28), (0.85, 1.3, 0.3))           # バックパック
    pt.box("body", "gray", (0, 0.55, 2.2), (0.9, 0.7, 0.3))
    for sx in (-1, 1):
        pt.cyl("body", "metal", (sx * 0.5, -0.55, 2.55), (0, 1, 0), 0.075, 1.9)   # 2連装ビーム砲
        pt.cyl("body", "metal", (sx * 0.5, -0.55, 2.3), (0, 1, 0), 0.075, 1.9)
        pt.box("body", "dark", (sx * 0.5, -0.45, 2.42), (0.22, 0.7, 0.55))
        pt.box("body", "red", (sx * 0.62, 0.95, 2.0), (0.14, 0.95, 0.75))        # 肩装甲(赤)
        pt.box("body", "red", (sx * 0.62, -0.05, 2.02), (0.14, 0.55, 0.5))
        for hy in (1.15, -1.15):
            pt.cyl("body", "dark", (sx * 0.75, hy, 1.6), (1, 0, 0), 0.42, 0.25)  # 股関節ディスク
            pt.cyl("body", "metal", (sx * 0.9, hy, 1.6), (1, 0, 0), 0.16, 0.1)

    # 脚(4本とも同じ構造)
    for name in HIPS:
        hip, knee, ankle, toe = rest_leg(name)
        th, sh, ft = f"{name}_thigh", f"{name}_shin", f"{name}_foot"
        pt.limb(th, "gray", hip, knee, 0.30, 0.34)
        pt.limb(sh, "dark", knee, ankle, 0.20, 0.22)
        pt.cyl(th, "dark", knee, (1, 0, 0), 0.19, 0.36)                      # 膝ダンパー
        pt.cyl(sh, "metal", ankle, (1, 0, 0), 0.13, 0.32)
        pt.limb(ft, "light", ankle, toe, 0.36, 0.30)
        for cx in (-0.11, 0.0, 0.11):
            pt.cone(ft, "dark", toe + Vector((cx, 0.10, -0.02)), (0, 1, -0.3), 0.045, 0.2)

    # 首・頭
    pt.limb("neck", "gray", P["neck"], P["head"], 0.5, 0.5)
    pt.cyl("neck", "dark", P["neck"] + Vector((0, 0.1, 0.2)), (1, 0, 0), 0.3, 0.55)
    pt.box("head", "gray", (0, 2.4, 2.1), (0.62, 1.0, 0.55))                 # 頭蓋
    pt.box("head", "gray", (0, 3.0, 1.95), (0.36, 0.7, 0.28))                # 鼻先
    pt.box("head", "dark", (0, 2.95, 1.72), (0.30, 0.8, 0.12))               # 下あご
    pt.box("head", "glass", (0, 2.5, 2.42), (0.46, 0.75, 0.18), rot=Matrix.Rotation(-0.25, 4, "X"))  # キャノピー
    for sx in (-1, 1):
        pt.box("head", "gray", (sx * 0.24, 2.05, 2.5), (0.1, 0.3, 0.4), rot=Matrix.Rotation(0.3, 4, "X"))  # 耳
        pt.box("head", "gray", (sx * 0.28, 2.6, 2.02), (0.1, 0.9, 0.35))     # 頬装甲
        pt.cone("head", "light", (sx * 0.1, 3.15, 1.78), (0, 0, -1), 0.03, 0.15)  # 牙

    # 背部砲(長砲身)
    pt.box("cannon", "dark", (0, -0.1, 2.72), (0.8, 0.9, 0.35))
    pt.box("cannon", "dark", (0, -0.15, 3.0), (0.5, 0.7, 0.3))
    pt.box("cannon", "dark", (0, 1.7, 2.95), (0.30, 3.8, 0.2), rot=Matrix.Rotation(0.03, 4, "X"))
    pt.cyl("cannon", "metal", (0, 1.9, 2.75), (0, 1, 0), 0.06, 3.8)
    pt.cyl("cannon", "metal", (0.18, 1.3, 2.83), (0, 1, 0), 0.05, 2.6)

    # 尾
    pt.limb("tail1", "gray", P["tail1"], P["tail2"], 0.28, 0.28)
    pt.limb("tail2", "dark", P["tail2"], P["tailtip"], 0.16, 0.55)

    pt.build(scene, arm, mats)


# ---------- アニメーション ----------
def smooth(t):
    return t * t * (3 - 2 * t)


def foot_target(name, f):
    """歩行位相 f(フレーム数)での足首位置(Vector)と足の角度。"""
    x, y0, _, _ = HIPS[name]
    p = (f / CYCLE + PHASE[name]) % 1.0
    if p < DUTY:                                   # 接地: 胴体に対して後ろへ流れる
        t = p / DUTY
        return Vector((x, y0 + STRIDE / 2 * (1 - 2 * t), ANKLE_Z)), 0.0
    t = (p - DUTY) / (1 - DUTY)                    # 遊脚: 前へ振り出す
    y = y0 - STRIDE / 2 + STRIDE * smooth(t)
    return Vector((x, y, ANKLE_Z + LIFT * math.sin(math.pi * t))), 0.7 * math.sin(math.pi * t)


def pose_frame(arm, rest, ph, key):
    """位相 ph のポーズを作り、キーフレーム key に打つ。"""
    pb = arm.pose.bones
    world = {}
    w = 2 * math.pi * ph / CYCLE
    dz = 0.07 * math.cos(2 * w)
    pitch = 0.035 * math.sin(2 * w + 0.6)
    Tb = Matrix.Translation((0, 0, dz)) @ rot_about(BODY_CENTER, "X", pitch)

    def set_key(name, M):
        """M(アーマチュア空間の目標姿勢)から親相対のチャンネル値を自前で計算して書き込む。
        P_b = P_parent @ (rest_parent^-1 @ rest_b) @ basis"""
        b = pb[name]
        par = b.parent
        if par is None:
            basis = rest[name].inverted() @ M
        else:
            offset = rest[par.name].inverted() @ rest[name]
            basis = offset.inverted() @ world[par.name].inverted() @ M
        world[name] = M
        loc, quat, _ = basis.decompose()
        b.location, b.rotation_quaternion = loc, quat
        b.keyframe_insert("location", frame=key)
        b.keyframe_insert("rotation_quaternion", frame=key)

    def put(name, T):
        set_key(name, T @ rest[name])

    put("root", Matrix.Identity(4))
    put("body", Tb)
    Tn = Tb @ rot_about(P["neck"], "X", -1.6 * pitch + 0.06 * math.sin(2 * w + 1.5))
    put("neck", Tn)
    put("head", Tn @ rot_about(P["head"], "X", 0.9 * pitch + 0.05 * math.sin(2 * w + 2.4)))
    put("cannon", Tb @ rot_about(P["cannon"], "Z", 0.12 * math.sin(w)) @
        rot_about(P["cannon"], "X", 0.03 * math.sin(2 * w)))
    T1 = Tb @ rot_about(P["tail1"], "Z", 0.28 * math.sin(w)) @ rot_about(P["tail1"], "X", -0.2 * pitch * 6)
    put("tail1", T1)
    put("tail2", T1 @ rot_about(P["tail2"], "Z", 0.35 * math.sin(w - 0.9)))

    for n in HIPS:
        x, y, z, s = HIPS[n]
        hip = Tb @ Vector((x, y, z))
        ankle, ang = foot_target(n, ph)
        knee = solve_leg(hip, ankle, s)
        toe = ankle + Matrix.Rotation(ang, 3, "X") @ TOE
        set_key(f"{n}_thigh", frame(hip, knee))
        set_key(f"{n}_shin", frame(knee, ankle))
        set_key(f"{n}_foot", frame(ankle, toe))


def animate(scene, arm, frames):
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, frames
    rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}
    for b in arm.pose.bones:
        b.rotation_mode = "QUATERNION"
    for f in range(1, frames + 1):
        pose_frame(arm, rest, f - 1, f)
    # 本体を一定速度で前進(足の接地速度と一致)
    for f, y in ((1, 0.0), (frames, SPEED * (frames - 1) / FPS)):
        arm.location = (0, y, 0)
        arm.keyframe_insert("location", frame=f)
    for fc in arm.animation_data.action.fcurves:
        if fc.data_path == "location":
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
