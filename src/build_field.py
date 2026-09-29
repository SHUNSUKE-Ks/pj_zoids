"""草原だけのシーンを out/field.blend に保存する。"""
from common import *
from field import make_field

scene = reset_scene()
make_field(scene)
save("out/field.blend")
