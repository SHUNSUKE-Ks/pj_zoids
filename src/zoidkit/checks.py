"""動きの自動検査。Blender が実際に解いた結果(IK込み)を、フレームを進めながら測る。"""
import bpy


def foot_slide_report(scene, arm, legs, contact_z, frames=None):
    """接地点(指の付け根)のワールド位置を追い、
    - 接地中の水平速度(=足滑り)。目安: 0.05 m/s 以下
    - 最低の高さ(=地面へのめり込み)。目安: -0.02 m 以上
    を脚ごとに返す。接地判定は高さ contact_z 以下。"""
    fps = scene.render.fps
    rng = frames or range(scene.frame_start, scene.frame_end + 1)
    prev = {}
    res = {leg.name: {"max_slide": 0.0, "sum": 0.0, "n": 0, "min_z": 9.0} for leg in legs}
    for f in rng:
        scene.frame_set(f)
        for leg in legs:
            p = arm.matrix_world @ arm.pose.bones[f"{leg.name}_toe"].head
            r = res[leg.name]
            r["min_z"] = min(r["min_z"], p.z)
            q = prev.get(leg.name)
            if q is not None and p.z < contact_z and q.z < contact_z:
                v = ((p.xy - q.xy).length) * fps
                r["max_slide"] = max(r["max_slide"], v)
                r["sum"] += v; r["n"] += 1
            prev[leg.name] = p.copy()
    for name, r in res.items():
        r["mean_slide"] = r["sum"] / r["n"] if r["n"] else 0.0
    return res


def print_report(res, slide_ok=0.05, sink_ok=-0.02):
    ok = True
    for name, r in res.items():
        good = r["mean_slide"] <= slide_ok and r["min_z"] >= sink_ok
        ok &= good
        print(f"[check] {name}: 足滑り 平均{r['mean_slide']:.3f} 最大{r['max_slide']:.3f} m/s"
              f" / 最低高さ {r['min_z']:+.3f} m  {'OK' if good else 'NG'}")
    print(f"[check] 総合: {'OK' if ok else 'NG'}")
    return ok
