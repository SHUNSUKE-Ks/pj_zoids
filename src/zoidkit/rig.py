"""アーマチュアの生成、脚のIKコントロール、ダンパー制約、キー打ち。

リグの方式(組み合わせ方式):
  - 胴・首・頭・尾・肩甲骨・指 … Python が計算してキーを打つ
  - 脚(大腿・すね)            … Blender の IK 制約が解く。Python は IK ターゲット骨にだけキーを打つ
  - 足(中足)                  … IK ターゲットの回転をコピー(Copy Rotation)
  - ダンパー                   … 筒とロッドが互いを向き合う(Damped Track)。キー不要
→ コマンド1つで再生成でき、GUI では IK ターゲットを掴んで足の位置を手直しできる。
"""
import math
import bpy
from mathutils import Matrix, Quaternion, Vector
from .geom import frame
from .leg import rest_chain, damper_points


# ---------- 骨の定義 ----------
def leg_bone_defs(leg, dampers):
    """脚1本ぶんの骨定義 [(名前, head, tail, 親, 変形するか)]。"""
    L = leg.name
    ch = rest_chain(leg)
    defs = []
    if leg.scapula is not None:
        defs.append((f"{L}_shoulder", leg.scapula, ch["hip"], leg.girdle, True))
    defs += [
        (f"{L}_thigh", ch["hip"], ch["knee"], leg.thigh_parent, True),
        (f"{L}_shin", ch["knee"], ch["ankle"], f"{L}_thigh", True),
        (f"{L}_foot", ch["ankle"], ch["ball"], f"{L}_shin", True),
        (f"{L}_toe", ch["ball"], ch["tip"], f"{L}_foot", True),
        # コントロール骨(変形しない)
        (f"IK_{L}", ch["ankle"], ch["ball"], "root", False),
    ]
    pole = ch["knee"] + Vector((0, leg.bend * 0.9, 0))           # 膝を曲げたい側に置く
    defs.append((f"POLE_{L}", pole, pole + Vector((0, 0, 0.25)), leg.girdle, False))
    for sp in dampers:
        pa, pb = damper_points(leg, ch, sp)
        defs.append((f"{L}_{sp.tag}_cyl", pa, pa + 0.65 * (pb - pa), f"{L}_{sp.upper}", True))
        defs.append((f"{L}_{sp.tag}_rod", pb, pb + 0.65 * (pa - pb), f"{L}_{sp.lower}", True))
    return defs


def build_armature(scene, name, defs):
    """骨定義からアーマチュアを作る。変形しない骨は "Controls" コレクションへ。"""
    data = bpy.data.armatures.new(f"{name}Rig")
    arm = bpy.data.objects.new(name, data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones
    for n, head, tail, parent, deform in defs:
        b = eb.new(n)
        b.head, b.tail = Vector(head), Vector(tail)
        b.matrix = frame(head, tail)
        b.use_deform = deform
        if parent:
            b.parent = eb[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    ctrl = data.collections.new("Controls")
    deform = data.collections.new("Deform")
    for n, *_rest, dfm in defs:
        (deform if dfm else ctrl).assign(data.bones[n])
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    data.display_type = "STICK"
    return arm


# ---------- 制約 ----------
def add_leg_constraints(arm, leg, dampers):
    L = leg.name
    pb = arm.pose.bones
    ik = pb[f"{L}_shin"].constraints.new("IK")
    ik.target, ik.subtarget = arm, f"IK_{L}"
    ik.pole_target, ik.pole_subtarget = arm, f"POLE_{L}"
    ik.chain_count = 2                      # すね + 大腿 だけを解く(肩甲骨はキーで動かす)
    cr = pb[f"{L}_foot"].constraints.new("COPY_ROTATION")
    cr.target, cr.subtarget = arm, f"IK_{L}"
    for sp in dampers:
        for a, b in ((f"{L}_{sp.tag}_cyl", f"{L}_{sp.tag}_rod"), (f"{L}_{sp.tag}_rod", f"{L}_{sp.tag}_cyl")):
            dt = pb[a].constraints.new("DAMPED_TRACK")
            dt.target, dt.subtarget, dt.head_tail = arm, b, 0.0


def calibrate_pole_angle(arm, legs):
    """IK の Pole Angle を、脚ごとに「静止姿勢で膝が動かない値」に決める。
    Pole Angle は「骨のローカルX軸」と「ポールの向き」のずれなので、骨のロールと膝の曲がる向きで値が変わる
    (この狼では前脚 -90°、後脚 +90°)。候補を試して誤差最小を選ぶ。"""
    pb = arm.pose.bones
    result = {}
    for leg in legs:
        con = pb[f"{leg.name}_shin"].constraints["IK"]
        errs = []
        for deg in (0, 90, -90, 180):
            con.pole_angle = math.radians(deg)
            bpy.context.view_layer.update()
            errs.append(((pb[f"{leg.name}_thigh"].tail - rest_chain(leg)["knee"]).length, deg))
        err, deg = min(errs)
        con.pole_angle = math.radians(deg)
        result[leg.name] = deg
        print(f"[rig] {leg.name} pole_angle={deg}° 静止姿勢の膝のずれ={err:.4f}m")
    bpy.context.view_layer.update()
    return result


# ---------- キー打ち ----------
class Keyer:
    """「この骨をアーマチュア空間でこの姿勢にしたい(M)」から、骨のポーズ値を計算してキーを打つ。
    ポーズ値は親から見た相対値なので:  P_bone = P_parent @ (rest_parent⁻¹ @ rest_bone) @ basis
    → basis = (rest_parent⁻¹ @ rest_bone)⁻¹ @ P_parent⁻¹ @ M
    同じフレーム内では、親を先にキーしておく(self.world に親の姿勢が入る)。"""

    def __init__(self, arm):
        self.arm = arm
        self.rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}
        self.world = {}

    def begin(self):
        self.world = {}

    def key(self, name, M, frame_no):
        b = self.arm.pose.bones[name]
        par = b.parent
        if par is None:
            basis = self.rest[name].inverted() @ M
        else:
            P = self.world.get(par.name, self.rest[par.name])
            offset = self.rest[par.name].inverted() @ self.rest[name]
            basis = offset.inverted() @ P.inverted() @ M
        self.world[name] = M
        loc, quat, _ = basis.decompose()
        b.location, b.rotation_quaternion = loc, quat
        b.keyframe_insert("location", frame=frame_no)
        b.keyframe_insert("rotation_quaternion", frame=frame_no)

    def put(self, name, T, frame_no):
        """静止姿勢に変換 T を掛けた姿勢でキーを打つ。"""
        self.key(name, T @ self.rest[name], frame_no)

    def local_rot(self, name, axis, ang, frame_no):
        """親に対するローカル回転だけでキーを打つ(IKで動く骨の子など、親の姿勢が分からない骨用)。"""
        b = self.arm.pose.bones[name]
        b.location = (0, 0, 0)
        b.rotation_quaternion = Quaternion(Vector(axis), ang)
        b.keyframe_insert("location", frame=frame_no)
        b.keyframe_insert("rotation_quaternion", frame=frame_no)


def move_root_linear(arm, direction, speed, frames, fps):
    """アーマチュア本体を一定速度で進める(足の接地速度と一致させる)。"""
    for f in (1, frames):
        arm.location = direction * (speed * (f - 1) / fps)
        arm.keyframe_insert("location", frame=f)
    for fc in arm.animation_data.action.fcurves:
        if fc.data_path == "location":
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
