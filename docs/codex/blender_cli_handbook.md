# Blender CLI ハンドブック（Codex 向け）

Blender の画面を開かずに、コマンドラインから Python で操作する方法と、このリポジトリでの使い方。

## 1. 仕組み

```
blender.exe -b [開く.blend] --factory-startup --python <スクリプト.py> --python-exit-code 1 -- <スクリプトへの引数>
```

| オプション | 意味 |
|---|---|
| `-b` | 画面なし(バックグラウンド)で起動 |
| `.blend` のパス | 開くファイル。省略すると空のシーン |
| `--factory-startup` | ユーザー設定・アドオンを読まない(結果を毎回同じにする) |
| `--python <file>` | スクリプトを実行 |
| `--python-expr "<code>"` | 1行のコードを実行(このリポジトリでは import パスの追加に使う) |
| `--python-exit-code 1` | スクリプトが例外で落ちたら終了コード 1 を返す(失敗を検知できる) |
| `--` | これより後ろはスクリプトの引数。スクリプト内では `sys.argv[sys.argv.index("--")+1:]` |

- Blender は自前の Python を内蔵している。`bpy`(Blender の API)と `mathutils` はその中でだけ import できる
- 環境変数 `PYTHONPATH` は読まれないので、`--python-expr "import sys; sys.path.insert(0, 'src')"` で import パスを足す
- 代わりに `pip install bpy` で通常の Python から Blender を使う方法もある(Python のバージョンを Blender に合わせる必要がある)。このリポジトリでは使っていない

## 2. このリポジトリのラッパー: `tools/bl.ps1`

上のコマンドを毎回書かずに済むようにしたもの。Blender の場所は環境変数 `BLENDER_EXE`、なければ `C:\Program Files\Blender Foundation\Blender 4.4\blender.exe`。

```powershell
.\tools\bl.ps1 <スクリプト> [-- 引数...]                 # 空のシーンで実行
.\tools\bl.ps1 -Blend <.blend> <スクリプト> [-- 引数...] # .blend を開いて実行
```

## 3. コマンド一覧

| 目的 | コマンド | 出力 |
|---|---|---|
| デモシーンを作る | `.\tools\bl.ps1 src\build_demo.py [-- フレーム数 歩容 方向x 方向y]` | `out/demo.blend` |
| 動きの検査 | `.\tools\bl.ps1 -Blend out\demo.blend src\check_motion.py` | `[check] 総合: OK/NG` (NG なら終了コード 1) |
| 接地と胴の高さの表 | `.\tools\bl.ps1 -Blend out\demo.blend src\diag_timing.py` | 標準出力 |
| 4面図 | `.\tools\bl.ps1 -Blend out\demo.blend src\review_shots.py` | `out/review/*.png` |
| 歩行のコマ割り | `.\tools\bl.ps1 -Blend out\demo.blend src\gait_sheet.py [-- コマ数 開始 間隔]` | `out/sheet/*.png` |
| 部位の寄り | `.\tools\bl.ps1 -Blend out\demo.blend src\closeup.py -- <骨名> <フレーム...>` | `out/closeup/*.png` |
| キャノピー開閉 | `.\tools\bl.ps1 src\canopy_test.py` | `out/canopy_*.png` |
| 静止画 | `.\tools\bl.ps1 -Blend out\demo.blend src\render_preview.py [-- フレーム...]` | `out/preview_*.png` |
| 動画 | `.\tools\bl.ps1 -Blend out\demo.blend src\render_video.py` | `out/zoids_demo.mp4` (約5分) |
| .glb 書き出し | `.\tools\bl.ps1 -Blend out\demo.blend src\export_glb.py [-- 出力パス]` | `out/CommandWolf.glb` |
| 参考モデル取り込み | `.\tools\bl.ps1 -Blend out\demo.blend src\import_reference.py -- <モデル> [全長 ずらし Z回転 保存先]` | `out/with_reference.blend` |

画像を1枚にまとめるときは ImageMagick:
`magick montage out\review\*.png -tile 2x -geometry +2+2 out\review_sheet.png`

歩容の例: `-- 240 gallop`(既定)、`-- 240 trot`、`-- 240 trot 1 0`(右への横ステップ)、`-- 240 gallop 0.7 0.7`(斜め前)

## 4. コードの構成

| 場所 | 中身 |
|---|---|
| `src/common.py` | ルートパス、引数の取得、シーン初期化、保存 |
| `src/zoidkit/` | 種類に依存しない共通部品: 行列・部品メッシュ(geom)、脚とIK(leg)、歩容と足の軌道(gait)、リグ生成とキー打ち(rig)、検査(checks) |
| `src/species/command_wolf.py` | コマンドウルフ固有: 関節位置 `P`、脚 `LEGS`、歩容 `GAITS`、部品 `make_model`、ポーズ `pose_frame` |
| `src/field.py` | 草原・空・太陽・岩と木 |
| `src/build_demo.py` 他 | 上の表の実行スクリプト |

## 5. bpy で守る約束（これを破ると壊れる / 環境依存になる）

1. **シェーダーのノードは名前でなく type で探す**。UI が日本語だと名前が変わる
   `next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")`
2. **列挙値(enum)を決め打ちしない**。版で変わる。迷ったら一覧を読む
   `[i.identifier for i in prop.bl_rna.properties["file_format"].enum_items]`
   - 描画エンジンは例外的に一覧に出ない。Blender 4.4 の EEVEE は `"BLENDER_EEVEE_NEXT"`
3. **骨の姿勢は `pose_bone.matrix = M` で入れない**。親の評価前だとずれる。`zoidkit/rig.py` の `Keyer` を使う(親から見た値を自前で計算する)
4. **骨の編集は Edit モードで**。`bpy.ops.object.mode_set(mode="EDIT")` → `edit_bones` を変更 → `"OBJECT"` に戻す
5. **IK の Pole Angle は脚ごとに違う**。`calibrate_pole_angle` が自動で決める(狼: 前脚 -90°、後脚 +90°)
6. **評価結果を読むには `scene.frame_set(f)`** してから `pose_bone.head` などを読む(IK・制約込みの結果になる)
7. 部品は「骨と同じ名前の頂点グループ(重み1.0) + Armature モディファイア」で骨に付く(`Parts.build`)

## 6. 作業の型

```
コード変更 → build_demo → check_motion(OK を確認) → review_shots / gait_sheet / closeup で目視 → 記録 → コミット
```
- 画像は自分で開いて確認する(例: 生成した PNG を読む)。数値の検査だけで終わらせない
- 動画は時間がかかるので最後に1回
