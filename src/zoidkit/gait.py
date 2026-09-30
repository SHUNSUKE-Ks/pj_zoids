"""歩容と足の軌道。

足の軌道は「接地点(指の付け根 ball)」を主役にして作る:
  接地(stance): ball は地面に固定 = 胴体から見ると進行速度で後ろへ流れる → 足が滑らない
                終盤は ball を支点にかかとを上げる(蹴り出し)
  遊脚(swing) : ball を前へ振り出し、持ち上げる。足先は前半たたみ、後半は前へ伸ばす
足首の位置は ball から逆算する(ankle = ball - 回転した足の向き)。
"""
import math
from dataclasses import dataclass, field
from mathutils import Matrix, Vector

FPS = 30


@dataclass
class Gait:
    name: str
    speed: float           # m/s
    cycle: int             # 1周期のフレーム数
    duty: float            # 接地時間の割合(0.5以上=どこかの足が常に接地、未満=浮く時間あり)
    phase: dict            # 脚ごとの位相のずれ(0..1)
    lift: float            # 遊脚の持ち上げ高さ
    motion: object         # p(0..1) -> (胴の上下, 胴のピッチ, 背骨の曲げ)  ※種類ごとに定義
    head_freq: int = 2     # 首・頭の上下が1周期に何回か
    jaw: tuple = (0.05, 0.0)  # あごの開き(基準, 振幅)
    dir: tuple = (0.0, 1.0)   # 進行方向(x=右, y=前)。胴体は +Y を向いたまま進む
    heel: float = 0.45     # 蹴り出しでかかとを上げる角度(rad)
    heel_from: float = 0.65  # 接地期間のどこから蹴り出すか(0..1)
    flex: float = 0.8      # 遊脚前半に足先をたたむ量(rad)
    reach: float = 0.25    # 遊脚後半に足先を前へ伸ばす量(rad)
    curl: float = 0.6      # 遊脚中に指を丸める量(rad)
    scapula: float = 0.22  # 肩甲骨の振り(rad)。足が前にあるほど前へ

    @property
    def stride(self):      # 接地中に足が胴体に対して動く距離
        return self.speed * self.duty * self.cycle / FPS

    @property
    def direction(self):
        return Vector((self.dir[0], self.dir[1], 0.0)).normalized()

    def with_dir(self, d):
        return Gait(**{**self.__dict__, "dir": tuple(d)})


def smooth(t):
    return t * t * (3 - 2 * t)


@dataclass
class FootPose:
    ankle: Vector     # 足首の位置(アーマチュア空間。IKターゲットの位置)
    foot_pitch: float # 足(中足)の回転。静止姿勢からの差(X軸まわり、負=かかとが上がる)
    toe_pitch: float  # 指の回転(世界基準。0=地面に平ら)
    ball: Vector      # 接地点
    reach: float      # 足が前後どこにあるか(-1=最後方 .. +1=最前方)。肩甲骨の振りに使う
    stance: bool


def foot_pose(g, leg, ball_rest, ph):
    """位相 ph(周期の何倍か) における足の姿勢。ball_rest は静止時の接地点。"""
    d = g.direction
    half = g.stride / 2
    p = (ph + g.phase[leg.name]) % 1.0
    if p < g.duty:                                           # 接地
        t = p / g.duty
        ball = ball_rest + d * (half * (1 - 2 * t))
        k = max(0.0, (t - g.heel_from) / (1 - g.heel_from))
        foot = -g.heel * smooth(k)
        toe, reach, stance = 0.0, 1 - 2 * t, True
    else:                                                    # 遊脚
        t = (p - g.duty) / (1 - g.duty)
        s = math.sin(math.pi * t)
        ball = ball_rest + d * (-half + g.stride * smooth(t))
        ball.z = ball_rest.z + g.lift * s
        foot = -g.heel * (1 - smooth(t)) - g.flex * s * (1 - t) + g.reach * s * t
        toe, reach, stance = -g.curl * s, -1 + 2 * smooth(t), False
    ankle = ball - Matrix.Rotation(foot, 3, "X") @ leg.toe
    return FootPose(ankle, foot, toe, ball, reach, stance)
