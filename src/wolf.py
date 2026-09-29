"""コマンドウルフ(アーバイン仕様) 低ポリ + リグ + 歩容アニメーション。

座標: +Y が前、+X が右、+Z が上。単位はm。
モデルは静止姿勢のワールド座標で作り、ボーン別の頂点グループ + Armatureモディファイアで動かす。
足は「胴体に対して後ろへ流れる速度 = 進行速度」で計算するので、接地した足は地面で滑らない。
歩容(GAITS)と進行方向(dir)を差し替えるだけで、トロット/ギャロップ/横ステップ/斜めステップを作れる。
リグの解説は docs/rigging_guide.md。
"""
import math
from dataclasses import dataclass, field
import bpy, bmesh
from mathutils import Matrix, Vector
from common import principled

FPS = 30
L1 = L2 = 0.80        # 大腿・すねの長さ
ANKLE_Z = 0.30
TOE = Vector((0, 0.42, -0.20))        # 足首→つま先(静止時)

HIPS = {  # 名前: (x, y, z, 膝の曲がり方向 +1=前 / -1=後ろ)  脚は胴の真下
    "FL": (-0.45, 1.1, 1.38, -1), "FR": (0.45, 1.1, 1.38, -1),
    "RL": (-0.45, -1.1, 1.38, +1), "RR": (0.45, -1.1, 1.38, +1),
}
FRONT = ("FL", "FR")

COL = {  # 色, roughness, metallic   アーバイン仕様: 黒に近いガンメタ + 赤 + 白キャップ
    "gray": ((0.06, 0.062, 0.068), 0.55, 0.2), "dark": ((0.015, 0.015, 0.017), 0.5, 0.3),
    "red": ((0.30, 0.015, 0.01), 0.45, 0.0), "metal": ((0.6, 0.6, 0.62), 0.25, 0.9),
    "glass": ((1.0, 0.45, 0.02), 0.2, 0.0), "light": ((0.11, 0.115, 0.125), 0.6, 0.1),
    "white": ((0.8, 0.8, 0.78), 0.5, 0.0),
}

HEAD_SHIFT = Vector((0, -0.30, -0.33))   # Ver1.1 の頭部座標からの移動量(首を短く・低く)
TOP_SHIFT = Vector((0, 0, -0.25))        # Ver1.1 の背中の装備・尾の座標からの移動量(胴を低く)

P = {  # 関節位置(静止姿勢)
    "body0": Vector((0, -1.0, 1.5)), "spine": Vector((0, 0.0, 1.5)), "chest1": Vector((0, 1.0, 1.5)),
    "neck": Vector((0, 1.2, 1.75)), "head": Vector((0, 1.6, 1.82)), "headtip": Vector((0, 2.75, 1.62)),
    "jaw": Vector((0, 2.15, 1.47)), "jawtip": Vector((0, 2.95, 1.45)),
    "tail1": Vector((0, -1.2, 1.65)), "tail2": Vector((0, -2.0, 1.75)), "tailtip": Vector((0, -3.0, 1.6)),
    "cannon": Vector((0, -0.1, 2.3)), "cannontip": Vector((0, 0.7, 2.35)),
}

# 脚のダンパー(油圧シリンダー): (タグ, 上側の骨, その位置0..1, 下側の骨, その位置0..1, 外側オフセット)
# 上側の骨の部位と下側の骨の部位の間を、伸縮する筒とロッドでつなぐ。
DAMPERS = (
    ("d1", "thigh", 0.30, "shin", 0.62, 0.31),
    ("d2", "shin", 0.72, "foot", 0.35, 0.25),
)
OVEREXTEND = {"count": 0}   # 脚が伸びきって足が目標に届かなかった回数(足が滑る原因)


# ---------- 歩容 ----------
@dataclass
class Gait:
    name: str
    speed: float           # m/s
    cycle: int             # 1周期のフレーム数
    duty: float            # 接地時間の割合
    phase: dict            # 脚ごとの位相(0..1)
    lift: float            # 遊脚の持ち上げ高さ
    motion: object         # p(0..1) -> (胴の上下, 胴のピッチ, 背骨の曲げ)
    head_freq: int = 2     # 首・頭の上下が1周期に何回か
    jaw: tuple = (0.05, 0.0)  # あごの開き(基準, 振幅)
    dir: tuple = (0.0, 1.0)   # 進行方向(x=右, y=前)。胴体は常に+Yを向いたまま動く

    @property
    def stride(self):      # 接地中に足が胴体に対して動く距離
        return self.speed * self.duty * self.cycle / FPS


def _trot_motion(p):
    return 0.07 * math.cos(4 * math.pi * p), 0.035 * math.sin(4 * math.pi * p + 0.6), 0.0


def _gallop_motion(p):
    """ロータリー・ギャロップ: 後脚で蹴る→伸びきり→前脚で着地→背を丸めて収縮。"""
    dz = 0.10 * math.cos(4 * math.pi * (p - 0.375))
    pitch = 0.09 * math.sin(2 * math.pi * (p - 0.2))
    flex = 0.14 * math.cos(2 * math.pi * (p - 0.40))    # 収縮時に背が丸まる
    return dz, pitch, flex


GAITS = {
    # 脚が短くなったので stride(=速度×duty×周期秒) が脚の届く範囲に収まるよう速度と周期を合わせる
    "trot": Gait("trot", 4.5, 20, 0.5, {"FL": 0.0, "RR": 0.0, "FR": 0.5, "RL": 0.5}, 0.45, _trot_motion),
    # 後脚(RR→RL)がほぼ同時に着地 → 前脚(FL→FR)が時間差で着地する
    "gallop": Gait("gallop", 7.5, 16, 0.35, {"RR": 0.0, "RL": 0.10, "FL": 0.45, "FR": 0.55}, 0.50,
                   _gallop_motion, head_freq=1, jaw=(0.20, 0.15)),
}


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
        self.off = Vector((0, 0, 0))   # 以降に作る部品をまとめてずらす量

    def _bm(self, bone, mat):
        return self.bms.setdefault((bone, mat), bmesh.new())

    def box(self, bone, mat, center, size, rot=None):
        M = Matrix.Translation(Vector(center) + self.off)
        if rot is not None:
            M = M @ rot
        bmesh.ops.create_cube(self._bm(bone, mat), size=1.0, matrix=M @ Matrix.Diagonal((*size, 1)))

    def limb(self, bone, mat, p0, p1, wx, wz):
        """p0→p1 に沿う直方体(長さ方向がY、幅wx、厚みwz)。"""
        p0, p1 = Vector(p0) + self.off, Vector(p1) + self.off
        M = frame(p0, p1)
        M.translation = (p0 + p1) / 2
        bmesh.ops.create_cube(self._bm(bone, mat), size=1.0,
                              matrix=M @ Matrix.Diagonal((wx, (p1 - p0).length, wz, 1)))

    def hull(self, bone, mat, pts, mirror=True):
        """点群の凸包。mirror=True なら x を反転した点も足して左右対称にする。"""
        bm = self._bm(bone, mat)
        allp = []
        for p in pts:
            allp.append(Vector(p) + self.off)
            if mirror and abs(p[0]) > 1e-6:
                allp.append(Vector((-p[0], p[1], p[2])) + self.off)
        vs = [bm.verts.new(p) for p in allp]
        bmesh.ops.convex_hull(bm, input=vs)

    def cyl(self, bone, mat, center, axis, r, length, r2=None):
        q = Vector(axis).to_track_quat("Z", "Y").to_matrix().to_4x4()
        bmesh.ops.create_cone(self._bm(bone, mat), cap_ends=True, segments=12, radius1=r,
                              radius2=r if r2 is None else r2, depth=length,
                              matrix=Matrix.Translation(Vector(center) + self.off) @ q)

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
    """2リンクIK(3D)。膝は hip→ankle の線を軸に、+Y側(sign=+1)か -Y側(sign=-1)へ曲げる。"""
    d_vec = ankle - hip
    if d_vec.length > L1 + L2 - 1e-4:
        OVEREXTEND["count"] += 1
    d = min(d_vec.length, L1 + L2 - 1e-4)
    u = d_vec.normalized()
    a = (L1 ** 2 - L2 ** 2 + d ** 2) / (2 * d)
    h = math.sqrt(max(L1 ** 2 - a ** 2, 0))
    n = Vector((0, 1, 0)) - Vector((0, 1, 0)).dot(u) * u
    n = n.normalized() if n.length > 1e-4 else Vector((1, 0, 0))
    return hip + a * u + sign * h * n


def rest_leg(name):
    x, y, z, s = HIPS[name]
    hip = Vector((x, y, z)); ankle = Vector((x, y, ANKLE_Z))
    return hip, solve_leg(hip, ankle, s), ankle, ankle + TOE


def segments(leg, hip, knee, ankle, toe):
    return {"thigh": (hip, knee), "shin": (knee, ankle), "foot": (ankle, toe)}


def damper_points(leg, seg, spec):
    """ダンパー両端の位置(ワールド)。(上端, 下端)"""
    tag, ba, fa, bb, fb, off = spec
    sx = 1 if HIPS[leg][0] > 0 else -1
    o = Vector((sx * off, 0, 0))
    a0, a1 = seg[ba]; b0, b1 = seg[bb]
    return a0.lerp(a1, fa) + o, b0.lerp(b1, fb) + o


# ---------- リグ ----------
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
    bone("body", P["body0"], P["spine"], "root")          # 骨盤側(後半身)
    bone("chest", P["spine"], P["chest1"], "body")        # 胸側(前半身)。背骨の曲げ用
    bone("neck", P["neck"], P["head"], "chest")
    bone("head", P["head"], P["headtip"], "neck")
    bone("jaw", P["jaw"], P["jawtip"], "head")
    bone("cannon", P["cannon"], P["cannontip"], "body")
    bone("tail1", P["tail1"], P["tail2"], "body")
    bone("tail2", P["tail2"], P["tailtip"], "tail1")
    for n in HIPS:
        hip, knee, ankle, toe = rest_leg(n)
        par = "chest" if n in FRONT else "body"
        bone(f"{n}_thigh", hip, knee, par)
        bone(f"{n}_shin", knee, ankle, f"{n}_thigh")
        bone(f"{n}_foot", ankle, toe, f"{n}_shin")
        seg = segments(n, hip, knee, ankle, toe)
        for spec in DAMPERS:
            pa, pb_ = damper_points(n, seg, spec)
            tag = spec[0]
            bone(f"{n}_{tag}_up", pa, pa + 0.6 * (pb_ - pa), f"{n}_{spec[1]}")   # 筒
            bone(f"{n}_{tag}_lo", pb_, pb_ + 0.6 * (pa - pb_), f"{n}_{spec[3]}")  # ロッド
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


# ---------- モデル ----------
def make_model(scene, arm):
    mats = make_materials()
    pt = Parts()

    # 胴体: 後半身(body) と 前半身(chest)。背骨の位置(y=0)で分かれる。厚み 1.0m(腹 1.0 〜 背 2.0)
    pt.hull("body", "gray", [(0.50, -1.4, 1.95), (0.44, -1.4, 1.1), (0.56, 0.06, 2.02), (0.52, 0.06, 1.0)])
    pt.hull("chest", "gray", [(0.56, -0.06, 2.02), (0.52, -0.06, 1.0), (0.62, 0.95, 2.05),
                              (0.54, 0.95, 1.02), (0.42, 1.35, 1.95), (0.32, 1.38, 1.25)])
    pt.hull("chest", "dark", [(0.40, 1.15, 2.05), (0.38, 1.15, 1.3), (0.30, 1.6, 1.95), (0.26, 1.55, 1.45)])  # 首カバー
    pt.box("body", "dark", (0, -0.55, 1.02), (0.7, 1.4, 0.18))           # 腹部フレーム
    pt.box("chest", "dark", (0, 0.6, 1.02), (0.7, 1.2, 0.18))
    pt.cyl("body", "dark", (0, 0.0, 1.5), (1, 0, 0), 0.34, 0.98)         # 背骨の関節
    for sx in (-1, 1):
        for hy, bn in ((1.1, "chest"), (-1.1, "body")):
            pt.cyl(bn, "dark", (sx * 0.74, hy, 1.38), (1, 0, 0), 0.40, 0.16)     # 股関節カバー
            pt.cyl(bn, "white", (sx * 0.83, hy, 1.38), (1, 0, 0), 0.13, 0.04)

    pt.off = TOP_SHIFT                                                    # 背中の装備(Ver1.1 の座標から下げる)
    pt.box("body", "dark", (0, -0.6, 2.3), (0.85, 1.1, 0.3))             # バックパック
    for sx in (-1, 1):
        pt.cyl("body", "metal", (sx * 0.5, -0.65, 2.55), (0, 1, 0), 0.075, 1.9)   # 2連装ビーム砲
        pt.cyl("body", "metal", (sx * 0.5, -0.65, 2.3), (0, 1, 0), 0.075, 1.9)
        pt.box("body", "dark", (sx * 0.5, -0.55, 2.42), (0.22, 0.7, 0.55))
        pt.box("chest", "red", (sx * 0.66, 0.85, 2.0), (0.14, 0.95, 0.75))       # 肩装甲(赤)
        pt.box("body", "red", (sx * 0.58, -0.7, 2.0), (0.14, 0.6, 0.5))
    pt.off = Vector((0, 0, 0))

    # 脚(4本とも同じ構造): 大腿 - 膝 - すね - 足首 - 足 + ダンパー2組
    for name in HIPS:
        hip, knee, ankle, toe = rest_leg(name)
        sx = 1 if hip.x > 0 else -1
        side = Vector((sx, 0, 0))
        th, sh, ft = f"{name}_thigh", f"{name}_shin", f"{name}_foot"
        pt.limb(th, "gray", hip, knee, 0.46, 0.50)
        pt.limb(sh, "dark", knee, ankle, 0.30, 0.32)
        pt.limb(sh, "gray", knee.lerp(ankle, 0.12) + 0.17 * side, knee.lerp(ankle, 0.80) + 0.17 * side,
                0.08, 0.34)                                                  # すね外装
        pt.cyl(th, "dark", knee, (1, 0, 0), 0.22, 0.52)                      # 膝関節
        pt.cyl(th, "white", knee + 0.27 * side, (1, 0, 0), 0.10, 0.04)
        pt.cyl(sh, "dark", ankle, (1, 0, 0), 0.15, 0.40)                     # 足首関節
        pt.cyl(sh, "white", ankle + 0.21 * side, (1, 0, 0), 0.09, 0.04)
        # 足: 甲 + 四角い肉球ブロック + 指4本 + 爪
        pt.limb(ft, "light", ankle, toe, 0.40, 0.26)
        pt.box(ft, "light", toe + Vector((0, 0.02, -0.01)), (0.44, 0.36, 0.18))
        pt.box(ft, "dark", toe + Vector((0, 0.0, -0.085)), (0.40, 0.32, 0.03))   # パッド(接地面)
        for cx in (-0.15, -0.05, 0.05, 0.15):
            pt.box(ft, "light", toe + Vector((cx, 0.24, -0.03)), (0.09, 0.14, 0.12))
            pt.cone(ft, "dark", toe + Vector((cx, 0.33, -0.05)), (0, 1, -0.4), 0.035, 0.12)
        seg = segments(name, hip, knee, ankle, toe)
        for spec in DAMPERS:
            pa, pb_ = damper_points(name, seg, spec)
            tag = spec[0]
            d = pb_ - pa
            for bn, p in ((spec[1], pa), (spec[3], pb_)):                       # 取り付け金具
                pt.box(f"{name}_{bn}", "dark", p, (0.10, 0.12, 0.12), rot=frame((0, 0, 0), d).to_3x3().to_4x4())
            pt.cyl(f"{name}_{tag}_up", "dark", pa + 0.3 * d, d, 0.075, 0.6 * d.length)
            pt.cyl(f"{name}_{tag}_lo", "metal", pb_ - 0.3 * d, d, 0.04, 0.6 * d.length)

    # 首・頭
    pt.limb("neck", "gray", P["neck"], P["head"], 0.5, 0.5)
    for sx in (-1, 1):
        pt.cyl("neck", "dark", P["neck"].lerp(P["head"], 0.5) + Vector((sx * 0.3, 0, 0.18)),
               P["head"] - P["neck"], 0.05, 0.6)                               # 動力パイプ
    pt.off = HEAD_SHIFT                                                   # 頭部(Ver1.1 の座標から移動)
    pt.hull("head", "gray", [(0.32, 1.95, 2.32), (0.34, 1.95, 1.85), (0.30, 2.6, 2.22),
                             (0.28, 2.6, 1.9), (0.14, 3.25, 2.05), (0.14, 3.3, 1.88)])   # 頭部
    pt.hull("head", "glass", [(0.24, 2.2, 2.30), (0.24, 2.85, 2.12), (0.14, 2.3, 2.52), (0.12, 2.75, 2.32)])  # キャノピー
    pt.hull("head", "gray", [(0.12, 1.98, 2.30), (0.32, 1.98, 2.30), (0.22, 2.15, 2.32), (0.22, 2.05, 2.80)])  # 耳
    pt.hull("head", "light", [(0.34, 2.15, 2.0), (0.36, 2.6, 2.0), (0.36, 2.55, 1.82), (0.34, 2.1, 1.82)])  # 頬装甲
    pt.hull("jaw", "dark", [(0.22, 2.45, 1.84), (0.22, 2.45, 1.70), (0.10, 3.25, 1.84), (0.10, 3.25, 1.74)])  # 下あご
    for sx in (-1, 1):
        pt.cone("head", "white", (sx * 0.11, 3.2, 1.78), (0, 0, -1), 0.03, 0.16)  # 牙

    pt.off = TOP_SHIFT
    # 背部砲(長砲身)
    pt.hull("cannon", "dark", [(0.4, -0.5, 2.55), (0.4, 0.3, 2.55), (0.3, -0.5, 3.05), (0.22, 0.3, 2.95)])
    pt.box("cannon", "dark", (0, 1.7, 2.95), (0.30, 3.8, 0.2), rot=Matrix.Rotation(0.03, 4, "X"))
    pt.cyl("cannon", "metal", (0, 1.9, 2.75), (0, 1, 0), 0.06, 3.8)
    pt.cyl("cannon", "metal", (0.18, 1.3, 2.83), (0, 1, 0), 0.05, 2.6)

    # 尾
    pt.off = Vector((0, 0, 0))
    pt.limb("tail1", "gray", P["tail1"], P["tail2"], 0.28, 0.28)
    pt.off = TOP_SHIFT
    pt.hull("tail2", "dark", [(0.08, -2.0, 2.2), (0.08, -2.0, 1.8), (0.06, -3.0, 2.1), (0.06, -3.0, 1.75)])

    pt.build(scene, arm, mats)


# ---------- アニメーション ----------
def smooth(t):
    return t * t * (3 - 2 * t)


def foot_target(g, name, ph):
    """歩行位相 ph(周期の何倍か)での足首位置(Vector)と足の角度。
    足は進行方向 g.dir に沿って、接地中は後ろへ流れ、遊脚中は前へ振り出す。"""
    x, y0, _, _ = HIPS[name]
    d = Vector((g.dir[0], g.dir[1], 0.0)).normalized()
    base = Vector((x, y0, ANKLE_Z))
    p = (ph + g.phase[name]) % 1.0
    if p < g.duty:                                  # 接地
        t = p / g.duty
        return base + d * (g.stride / 2 * (1 - 2 * t)), 0.0
    t = (p - g.duty) / (1 - g.duty)                 # 遊脚
    pos = base + d * (-g.stride / 2 + g.stride * smooth(t))
    pos.z = ANKLE_Z + g.lift * math.sin(math.pi * t)
    return pos, 0.7 * math.sin(math.pi * t)


def pose_frame(arm, rest, g, ph, key):
    """位相 ph のポーズを作り、キーフレーム key に打つ。"""
    pb = arm.pose.bones
    world = {}
    w = 2 * math.pi * ph
    dz, pitch, flex = g.motion(ph % 1.0)
    Tb = Matrix.Translation((0, 0, dz)) @ rot_about(P["spine"], "X", pitch)
    Tc = Tb @ rot_about(P["spine"], "X", flex)          # 前半身 = 後半身 + 背骨の曲げ

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
        loc, quat, sc = basis.decompose()
        b.location, b.rotation_quaternion, b.scale = loc, quat, sc
        b.keyframe_insert("location", frame=key)
        b.keyframe_insert("rotation_quaternion", frame=key)
        b.keyframe_insert("scale", frame=key)

    def put(name, T):
        set_key(name, T @ rest[name])

    hw = w * g.head_freq
    put("root", Matrix.Identity(4))
    put("body", Tb)
    put("chest", Tc)
    Tn = Tc @ rot_about(P["neck"], "X", -1.6 * pitch - 0.8 * flex + 0.06 * math.sin(hw + 1.5))
    put("neck", Tn)
    Th = Tn @ rot_about(P["head"], "X", 0.9 * pitch + 0.05 * math.sin(hw + 2.4))
    put("head", Th)
    put("jaw", Th @ rot_about(P["jaw"], "X", g.jaw[0] + g.jaw[1] * math.sin(w)))
    put("cannon", Tb @ rot_about(P["cannon"], "Z", 0.12 * math.sin(w)) @
        rot_about(P["cannon"], "X", 0.03 * math.sin(2 * w)))
    T1 = Tb @ rot_about(P["tail1"], "Z", 0.28 * math.sin(w)) @ rot_about(P["tail1"], "X", -1.2 * pitch)
    put("tail1", T1)
    put("tail2", T1 @ rot_about(P["tail2"], "Z", 0.35 * math.sin(w - 0.9)))

    for n in HIPS:
        x, y, z, s = HIPS[n]
        hip = (Tc if n in FRONT else Tb) @ Vector((x, y, z))
        ankle, ang = foot_target(g, n, ph)
        knee = solve_leg(hip, ankle, s)
        toe = ankle + Matrix.Rotation(ang, 3, "X") @ TOE
        set_key(f"{n}_thigh", frame(hip, knee))
        set_key(f"{n}_shin", frame(knee, ankle))
        set_key(f"{n}_foot", frame(ankle, toe))
        seg = segments(n, hip, knee, ankle, toe)
        rest_seg = segments(n, *rest_leg(n))
        for spec in DAMPERS:
            pa, pb_ = damper_points(n, seg, spec)
            ra, rb = damper_points(n, rest_seg, spec)
            k = (pb_ - pa).length / (rb - ra).length      # 伸縮率
            set_key(f"{n}_{spec[0]}_up", frame(pa, pb_) @ Matrix.Diagonal((1, k, 1, 1)))
            set_key(f"{n}_{spec[0]}_lo", frame(pb_, pa) @ Matrix.Diagonal((1, k, 1, 1)))


def animate(scene, arm, frames, gait="gallop", direction=None):
    """gait: GAITS のキー。direction: (x, y) で進行方向を上書き(例 (1,0)=右横ステップ)。"""
    g = GAITS[gait]
    if direction is not None:
        g = Gait(**{**g.__dict__, "dir": tuple(direction)})
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, frames
    rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}
    for b in arm.pose.bones:
        b.rotation_mode = "QUATERNION"
    for f in range(1, frames + 1):
        pose_frame(arm, rest, g, (f - 1) / g.cycle, f)
    # 本体を一定速度で進行方向へ動かす(足の接地速度と一致)
    d = Vector((g.dir[0], g.dir[1], 0.0)).normalized()
    for f in (1, frames):
        arm.location = d * (g.speed * (f - 1) / FPS)
        arm.keyframe_insert("location", frame=f)
    for fc in arm.animation_data.action.fcurves:
        if fc.data_path == "location":
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
    print(f"[gait] {g.name} stride={g.stride:.2f}m 脚の伸びきり={OVEREXTEND['count']}回")
    return g
