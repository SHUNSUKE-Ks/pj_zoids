# 3D生成AI を MCP なしで使う（CLI 手順・Codex 向け）

Blender MCP は「Blender の画面を開き、アドオンで接続した状態」でしか生成AIを呼べない。
ここでは **生成AIの呼び出しと Blender を切り離し**、どちらもコマンドラインで動かす。

```
① 生成(普通の Python / ブラウザ)   → out/genai/<名前>.glb
② 取り込み(Blender CLI)             → src/import_reference.py で大きさ・位置を揃えて並べる
③ 見比べ(Blender CLI)               → review_shots.py の4面図で、自作の塊と並べて確認
```

## 1. 生成AIの選択肢

| 名前 | 提供元 | CLI からの使い方 | 費用・前提 |
|---|---|---|---|
| **Hunyuan3D**(フンユエン3D) | Tencent | (a) オープンソース版をローカルで実行 (b) Hugging Face の公開デモを `gradio_client` で呼ぶ (c) Tencent Cloud の API | (a) NVIDIA GPU が必要 (b) 無料だが混雑・回数制限あり (c) Tencent の登録とキー |
| **Tripo** | VAST | REST API | 登録とキー。無料枠あり(条件は公式で確認) |
| **Hyper3D Rodin** | Deemos | REST API | 登録とキー |

> 料金・無料枠・API の細部は変わりやすい。**実装前に必ず公式ドキュメントで確認する**。ここに書いた API 名や引数は「確認すべき項目」の目安であり、動作保証はない。

### 推奨の順
1. **(b) Hugging Face の公開デモ** … 登録なしで試せる。品質の当たりを付けるのに向く
2. **(a) ローカル実行** … GPU があれば回数制限なし。再現性も上げやすい
3. (c) や Tripo/Rodin の API … 継続して使うと決めてから

## 2. 手順

### 2-1. 下調べ（Codex がやること）
```powershell
nvidia-smi                      # GPU の有無と VRAM。ローカル実行(a)ができるかの判断
python --version                # 生成側は通常の Python(Blender 内蔵の Python とは別)
```

### 2-2. (b) Hugging Face の公開デモを呼ぶ
```powershell
python -m venv .venv-genai
.\.venv-genai\Scripts\pip install gradio_client
```
```python
# tools/genai_hf.py の骨子(未検証。API 名と引数は view_api() の結果で確定させる)
from gradio_client import Client, handle_file
client = Client("tencent/Hunyuan3D-2")       # Space 名は Hugging Face で確認する
client.view_api()                            # ← まずこれを実行し、使える関数と引数を読む
# result = client.predict(handle_file("references/cw_01.webp"), api_name="/<確認した名前>")
# 返ってきたファイル(.glb など)を out/genai/ にコピーする
```
- 入力画像は**背景のない1体だけの画像**がよい(`references/cw_01.webp` は背景が透過で向いている)
- 混雑時は待たされる・失敗する。タイムアウトと再試行を入れる

### 2-3. (a) ローカルで実行
- GitHub の `Tencent/Hunyuan3D-2`(または後継の版)の README の手順に従う
- 形だけの生成と、質感(テクスチャ)付きの生成で必要な VRAM が違う。README の数値を確認し、`nvidia-smi` の結果と照らす
- 出力を `out/genai/<名前>.glb` に置く

### 2-4. Blender に取り込んで見比べる
```powershell
.\tools\bl.ps1 src\build_demo.py
.\tools\bl.ps1 -Blend out\demo.blend src\import_reference.py -- out/genai/cw_hunyuan.glb 6.0 8.0 0
.\tools\bl.ps1 -Blend out\with_reference.blend src\review_shots.py
```
- 第2引数 `6.0` … 水平方向の長い辺をこの長さ(m)にそろえる(コマンドウルフの全長に合わせる)
- 第3引数 `8.0` … 横(+X)へずらす距離。並べて見比べるため
- 第4引数 `0` … Z 軸の回転(度)。生成物の正面が +Y(前)を向くように合わせる。横を向いていたら `90` か `-90`
- 4面図の撮影範囲から外れる場合は、ずらしを小さくするか `review_shots.py` の正投影の幅を広げる

## 3. 生成物の使い方（重要）
- 生成物は**1体丸ごとの一体成形**。関節で切ると断面に穴が開き、回すと隙間が出るので、**リグには載せない**
- 使い道は「**形の参考**」: 頭部のくさびの角度、キャノピーの大きさ、装甲の厚みなどを見比べ、`src/species/command_wolf.py` の塊の数値を直す
- 部品単位で外部AIに作り込ませる場合の条件は `docs/knowledge/05_handoff.md`

## 4. 守ること
- API キーは環境変数で渡す(例 `$env:TRIPO_API_KEY`)。コードやリポジトリに書かない
- 生成物(`out/genai/`)はコミットしない。各サービスの利用規約で、出力の扱い(商用可否・公開可否)を確認する
- ゾイドは著作物。参考画像と生成物は個人の学習・制作の範囲で扱う
- 生成を何回・どの設定で行い、何が分かったかを `docs/knowledge/04_motion_hypotheses.md` か `docs/review_*.md` に残す
