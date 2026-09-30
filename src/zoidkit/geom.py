"""行列ヘルパー、部品メッシュ、材質。"""
import bpy, bmesh
from mathutils import Matrix, Vector
from common import principled


def frame(head, tail, up=(1, 0, 0)):
    """head→tail を Y 軸、up に最も近い方向を X 軸とする4x4行列(原点=head)。
    Blender の骨と同じ「骨の向き=ローカルY」の約束に合わせてある。"""
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
    """点 p を中心に axis 軸まわりへ ang 回す4x4行列。"""
    p = Vector(p)
    return Matrix.Translation(p) @ Matrix.Rotation(ang, 4, axis) @ Matrix.Translation(-p)


def make_materials(colors, prefix):
    """colors: {名前: ((r,g,b), roughness, metallic)}。"glass" は発光を足す。"""
    out = {}
    for k, (c, r, m) in colors.items():
        mat = bpy.data.materials.new(f"{prefix}{k}")
        mat.use_nodes = True
        b = principled(mat)
        b.inputs["Base Color"].default_value = (*c, 1)
        b.inputs["Roughness"].default_value = r
        b.inputs["Metallic"].default_value = m
        if k == "glass":
            b.inputs["Emission Color"].default_value = (*c, 1)
            b.inputs["Emission Strength"].default_value = 0.6
        out[k] = mat
    return out


class Parts:
    """(骨, 材質) ごとに bmesh を貯めて最後にオブジェクト化する(剛体スキニング)。
    座標はすべて静止姿勢のアーマチュア空間。"""

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
        """部品ごとにオブジェクトを作り、骨と同じ名前の頂点グループ(重み1.0)で骨に付ける。"""
        for (bone, mat), bm in self.bms.items():
            name = f"{bone}_{mat}"
            me = bpy.data.meshes.new(name)
            bm.to_mesh(me); bm.free()
            ob = bpy.data.objects.new(name, me)
            ob.data.materials.append(mats[mat])
            ob.vertex_groups.new(name=bone).add(list(range(len(me.vertices))), 1.0, "REPLACE")
            md = ob.modifiers.new("Armature", "ARMATURE"); md.object = arm
            scene.collection.objects.link(ob)
            ob.parent = arm
