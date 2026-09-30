"""コマンドウルフ(アーバイン仕様)。四足・趾行性(つま先立ち)・狼型。

座標: +Y が前、+X が右、+Z が上。単位はm。
形は「プロキシ(部品の塊)」の段階: シルエット・関節位置・可動の確認用。細部の造形はまだ入れない。
設計判断の記録は docs/knowledge/ 、評価は docs/review_*.md 。
"""
import math
from mathutils import Matrix, Vector
from zoidkit.geom import frame, rot_about, make_materials, Parts
from zoidkit.leg import LegSpec, DamperSpec, rest_chain, damper_points, solve_knee, OVEREXTEND
from zoidkit.gait import Gait, FPS, foot_pose
from zoidkit.rig import (leg_bone_defs, build_armature, add_leg_constraints, calibrate_pole_angle,
                         Keyer, move_root_linear)

NAME = "CommandWolf"

COL = {  # 色, roughness, metallic   アーバイン仕様: 黒に近いガンメタ + 赤 + 白キャップ
    "gray": ((0.06, 0.062, 0.068), 0.55, 0.2), "dark": ((0.015, 0.015, 0.017), 0.5, 0.3),
    "red": ((0.30, 0.015, 0.01), 0.45, 0.0), "metal": ((0.6, 0.6, 0.62), 0.25, 0.9),
    "glass": ((1.0, 0.45, 0.02), 0.2, 0.0), "light": ((0.11, 0.115, 0.125), 0.6, 0.1),
    "white": ((0.8, 0.8, 0.78), 0.5, 0.0),
}

# ---------- 骨格 ----------
P = {  # 胴・首・頭・尾・砲の関節位置(静止姿勢)
    "body0": Vector((0, -1.0, 1.5)), "spine": Vector((0, 0.0, 1.5)), "chest1": Vector((0, 1.0, 1.5)),
    "neck": Vector((0, 1.2, 1.75)), "head": Vector((0, 1.6, 1.82)), "headtip": Vector((0, 2.75, 1.62)),
    "jaw": Vector((0, 2.15, 1.47)), "jawtip": Vector((0, 2.95, 1.45)),
    "tail1": Vector((0, -1.2, 1.65)), "tail2": Vector((0, -2.0, 1.75)), "tailtip": Vector((0, -3.0, 1.6)),
    "cannon": Vector((0, -0.1, 2.3)), "cannontip": Vector((0, 0.7, 2.35)),
}
HEAD_SHIFT = Vector((0, -0.30, -0.33))   # 頭部の部品を Ver1.1 の座標から移す量
TOP_SHIFT = Vector((0, 0, -0.25))        # 背中の装備・尾の部品を Ver1.1 の座標から移す量


def _leg(name, x, y, bend, girdle, scapula):
    return LegSpec(name, Vector((x, y, 1.38)), bend, girdle, l1=0.80, l2=0.80, ankle_z=0.30,
                   toe=Vector((0, 0.42, -0.20)), tip=Vector((0, 0.35, 0.0)),
                   scapula=Vector((x, 0.95, 1.85)) if scapula else None)


LEGS = [  # 前脚は肩甲骨あり(踏み出しを伸ばす)、後脚は骨盤に直付け
    _leg("FL", -0.45, 1.1, -1, "chest", True), _leg("FR", 0.45, 1.1, -1, "chest", True),
    _leg("RL", -0.45, -1.1, +1, "body", False), _leg("RR", 0.45, -1.1, +1, "body", False),
]
FRONT = ("FL", "FR")
DAMPERS = [DamperSpec("d1", "thigh", 0.30, "shin", 0.62, 0.31),
           DamperSpec("d2", "shin", 0.72, "foot", 0.35, 0.25)]
CONTACT_Z = 0.105  # 接地点(指の付け根)がこの高さ以下なら接地とみなす(静止時 0.10)。広いと振り上げ直後を誤検出する


# ---------- 歩容 ----------
def _trot_motion(p):
    return 0.07 * math.cos(4 * math.pi * p), 0.035 * math.sin(4 * math.pi * p + 0.6), 0.0


def _gallop_motion(p):
    """ロータリー・ギャロップ: 後脚で蹴る→伸びきり→前脚で着地→背を丸めて収縮。"""
    dz = 0.10 * math.cos(4 * math.pi * (p - 0.375))
    pitch = 0.09 * math.sin(2 * math.pi * (p - 0.2))
    flex = 0.14 * math.cos(2 * math.pi * (p - 0.40))    # 収縮時に背が丸まる
    return dz, pitch, flex


GAITS = {
    "trot": Gait("trot", 4.5, 20, 0.5, {"FL": 0.0, "RR": 0.0, "FR": 0.5, "RL": 0.5}, 0.45, _trot_motion,
                 heel=0.35, scapula=0.15),
    # 後脚(RR→RL)がほぼ同時に着地 → 前脚(FL→FR)が時間差で着地する
    "gallop": Gait("gallop", 7.5, 16, 0.35, {"RR": 0.0, "RL": 0.10, "FL": 0.45, "FR": 0.55}, 0.50,
                   _gallop_motion, head_freq=1, jaw=(0.20, 0.15)),
}


# ---------- 組み立て ----------
def bone_defs():
    defs = [
        ("root", (0, 0, 0), (0, 0.6, 0), None, False),
        ("body", P["body0"], P["spine"], "root", True),          # 骨盤側(後半身)
        ("chest", P["spine"], P["chest1"], "body", True),        # 胸側(前半身)。背骨の曲げ用
        ("neck", P["neck"], P["head"], "chest", True),
        ("head", P["head"], P["headtip"], "neck", True),
        ("jaw", P["jaw"], P["jawtip"], "head", True),
        ("cannon", P["cannon"], P["cannontip"], "body", True),
        ("tail1", P["tail1"], P["tail2"], "body", True),
        ("tail2", P["tail2"], P["tailtip"], "tail1", True),
    ]
    for leg in LEGS:
        defs += leg_bone_defs(leg, DAMPERS)
    return defs


def build(scene):
    arm = build_armature(scene, NAME, bone_defs())
    for leg in LEGS:
        add_leg_constraints(arm, leg, DAMPERS)
    make_model(scene, arm)
    calibrate_pole_angle(arm, LEGS)
    return arm


def make_model(scene, arm):
    mats = make_materials(COL, "CW_")
    pt = Parts()

    # 胴体: 後半身(body) と 前半身(chest)。背骨の位置(y=0)で分かれる。厚み 1.0m(腹 1.0 〜 背 2.0)
    pt.hull("body", "gray", [(0.50, -1.4, 1.95), (0.44, -1.4, 1.1), (0.56, 0.06, 2.02), (0.52, 0.06, 1.0)])
    pt.hull("chest", "gray", [(0.56, -0.06, 2.02), (0.52, -0.06, 1.0), (0.62, 0.95, 2.05),
                              (0.54, 0.95, 1.02), (0.42, 1.35, 1.95), (0.32, 1.38, 1.25)])
    pt.hull("chest", "dark", [(0.40, 1.15, 2.05), (0.38, 1.15, 1.3), (0.30, 1.6, 1.95), (0.26, 1.55, 1.45)])  # 首カバー
    pt.box("body", "dark", (0, -0.55, 1.02), (0.7, 1.4, 0.18))           # 腹部フレーム
    pt.box("chest", "dark", (0, 0.6, 1.02), (0.7, 1.2, 0.18))
    pt.cyl("body", "dark", (0, 0.0, 1.5), (1, 0, 0), 0.34, 0.98)         # 背骨の関節

    pt.off = TOP_SHIFT                                                    # 背中の装備
    pt.box("body", "dark", (0, -0.6, 2.3), (0.85, 1.1, 0.3))             # バックパック
    for sx in (-1, 1):
        pt.cyl("body", "metal", (sx * 0.5, -0.65, 2.55), (0, 1, 0), 0.075, 1.9)   # 2連装ビーム砲
        pt.cyl("body", "metal", (sx * 0.5, -0.65, 2.3), (0, 1, 0), 0.075, 1.9)
        pt.box("body", "dark", (sx * 0.5, -0.55, 2.42), (0.22, 0.7, 0.55))
        pt.box("body", "red", (sx * 0.58, -0.7, 2.0), (0.14, 0.6, 0.5))
    pt.off = Vector((0, 0, 0))

    # 脚: [肩甲骨] - 大腿 - 膝 - すね - 足首 - 足(中足) - 指(肉球) + ダンパー2組
    for leg in LEGS:
        L, ch = leg.name, rest_chain(leg)
        hip, knee, ankle, ball = ch["hip"], ch["knee"], ch["ankle"], ch["ball"]
        side = Vector((leg.side, 0, 0))
        cover = f"{L}_shoulder" if leg.scapula is not None else leg.girdle
        pt.cyl(cover, "dark", hip + 0.29 * side, (1, 0, 0), 0.40, 0.16)      # 股関節カバー
        pt.cyl(cover, "white", hip + 0.38 * side, (1, 0, 0), 0.13, 0.04)
        if leg.scapula is not None:
            pt.box(cover, "red", Vector((leg.side * 0.66, 0.85, 1.75)), (0.14, 0.95, 0.75))  # 肩装甲(赤)
        th, sh, ft, to = f"{L}_thigh", f"{L}_shin", f"{L}_foot", f"{L}_toe"
        pt.limb(th, "gray", hip, knee, 0.46, 0.50)
        pt.limb(sh, "dark", knee, ankle, 0.30, 0.32)
        pt.limb(sh, "gray", knee.lerp(ankle, 0.12) + 0.17 * side, knee.lerp(ankle, 0.80) + 0.17 * side,
                0.08, 0.34)                                                  # すね外装
        pt.cyl(th, "dark", knee, (1, 0, 0), 0.22, 0.52)                      # 膝関節
        pt.cyl(th, "white", knee + 0.27 * side, (1, 0, 0), 0.10, 0.04)
        pt.cyl(sh, "dark", ankle, (1, 0, 0), 0.15, 0.40)                     # 足首関節
        pt.cyl(sh, "white", ankle + 0.21 * side, (1, 0, 0), 0.09, 0.04)
        pt.limb(ft, "light", ankle, ball, 0.40, 0.26)                        # 中足(甲)
        pt.box(to, "light", ball + Vector((0, 0.02, -0.01)), (0.44, 0.36, 0.18))   # 肉球ブロック
        pt.box(to, "dark", ball + Vector((0, 0.0, -0.085)), (0.40, 0.32, 0.03))    # パッド(接地面)
        for cx in (-0.15, -0.05, 0.05, 0.15):
            pt.box(to, "light", ball + Vector((cx, 0.24, -0.03)), (0.09, 0.14, 0.12))
            pt.cone(to, "dark", ball + Vector((cx, 0.33, -0.05)), (0, 1, -0.4), 0.035, 0.12)
        for sp in DAMPERS:                                                   # 筒とロッドは伸縮せず、重なりが変わる
            pa, pb = damper_points(leg, ch, sp)
            d = pb - pa
            rot = frame((0, 0, 0), d).to_3x3().to_4x4()
            pt.box(f"{L}_{sp.upper}", "dark", pa, (0.10, 0.12, 0.12), rot=rot)    # 取り付け金具
            pt.box(f"{L}_{sp.lower}", "dark", pb, (0.10, 0.12, 0.12), rot=rot)
            pt.cyl(f"{L}_{sp.tag}_cyl", "dark", pa + 0.325 * d, d, 0.075, 0.65 * d.length)
            pt.cyl(f"{L}_{sp.tag}_rod", "metal", pb - 0.325 * d, d, 0.04, 0.65 * d.length)

    # 首・頭
    pt.limb("neck", "gray", P["neck"], P["head"], 0.5, 0.5)
    for sx in (-1, 1):
        pt.cyl("neck", "dark", P["neck"].lerp(P["head"], 0.5) + Vector((sx * 0.3, 0, 0.18)),
               P["head"] - P["neck"], 0.05, 0.6)                               # 動力パイプ
    pt.off = HEAD_SHIFT
    pt.hull("head", "gray", [(0.32, 1.95, 2.32), (0.34, 1.95, 1.85), (0.30, 2.6, 2.22),
                             (0.28, 2.6, 1.9), (0.14, 3.25, 2.05), (0.14, 3.3, 1.88)])   # 頭部
    pt.hull("head", "glass", [(0.24, 2.2, 2.30), (0.24, 2.85, 2.12), (0.14, 2.3, 2.52), (0.12, 2.75, 2.32)])  # キャノピー
    pt.hull("head", "gray", [(0.12, 1.98, 2.30), (0.32, 1.98, 2.30), (0.22, 2.15, 2.32), (0.22, 2.05, 2.80)])  # 耳
    pt.hull("head", "light", [(0.34, 2.15, 2.0), (0.36, 2.6, 2.0), (0.36, 2.55, 1.82), (0.34, 2.1, 1.82)])  # 頬装甲
    pt.hull("jaw", "dark", [(0.22, 2.45, 1.84), (0.22, 2.45, 1.70), (0.10, 3.25, 1.84), (0.10, 3.25, 1.74)])  # 下あご
    for sx in (-1, 1):
        pt.cone("head", "white", (sx * 0.11, 3.2, 1.78), (0, 0, -1), 0.03, 0.16)  # 牙

    pt.off = TOP_SHIFT                                                    # 背部砲(長砲身)
    pt.hull("cannon", "dark", [(0.4, -0.5, 2.55), (0.4, 0.3, 2.55), (0.3, -0.5, 3.05), (0.22, 0.3, 2.95)])
    pt.box("cannon", "dark", (0, 1.7, 2.95), (0.30, 3.8, 0.2), rot=Matrix.Rotation(0.03, 4, "X"))
    pt.cyl("cannon", "metal", (0, 1.9, 2.75), (0, 1, 0), 0.06, 3.8)
    pt.cyl("cannon", "metal", (0.18, 1.3, 2.83), (0, 1, 0), 0.05, 2.6)

    pt.off = Vector((0, 0, 0))                                            # 尾
    pt.limb("tail1", "gray", P["tail1"], P["tail2"], 0.28, 0.28)
    pt.off = TOP_SHIFT
    pt.hull("tail2", "dark", [(0.08, -2.0, 2.2), (0.08, -2.0, 1.8), (0.06, -3.0, 2.1), (0.06, -3.0, 1.75)])

    pt.build(scene, arm, mats)


# ---------- アニメーション ----------
def pose_frame(k, g, ph, f):
    """位相 ph のポーズを作り、フレーム f にキーを打つ。"""
    k.begin()
    w = 2 * math.pi * ph
    hw = w * g.head_freq
    dz, pitch, flex = g.motion(ph % 1.0)
    Tb = Matrix.Translation((0, 0, dz)) @ rot_about(P["spine"], "X", pitch)
    Tc = Tb @ rot_about(P["spine"], "X", flex)              # 前半身 = 後半身 + 背骨の曲げ

    k.put("root", Matrix.Identity(4), f)
    k.put("body", Tb, f)
    k.put("chest", Tc, f)
    # 頭の安定化: 胴の傾きを首で打ち消し、頭はほぼ水平を保つ(狼は走るとき頭を低く保つ)
    Tn = Tc @ rot_about(P["neck"], "X", -0.9 * (pitch + flex) + 0.03 * math.sin(hw + 1.5))
    k.put("neck", Tn, f)
    Th = Tn @ rot_about(P["head"], "X", 0.02 * math.sin(hw + 2.4))
    k.put("head", Th, f)
    k.put("jaw", Th @ rot_about(P["jaw"], "X", g.jaw[0] + g.jaw[1] * math.sin(w)), f)
    k.put("cannon", Tb @ rot_about(P["cannon"], "Z", 0.08 * math.sin(w)) @
          rot_about(P["cannon"], "X", 0.03 * math.sin(2 * w)), f)
    # 尾: 後方へ水平に流し、横の振りは小さく(遅れて付いてくる)
    T1 = Tb @ rot_about(P["tail1"], "Z", 0.09 * math.sin(w)) @ rot_about(P["tail1"], "X", -1.2 * pitch)
    k.put("tail1", T1, f)
    k.put("tail2", T1 @ rot_about(P["tail2"], "Z", 0.12 * math.sin(w - 0.9)), f)

    for leg in LEGS:
        L, ch = leg.name, rest_chain(leg)
        T = Tc if L in FRONT else Tb
        fp = foot_pose(g, leg, ch["ball"], ph)
        if leg.scapula is not None:                          # 肩甲骨: 足が前にあるほど前へ振る
            Ts = T @ rot_about(leg.scapula, "X", g.scapula * max(-1.0, min(1.0, fp.reach)))
            k.put(f"{L}_shoulder", Ts, f)
            hip = Ts @ ch["hip"]
        else:
            hip = T @ ch["hip"]
        solve_knee(hip, fp.ankle, leg.l1, leg.l2, leg.bend)  # 届くかの検査だけ(脚は Blender の IK が解く)
        k.key(f"IK_{L}", frame(fp.ankle, fp.ankle + Matrix.Rotation(fp.foot_pitch, 3, "X") @ leg.toe), f)
        k.local_rot(f"{L}_toe", (1, 0, 0), fp.toe_pitch - fp.foot_pitch, f)   # 指は世界基準の角度にする


def animate(scene, arm, frames, gait="gallop", direction=None):
    """gait: GAITS のキー。direction: (x, y) で進行方向を上書き(例 (1,0)=右横ステップ)。"""
    g = GAITS[gait]
    if direction is not None:
        g = g.with_dir(direction)
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, frames
    OVEREXTEND["count"] = 0
    k = Keyer(arm)
    for f in range(1, frames + 1):
        pose_frame(k, g, (f - 1) / g.cycle, f)
    move_root_linear(arm, g.direction, g.speed, frames, FPS)
    print(f"[gait] {g.name} dir={g.dir} stride={g.stride:.2f}m 脚の伸びきり={OVEREXTEND['count']}回")
    return g
