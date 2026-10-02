# pj_zoids — AIエージェント向けの入口

ゾイド「コマンドウルフ」を Blender 4.4 で、**画面を開かずに Python から**生成・アニメーション・書き出しするプロジェクト。

## 最初に読む
1. `docs/codex/blender_cli_handbook.md` … Blender CLI の使い方、このリポジトリの全コマンド、守るべき約束
2. `docs/codex/genai_3d_cli.md` … 3D生成AI(Hunyuan3D 等)を MCP を使わず CLI で扱う手順
3. `docs/knowledge/README.md` … 設計判断と、動きの仮説・検証の記録

## 守ること
- Blender MCP は使わない。すべて `tools/bl.ps1`(ヘッドレス実行)で行う
- 生成物はすべて `src/` のコードから再生成できる状態を保つ。`.blend` を手で編集して終わりにしない
- 変更したら `src/check_motion.py` を実行し、`[check] 総合: OK` を確認する
- `out/` は生成物置き場(git 管理外)。API キーや生成AIの出力モデルはコミットしない
- 動きや形の判断を変えたら `docs/knowledge/04_motion_hypotheses.md` に「仮説・判断・評価・結果」で追記する
