# 解像度＋空潜在画像 一体化ノード 実装指示書

Nov 22, 2026 · @よしあき

## 1. 概要

ComfyUI標準の「Resolution Selector」と「Empty Latent Image」を1つにまとめたカスタムノードを新規作成する。モデル別プリセット（TOML）と任意アスペクト比に対応し、Anima・Krea 2・MOSS-Imageで共通に使えるようにする。

- 追加先：既存リポジトリ [yoshiaki-comfy](https://github.com/Yoshiaki21/yoshiaki-comfy) の1ノードとして追加する（別パッケージにはしない）
- リポジトリ直下の`CLAUDE.md`の規約に従う。本書と食い違う場合は`CLAUDE.md`を優先し、報告する
- モジュール：`modules/yoshiaki_resolution_latent/`
- `class_type`：`YoshiakiResolutionLatent`
- 表示名：`Yoshiaki-ResolutionLatent`
- `CATEGORY`：`yoshiaki-comfy/latent`（ノード追加メニューのyoshiaki-comfyの下に出る）
- 前提環境：ComfyUI 0.42.0以降（MOSS-Imageのコア対応バージョン）、Python 3.11以上（標準の`tomllib`を使う）
- 追加ライブラリ：なし（`requirements.txt`は変更しない）
- 本書は`docs/yoshiaki/ResolutionLatent_Node_指示書.md`としてリポジトリに保存する（既存の指示書と同じ扱い）

### 対象モデル

| モデル | VAE | 備考 |
| --- | --- | --- |
| Anima | Qwen-Image VAE | Cosmos系。潜在画像は5次元になる可能性あり |
| Krea 2 | Qwen-Image VAE | 推奨1〜2MP |
| MOSS-Image | FLUX.2 small VAE | **ComfyUI本体の実装のみ**対象 |

### 対象外

- MOSS-Imageのサードパーティ実装（T8パックなど、独自ソケット型`MOSS_IMAGE_LATENT`を使うもの）
- 動画モデル（フレーム数の入力は持たない）
- プリセットのホットリロード（編集後はComfyUIの再起動で反映）

## 2. ノードのUI仕様

入力欄は上からこの順に並べる。内部名は英語、画面上の表示名は日本語にする。

### 入力

| 順 | 内部名 | 表示名 | 型 | 既定値・範囲 | 説明 |
| --- | --- | --- | --- | --- | --- |
| 1 | `vae` | VAE | VAE（optional） | — | 接続すると潜在画像の形状をVAEから決める |
| 2 | `model_preset` | モデル | COMBO | プリセットの先頭 | プリセットファイルのモデル名 |
| 3 | `aspect_ratio` | アスペクト比 | COMBO | 選択モデルの先頭 | 選択モデルのリスト＋末尾に「カスタム」 |
| 4 | `custom_ratio` | カスタム比率 | STRING | `2.39:1` | 「カスタム」選択時のみ使用。固定解像度も可 |
| 5 | `orientation` | 向き | COMBO | 横長／縦長 | 長辺の向きを決める（4章） |
| 6 | `megapixels` | メガピクセル | FLOAT | 1.00（0.1〜16、step 0.01） | 固定解像度のときは無視 |
| 7 | `multiple` | 倍数 | INT | 16（1〜256） | 幅・高さの丸め単位 |
| 8 | `batch_size` | バッチサイズ | INT | 1（1〜4096） | 潜在画像の枚数 |

### 出力

| 内部名 | 表示名 | 型 | 説明 |
| --- | --- | --- | --- |
| `latent` | 潜在画像 | LATENT | 全ゼロの潜在画像 |
| `width` | 幅 | INT | ピクセル幅 |
| `height` | 高さ | INT | ピクセル高さ |

ノード下部に計算結果を表示する（5章）。

## 3. プリセットファイル仕様

プリセットはリポジトリ直下の`yoshiaki-resolution-latent.toml`に書き、起動時に1回だけ読む（`yoshiaki-wildcard.ini`と同じ置き方）。テーブル1つが1モデルで、ファイルに書いた順が「モデル」欄の選択肢の順になる。

### キー一覧

| キー | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `latent_channels` | int | ○ | VAE未接続時に使うチャンネル数 |
| `downscale` | int | ○ | VAE未接続時に使う空間縮小率。VAE接続時は食い違いチェックに使う |
| `multiple` | int | ○ | モデル選択時に「倍数」欄へ入れる値。必要な最小倍数も兼ねる |
| `default_mp` | float | ○ | モデル選択時に「メガピクセル」欄へ入れる値 |
| `mp_range` | \[float, float\] | — | 推奨範囲。外れたら警告のみ |
| `aspect_ratios` | \[string\] | ○ | アスペクト比または固定解像度のリスト |
| `generic` | bool | — | trueなら汎用扱い（標準Empty Latentと同じ挙動、4章） |

### aspect\_ratiosの書式

- **比率**：`"16:9"`、`"2.39:1"`、`"1.85"`（小数のみは`:1`とみなす）。区切りは`:`のみ
- **固定解像度**：`"1152x896"`（区切りは`x`または`×`）。メガピクセルを無視してこのサイズを使う
- 半角スペース以降は自由なラベル：`"16:9 Widescreen"`
- 横長と正方形だけを書く。縦長は「向き」欄で作る（縦長の形で書いても向き欄が優先）
- 書式が不正な項目は起動時にログへ警告を出してスキップする

### 初期ファイル

数値は仮の値。`latent_channels`と`downscale`は、実装前にComfyUI本体の`comfy/latent_formats.py`で確定させる（7章）。

```toml
# yoshiaki-resolution-latent.toml
# 編集後はComfyUIを再起動。aspect_ratiosは横長と正方形だけ書く

["汎用"]
generic = true
latent_channels = 4
downscale = 8
multiple = 16
default_mp = 1.0
aspect_ratios = ["1:1 Square", "5:4", "4:3", "3:2", "16:10", "16:9 Widescreen", "21:9 Ultrawide", "2.39:1 Cinemascope"]

[Anima]
latent_channels = 16
downscale = 8
multiple = 16
default_mp = 1.0
mp_range = [0.25, 2.25]
aspect_ratios = ["1:1 Square", "5:4", "4:3", "3:2", "16:9 Widescreen", "1152x896", "1216x832"]

[Krea2]
latent_channels = 16
downscale = 8
multiple = 16
default_mp = 1.0
mp_range = [1.0, 4.0]
aspect_ratios = ["1:1 Square", "4:3", "3:2", "16:9 Widescreen", "21:9 Ultrawide", "2.39:1 Cinemascope"]

["MOSS-Image"]
latent_channels = 128   # 要確認（FLUX.2系のパック後チャンネル数）
downscale = 16          # 要確認
multiple = 16
default_mp = 1.0
aspect_ratios = ["1:1 Square", "4:3", "3:2", "16:9 Widescreen"]
```

### 読み込み時の解釈

- ファイルが無い、または解析に失敗したときは、コード内の「汎用」プリセットだけで起動し、ログに警告を出す
- 必須キーが欠けたモデルはスキップして警告を出す
- `multiple`が`downscale`の倍数でないときは、`downscale`の倍数へ切り上げて警告を出す
- 配布用に`yoshiaki-resolution-latent.toml.example`をリポジトリ直下に同梱する（`yoshiaki-wildcard.ini.example`と同じ扱い）。`yoshiaki-resolution-latent.toml`が無ければ、初回起動時にexampleをコピーして作る
- `.gitignore`に`/yoshiaki-resolution-latent.toml`を追加する（編集内容がgit pullで上書きされないようにするため。既存のyoshiaki-comfy用ブロックの末尾にコメント付きで追記）
- 自動生成した後は手書きファイルとして扱い、ノードから書き戻しはしない（ユーザーのコメントが消えるため）

## 4. 計算ロジック

処理は「比率の解析 → 向きの適用 → 倍数の確定 → サイズ計算 → 潜在画像の形状決定」の順に行う。計算部分はComfyUIに依存しない純粋関数に分け、単体テストできるようにする。

1. **比率の取得**：`aspect_ratio`が「カスタム」なら`custom_ratio`、それ以外は`aspect_ratio`の文字列を使う
2. **解析**：最初の半角スペースまでを対象にし、次のどちらかを返す
   - 比率 `(rw, rh)`：`W:H` または小数のみ（`:1`扱い）
   - 固定解像度 `(W, H)`：`WxH` / `W×H`
3. **向き**：「横長」なら長辺を幅、「縦長」なら長辺を高さになるよう入れ替える。正方形はそのまま。固定解像度にも適用する
4. **倍数の確定**
   - 必要倍数 `req`：汎用プリセットなら実際の縮小率、それ以外は `lcm(preset.multiple, 実際の縮小率)`
   - 実際の縮小率：VAE接続時はVAEの値、未接続時は`preset.downscale`
   - `multiple`が`req`の倍数でなければ、`req`の倍数へ切り上げて警告を出す（例：MOSSで8 → 16）
5. **サイズ計算**（1MP = 1024×1024、標準のResolution Selectorと同じ）
   - 比率：下の式。各辺は最低1倍数分
   - 固定解像度：倍数へ丸める。値が変わったら警告を出す
6. **潜在画像の形状決定**（下の表）

```latex
\text{scale} = \sqrt{\frac{mp \cdot 1024^2}{r_w \cdot r_h}},\quad w = \max\left(m,\ \operatorname{round}\left(\frac{r_w \cdot \text{scale}}{m}\right) m\right),\quad h = \max\left(m,\ \operatorname{round}\left(\frac{r_h \cdot \text{scale}}{m}\right) m\right)
```

確認用の値：16:9・1.00MP・倍数16で 1360×768。縦長なら 768×1360。

丸めは四捨五入 `floor(x / m + 0.5) * m` で統一する。Pythonの`round()`は偶数丸めで、JSの`Math.round()`と結果がずれるため使わない。

### 潜在画像の形状

| 条件 | チャンネル数 | 縮小率 | 備考 |
| --- | --- | --- | --- |
| VAE接続あり | VAEの値 | VAEの値 | プリセットの値と食い違えば警告（結果はVAEを優先） |
| VAEなし・モデルプリセット | `preset.latent_channels` | `preset.downscale` | — |
| VAEなし・汎用 | 4 | 8 | 標準Empty Latent Imageと同じ。本体の自動補正に任せる |

- テンソルは `[batch, C, h/d, w/d]` の全ゼロ。device・dtypeは標準のEmptyLatentImageと同じ取り方（`comfy.model_management.intermediate_device()`など）に合わせる
- 標準のEmptyLatentImageが返す辞書のキー（`samples`、`downscale_ratio_spacial`など）を実装時に本体コードで確認し、同じキー構成で返す。`downscale_ratio_spacial`には実際の縮小率を入れ、本体の自動補正で余計なリサイズが起きないようにする
- 基本は4次元で出す。5次元が必要なモデル（Qwen-Image VAE系）は、本体の`fix_empty_latent_channels`が次元を足す前提。7章の実機確認で問題が出た場合は、`vae.latent_dim == 3`のとき5次元`[B, C, 1, h/d, w/d]`で出す
- VAEから値を読むときは、本体`comfy/sd.py`のVAEクラスの属性・メソッド（`latent_channels`、`spacial_compression_encode()`、`latent_dim`など）を確認して使う。縮小率がタプルや関数（動画VAE）の場合は空間方向の値だけを取り出す

### ノード上の表示用データ

Python側は戻り値を `{"ui": {...}, "result": (latent, w, h)}` の形で返し、`ui`に次を入れる：幅・高さ・実際のMP・潜在画像の形状・形状の決定元（VAE／プリセット／汎用）・警告文のリスト。

## 5. フロントエンド（JS）仕様

モデルごとのアスペクト比リストの切替、値の自動入力、計算結果の表示をJS拡張で実装する。Python側のCOMBOは起動時に固定されるためである。

### Python側の準備

- `aspect_ratio`のCOMBOには、全プリセットのアスペクト比を重複なく並べた和集合＋「カスタム」を登録する
- プリセットの中身を返すAPIを用意する：`GET /yoshiaki/resolution_latent/presets`（既存ノードと同じく`modules/yoshiaki_resolution_latent/server.py`で`PromptServer.instance.routes`に登録）
- JSは`js/yoshiaki-resolution-latent.js`に置く。`__init__.py`の`nodes.EXTENSION_WEB_DIRS["yoshiaki-comfy"]`で`js/`は公開済みなので、`WEB_DIRECTORY`は使わない
- JSで追加する表示用ウィジェットは`serialize = false`にし、保存済みワークフローの`widgets_values`がずれないようにする（`js/yoshiaki-load-jxl.js`と同じ方針）

### JSの動作

1. 起動時にプリセットAPIを読み、メモリに保持する
2. **ユーザーが「モデル」欄を変更したとき**：
   - 「アスペクト比」の選択肢をそのモデルのリスト＋「カスタム」に差し替える
   - 現在の値が新リストにあれば維持し、無ければ先頭にする（「カスタム」は常に維持）
   - 「倍数」に`multiple`、「メガピクセル」に`default_mp`を入れる
3. **ワークフロー読み込み時（onConfigure等）**：選択肢の差し替えだけ行い、**倍数・メガピクセル・アスペクト比の値は上書きしない**。保存済みのアスペクト比がリストに無い場合は、その値を選択肢に一時的に追加して保持し、警告を表示する
4. **ライブ表示**：欄の値が変わるたびにJSで幅・高さ・MPを計算し、ノード下部に表示する。例：`1360 × 768 ｜ 1.00 MP ｜ 潜在 16×96×170（プリセット値）`
5. **実行後の表示**：Pythonの`ui`を受け取り（`onExecuted`）、実際の潜在画像の形状・決定元（VAEなど）・警告を表示する。警告は目立つ色にする
6. 「カスタム比率」欄は、「カスタム」以外のとき非表示かグレーアウトにする（現行フロントエンドで非表示が不安定なら常時表示でよい）

### 注意点

- ライブ表示の計算はJSとPythonの二重実装になる。7章のテストケースをJS側でも確認し、結果を一致させる
- 編集中はVAEの中身を知る手段が無いため、ライブ表示の潜在形状はプリセット値でよい（「プリセット値」と明記）
- 欄がリンク入力に変換されている場合は、その欄に関わる自動処理をスキップする
- 現行のComfyUIフロントエンド（Vue版）の拡張API（`app.registerExtension`）に合わせ、動作したフロントエンドのバージョンをCLAUDE.mdの本ノードの項に記載する

## 6. 警告・エラー処理

生成を続けられるものは警告にとどめ、意図と違う画像が確実に出るものだけエラーにする。警告はコンソールログ（接頭辞`[yoshiaki-comfy] ResolutionLatent:`）とノード上の表示の両方に出す。

| 状況 | 扱い | 動作 |
| --- | --- | --- |
| 倍数が必要倍数の倍数でない | 警告 | 切り上げて続行 |
| 固定解像度が倍数に合わない | 警告 | 倍数へ丸めて続行 |
| MPが`mp_range`の範囲外 | 警告 | そのまま続行 |
| VAEの縮小率・チャンネル数がプリセットと不一致 | 警告 | VAEの値で続行（「モデル選択とVAEが合っていない可能性」と表示） |
| 保存されたモデル名がプリセットに無い | 警告 | 「汎用」として続行 |
| 保存されたアスペクト比がどのリストにも無い | 警告 | 文字列を解析できればそのまま使う |
| カスタム比率が解析できない・0以下 | エラー | 入力例を添えたメッセージで停止 |
| 固定解像度のどちらかの辺が64px未満 | エラー | 「比率なら 16:9 のように`:`で書いてください」と表示（`16x9`の書き間違い対策） |
| 幅・高さが本体の`MAX_RESOLUTION`を超える | エラー | 停止 |

### バリデーションの回避

プリセットに無い名前が保存されていると、ComfyUIの標準チェックが実行前に弾いてしまう。そこで`VALIDATE_INPUTS`に`model_preset`と`aspect_ratio`を引数として定義し、標準チェックを外して自前で判定する（上の表の通り警告で通す）。この仕組みが現行の`execution.py`でも有効かは実装前に確認する。

## 7. 実装の進め方

コードを書く前に、ComfyUI本体のソースで5点を確認し、結果を報告してから実装に入る。仕様と食い違う点があれば、自分で判断せず報告する。

### 実装前の確認事項

1. `comfy/latent_formats.py`：Anima・Qwen-Image（Krea 2）・MOSS-Imageが使うlatent formatの`latent_channels`、`spacial_downscale_ratio`、`latent_dimensions` → 初期プリセットの値を確定
2. `comfy/sample.py`：`fix_empty_latent_channels`の現在の挙動（チャンネル補正・縮小率補正・次元追加）
3. `nodes.py`：`EmptyLatentImage`の戻り値のキー構成、device、dtype、`MAX_RESOLUTION`
4. `comfy/sd.py`：VAEクラスからチャンネル数・空間縮小率・次元数を取得する方法
5. `execution.py`：`VALIDATE_INPUTS`でCOMBOの標準チェックを外せるか

### ファイル構成

```
yoshiaki-comfy/
├── __init__.py                                  # 既存。本ノードのMAPPINGSとserverを他ノードと同じ形で追加
├── yoshiaki-resolution-latent.toml.example      # 新規。配布用の初期プリセット
├── .gitignore                                   # 既存。/yoshiaki-resolution-latent.toml を追記
├── CLAUDE.md                                    # 既存。「含まれるカスタムノード」に本ノードの項を追記
├── docs/yoshiaki/
│   ├── ResolutionLatent_Node_指示書.md            # 新規。本書
│   └── tasks_done.md                            # 既存。履歴を追記
├── js/yoshiaki-resolution-latent.js             # 新規。リスト切替・自動入力・表示
└── modules/yoshiaki_resolution_latent/          # 新規
    ├── __init__.py
    ├── nodes.py                                 # YoshiakiResolutionLatentクラス
    ├── calc.py                                  # 比率解析・サイズ計算（ComfyUI非依存）
    ├── presets.py                               # TOML読み込み・検証
    ├── server.py                                # /yoshiaki/resolution_latent/presets
    └── tests/test_calc.py                       # pytest
```

### 単体テスト（calc.py、JS側も同じ結果になること）

| 入力 | 向き | MP | 倍数 | 期待値 |
| --- | --- | --- | --- | --- |
| `16:9` | 横長 | 1.00 | 16 | 1360×768 |
| `16:9` | 縦長 | 1.00 | 16 | 768×1360 |
| `9:16` | 横長 | 1.00 | 16 | 1360×768（向き欄が優先） |
| `2.39:1` | 横長 | 1.00 | 16 | 1584×656 |
| `1:1` | 縦長 | 1.00 | 16 | 1024×1024 |
| `1152x896` | 縦長 | 無視 | 16 | 896×1152 |
| `1000x700` | 横長 | 無視 | 16 | 1008×704＋警告（62.5は切り上げ） |
| `16:9`（MOSSプリセット） | 横長 | 1.00 | 8 | 倍数16へ切り上げ＋警告 |
| `16x9` | — | — | — | エラー（64px未満） |
| `abc` | — | — | — | エラー |

期待値は丸め方で変わりうる。実装で別の値になったら、計算過程を示して報告する。

### 実機確認（ユーザーが実施）

Anima・Krea 2・MOSS-Imageのそれぞれで、次を確かめる。手順は本書のこの節を使う。

- [ ] VAE接続あり／なしの両方でKSamplerが動き、デコード後の画像サイズが幅・高さの出力と一致する
- [ ] Anima・Krea 2で、同じseedなら標準のResolution Selector＋Empty Latentと同じ画像になる
- [ ] モデルを切り替えると、アスペクト比のリスト・倍数・メガピクセルが変わる
- [ ] 保存したワークフローを開き直しても、倍数・メガピクセル・アスペクト比が保存時のまま
- [ ] プリセットからモデルを消して再起動 → そのワークフローが警告付きで実行できる
- [ ] 違うVAEをつなぐと不一致の警告が出る

### 完了条件

- 単体テストがすべて通る
- 既存ノードがこれまでどおり読み込まれる（本ノードの読み込み失敗でパック全体を止めない。JXLノードと同じく`try`で囲む）
- `CLAUDE.md`の「含まれるカスタムノード」に、指定フォーマットで本ノードの項を追記している（実装前の確認結果、確定したプリセット値、`class_type`・表示名・`CATEGORY`を含む）
- `docs/yoshiaki/tasks_done.md`に履歴を追記している（動作確認は「⬜未確認」でよい）
- 本書を`docs/yoshiaki/ResolutionLatent_Node_指示書.md`として保存している
