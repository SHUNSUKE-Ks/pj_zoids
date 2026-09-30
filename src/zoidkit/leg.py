"""脚の定義と2リンクIK。四足の前脚・後脚、二足の脚に共通で使う。

脚の骨の並び(付け根→先):
  [shoulder(肩甲骨・任意)] → thigh(大腿/上腕) → shin(すね/前腕) → foot(中足) → toe(指・肉球)
  股関節=hip, 膝=knee, 足首=ankle, 指の付け根(接地点)=ball, 指先=tip
"""
import math
from dataclasses import dataclass
from mathutils import Vector

OVEREXTEND = {"count": 0}   # 脚が伸びきって足が目標に届かなかった回数(=足が滑る原因)


@dataclass
class LegSpec:
    name: str               # 例 "FL"
    hip: Vector             # 股関節(肩関節)の静止位置
    bend: int               # 膝の曲がり方向: +1=前へ(犬の後脚) / -1=後ろへ(犬の前脚)
    girdle: str             # 付け根の骨(四足なら前脚=chest, 後脚=body)
    l1: float               # 大腿の長さ
    l2: float               # すねの長さ
    ankle_z: float          # 静止時の足首の高さ
    toe: Vector             # 足首→指の付け根(静止時)
    tip: Vector             # 指の付け根→指先(静止時)
    scapula: Vector = None  # 肩甲骨の回転中心。None なら肩甲骨なし(股関節が胴に直付け)
    fold: float = 1.0       # 遊脚で足首をたたむ量の倍率(犬の前脚は手首を大きく折る)

    @property
    def side(self):
        return 1 if self.hip.x > 0 else -1

    @property
    def thigh_parent(self):
        return f"{self.name}_shoulder" if self.scapula is not None else self.girdle


def solve_knee(hip, ankle, l1, l2, bend):
    """2リンクIK(3D)。膝は hip→ankle の線を軸に、+Y側(bend=+1)か -Y側(bend=-1)へ曲げる。
    余弦定理: hip から膝までの「線に沿った距離 a」と「線からの高さ h」を出す。"""
    d_vec = ankle - hip
    if d_vec.length > l1 + l2 - 1e-4:
        OVEREXTEND["count"] += 1
    d = min(d_vec.length, l1 + l2 - 1e-4)
    u = d_vec.normalized()
    a = (l1 ** 2 - l2 ** 2 + d ** 2) / (2 * d)
    h = math.sqrt(max(l1 ** 2 - a ** 2, 0))
    n = Vector((0, 1, 0)) - Vector((0, 1, 0)).dot(u) * u
    n = n.normalized() if n.length > 1e-4 else Vector((1, 0, 0))
    return hip + a * u + bend * h * n


def rest_chain(leg):
    """静止姿勢の関節位置 {hip, knee, ankle, ball, tip}。"""
    hip = leg.hip.copy()
    ankle = Vector((hip.x, hip.y, leg.ankle_z))
    knee = solve_knee(hip, ankle, leg.l1, leg.l2, leg.bend)
    ball = ankle + leg.toe
    return {"hip": hip, "knee": knee, "ankle": ankle, "ball": ball, "tip": ball + leg.tip}


def segments(ch):
    """骨ごとの (始点, 終点)。ダンパーの取り付け位置の計算に使う。"""
    return {"thigh": (ch["hip"], ch["knee"]), "shin": (ch["knee"], ch["ankle"]),
            "foot": (ch["ankle"], ch["ball"])}


@dataclass
class DamperSpec:
    """油圧ダンパー: 上側の骨の途中 と 下側の骨の途中 を、筒(cyl)とロッド(rod)でつなぐ。"""
    tag: str
    upper: str        # 筒を付ける骨の部位 ("thigh" など)
    upper_at: float   # その骨の上の位置 0..1
    lower: str        # ロッドを付ける骨の部位
    lower_at: float
    offset: float     # 脚の外側へのずらし量


def damper_points(leg, ch, spec):
    """ダンパー両端の位置(筒側, ロッド側)。"""
    seg = segments(ch)
    o = Vector((leg.side * spec.offset, 0, 0))
    a0, a1 = seg[spec.upper]
    b0, b1 = seg[spec.lower]
    return a0.lerp(a1, spec.upper_at) + o, b0.lerp(b1, spec.lower_at) + o
