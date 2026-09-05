# yoshiaki-comfy

個人利用のためのComfyUIカスタムノード集です。配布は行っていません。

## 含まれるノード

| ノード | 概要 |
|---|---|
| **Yoshiaki Wildcard Processor** (`YoshiakiWildcardProcessor`) | ワイルドカード構文のテキストを解決して文字列を出力する |
| **Yoshiaki Wildcard Encode** (`YoshiakiWildcardEncode`) | ワイルドカード構文とLoRA構文を解決し、LoRA適用済みの `MODEL`/`CLIP` とCLIP条件付け(`CONDITIONING`)を出力する |
| **Yoshiaki-LLMCaptionGenerator** (`YoshiakiLLMCaptionGenerator`) | WD14 Tagger等が出力したタグを画像と一緒にローカルLLM（Lemonade Server）へ渡し、タグの補正やキャプション文を生成する |
| **Yoshiaki LoRA Caption Load** (`YoshiakiLoRACaptionLoad`) | 指定フォルダ内のPNG画像とファイル名一覧を読み込む（LoRA学習用データセット準備の入力側） |
| **Yoshiaki LoRA Caption Save** (`YoshiakiLoRACaptionSave`) | 画像ファイル名に対応するキャプション(`.txt`)を、共通プレフィックス付きで保存する |
| **Yoshiaki WD14 Tagger** (`YoshiakiWD14Tagger`) | 画像をWD14系ONNXモデルでタグ付けする（booruタグ形式）。タグの優先順位並べ替え・ワイルドカード対応の除外タグをサポート |

`YoshiakiWildcardProcessor` / `YoshiakiWildcardEncode` は [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) の `ImpactWildcardProcessor` / `ImpactWildcardEncode` を、この2ノードだけ使う用途に切り出して単独パック化したものです。`YoshiakiLLMCaptionGenerator` はもともと別リポジトリ [ComfyUI-LLM-Tagger](https://github.com/Yoshiaki21/ComfyUI-LLM-Tagger) として作っていたノードをこちらに統合したものです（当時の開発履歴は [docs/yoshiaki/tasks_done.LLM.md](docs/yoshiaki/tasks_done.LLM.md)、詳細仕様は [docs/yoshiaki/LLM_Caption_Node_指示書.md](docs/yoshiaki/LLM_Caption_Node_指示書.md) 参照）。`YoshiakiLoRACaptionLoad` / `YoshiakiLoRACaptionSave` は自分のフォーク [Image-Captioning-in-ComfyUI](https://github.com/Yoshiaki21/Image-Captioning-in-ComfyUI)（本家: [LarryJane491/Image-Captioning-in-ComfyUI](https://github.com/LarryJane491/Image-Captioning-in-ComfyUI)）から統合したものです。いずれもノード名・Pythonパッケージ名を独自のものに変更しているため、元のリポジトリと同一環境に共存インストールしても衝突しません。

---

## Yoshiaki Wildcard Processor

`wildcard_text` に書いたワイルドカード構文を解決し、`processed text` (STRING) として出力します。LoRAやCLIPは扱わず、テキスト生成だけが必要な場合に使います。

**入力**

| 名前 | 型 | 説明 |
|---|---|---|
| `wildcard_text` | STRING | ワイルドカード構文を含むプロンプト |
| `populated_text` | STRING | 実際にワークフロー実行時に解決される欄。`mode`により挙動が変わる |
| `mode` | populate / fixed / reproduce | 下記参照 |
| `seed` | INT | ワイルドカード選択・ランダム選択に使う乱数シード |

**出力**

| 名前 | 型 |
|---|---|
| `processed text` | STRING |

---

## Yoshiaki Wildcard Encode

`wildcard_text` に書いたワイルドカード構文とLoRA構文（`<lora:...>`）を解決し、LoRAを適用した `model`/`clip` と、CLIPエンコード済みの `conditioning` をまとめて出力します。

**入力**

| 名前 | 型 | 説明 |
|---|---|---|
| `model` | MODEL | 入力モデル |
| `clip` | CLIP | 入力CLIP |
| `wildcard_text` | STRING | ワイルドカード構文・LoRA構文を含むプロンプト |
| `populated_text` | STRING | 実際にワークフロー実行時に解決される欄。`mode`により挙動が変わる |
| `mode` | populate / fixed / reproduce | 下記参照 |
| `seed` | INT | ワイルドカード選択・ランダム選択に使う乱数シード |

**出力**

| 名前 | 型 | 説明 |
|---|---|---|
| `model` | MODEL | LoRA適用後のモデル |
| `clip` | CLIP | LoRA適用後のCLIP |
| `conditioning` | CONDITIONING | 解決後テキストをCLIPエンコードした条件付け |
| `populated_text` | STRING | 実際に使用された解決後テキスト |

### LoRA構文

```
<lora:LoRA名>                          重み1.0で適用
<lora:LoRA名:0.8>                      model/clip共通で重み0.8
<lora:LoRA名:0.8:0.6>                  model重み0.8, clip重み0.6
```

- 拡張子は省略可（`.safetensors` を自動補完）
- 同じLoRAタグを複数書いても1回しか適用されない
- `BREAK` でテキストを区切ると、区切りごとに個別にCLIPエンコードして連結する（Automatic1111互換の`BREAK`と同じ考え方）
- LoRA Block Weight（`LBW=`構文, Inspire Pack連携）や `LOADER=nunchaku` 構文は**非対応**です（未使用のため意図的に省略。詳細は[docs/yoshiaki/tasks_done.md](docs/yoshiaki/tasks_done.md)参照）

### LoRA情報表示・追加ボタン

`Select to add LoRA`でLoRAを選んでも、**その時点ではプロンプトに追加されません**。情報を見るだけ、選ぶだけ、という使い方ができます。

`Select to add LoRA`のコンボにはファイル名だけ（フォルダ名なし）が表示されます。内部的には、ComfyUIの「モデルファイル存在チェック」と一致させる必要があるフォルダ込みのフルパスを保持する本体のウィジェットを非表示にし、見た目上の`Select to add LoRA`は別の表示専用ウィジェットに差し替えることで、余計な行を増やさずに警告を回避しています。

- **LoRA Info**: 選択中のLoRAについて、以下を表示するダイアログを開きます
  - ファイル名 / SHA256ハッシュ
  - 種類・ベースモデル、Civitaiへのリンク（初回表示時に自動取得。失敗時は「Retry」で再取得）
  - トリガーワード（LoRAファイル自体に埋め込まれたメタデータ＋Civitai由来の両方をマージ）。クリックで選択でき、「Copy selected」（選択したものだけコピー）と「Copy all」（すべてコピー）が使える
  - Civitaiのサンプル画像（seed/steps/cfg/sampler/model、Positive/Negativeプロンプトとそれぞれの「Copy」ボタン付き）
- **LoRA Add**: 選択中のLoRAを、実際に`<lora:名前>`の形で`wildcard_text`へ追加します。情報を確認してから「これを使う」と決めたときに押してください

[rgthree-comfy](https://github.com/rgthree/rgthree-comfy)（MITライセンス）のPower Lora Loaderにある同種の機能を参考にしていますが、**そのコードを移植したものではなく独自に書き直した縮小版**です。編集可能なメモ欄・独自の動画再生コントロール・開発者向けメニュー・モデル一括管理APIは含んでいません。キャッシュ（`modules/yoshiaki_lora_info/cache/`、`.gitignore`対象）も完全に独立しており、実際のrgthree-comfyのキャッシュファイルとは一切共有しません。

---

## `mode` の挙動（両ノード共通）

| mode | 動作 |
|---|---|
| `populate` | ワークフロー実行前に `wildcard_text` を解決し、結果を `populated_text` へ自動反映する（`populated_text` は編集不可）。実行後、自動的に `reproduce` に切り替わる |
| `fixed` | `wildcard_text` は無視し、`populated_text` をそのまま使う。`populated_text` は自由に編集できる（ここに直接ワイルドカード構文を書いても実行時に解決される） |
| `reproduce` | 1回だけ`fixed`として動作（直前の解決結果を再現）し、次回から自動的に`populate`へ戻る。同じ結果を再現したいときに使う |

---

## ワイルドカード構文リファレンス

`wildcards/` フォルダ（または設定した `custom_wildcards` フォルダ）に置いた `.txt` / `.yaml` ファイルがワイルドカードとして使えます。

### 基本: `__name__`

`wildcards/example.txt` に1行1候補で書くと、`__example__` と書いた箇所がランダムに1行へ置き換わります。`#` から始まる行はコメントとして無視されます。

```
__example__
```

サブフォルダに入れた場合は `__folder/name__` のようにパス区切りで参照します。`*` を使ったあいまい一致（例: `__*/dragon__`）にも対応しています。

### 固定行選択: `__name#N__`

`__example#2__` のように末尾に `#N` を付けると、乱数を使わずファイルのN行目（1始まり、コメント・空行除く）を固定で選びます。`.txt` ファイル限定・グロブとの併用不可です。

### 中括弧によるインライン選択: `{a|b|c}`

ファイルを用意しなくても、その場で選択肢を書けます。

```
{赤|青|黄}い花
```

- 重み付け: `{2::赤|1::青}` のように `数値::選択肢` とすると出現比率を調整できます
- 複数選択: `{2$$赤|青|黄}` のように `個数$$` を先頭に付けると、指定個数をスペース区切りで選び出します。範囲指定 `{1-2$$赤|青|黄}` や、区切り文字を挟んだ `{1-2$$,$$赤|青|黄}`（この場合カンマ区切りで結合）も可能です

### 繰り返し: `N#__name__`

`3#__example__` と単体で書くと、`__example__` をそれぞれ独立に3回ランダム解決し、結果を `|` で連結したテキストになります（例: `red flower|blue flower|yellow flower`）。

`{}` で囲んで `{3#__example__}` と書くと、その3回分の抽選結果から1つだけをランダムに選びます。用途に応じて使い分けてください。

### YAMLファイル

`.yaml` / `.yml` ファイルでは、キー名で参照できるネスト構造（1階層まで）に対応しています。

```yaml
colors:
  warm:
    - red
    - orange
  cool:
    - blue
    - green
```

この場合、`__colors__`（warm/coolの全値）、`__colors/warm__`（redかorange）のように参照できます。

---

## ワイルドカードファイルの場所

デフォルトはこのリポジトリ内の [`wildcards/`](wildcards) フォルダです。別の場所にある既存のワイルドカード集を使いたい場合は、[`yoshiaki-wildcard.ini.example`](yoshiaki-wildcard.ini.example) をコピーして `yoshiaki-wildcard.ini` を作り、`custom_wildcards` にパスを書いてください（設定すると、そのフォルダ**のみ**が参照され、`wildcards/` は使われなくなります）。

```ini
[default]
custom_wildcards = D:\GitHub_data\ComfyUI-Impact-Pack\wildcards
```

反映にはComfyUIの再起動、または右クリックメニュー等から `Yoshiaki: Refresh Wildcard List` コマンドを実行してください。

内容はキャッシュせず、毎回ディスクから読み直します（ファイルを編集したら即座に反映されます）。

### 「Select to add Wildcard」/「Select to add LoRA」のフォルダ絞り込み

ワイルドカードファイルやLoRAファイルが増えて選択肢が探しにくくなってきた場合のために、「Select to add Wildcard」の直上に「Wildcard Folder」、（`YoshiakiWildcardEncode`では）「Select to add LoRA」の直上に「LoRA Folder」というコンボが用意されています。ここでサブフォルダを選ぶと、それぞれの選択肢にはそのフォルダ**直下**にあるものだけが表示されます（サブフォルダの中身は含みません。さらに深い階層を見たい場合はその階層自体をフォルダ一覧から選んでください）。先頭の「(no folder)」は、サブフォルダに入れていないファイルを絞り込むための選択肢です。選んだフォルダはノード・種類ごとにブラウザの`localStorage`に記憶され、ワークフローファイル自体には保存されません。

---

## Yoshiaki-LLMCaptionGenerator

画像とWD14 Taggerなどのタグ文字列を、手元のLAN上で動く **Lemonade Server**（AMD製のローカルLLM推論サーバー、OpenAI互換API）に送り、タグの補正やキャプション文（自然言語の説明文）をLLMに生成させるノードです。

```
[LoadImage] → [WD14Tagger] → tags(STRING) ┐
       └─────────────────────────────────→ [Yoshiaki-LLMCaptionGenerator] → caption_text(STRING)
```

**入力（抜粋）**

| 名前 | 型 | 説明 |
|---|---|---|
| `image` | IMAGE | キャプション対象の画像（バッチ/リストどちらも可） |
| `tags` | STRING | WD14 Tagger等から受け取るタグ文字列（このノード自体はタグ生成ノードに依存しない。単なるテキスト入力） |
| `trigger_word` | STRING | 学習用データセットのトリガーワード（任意。指定するとタグ列の先頭に必ず挿入される） |
| `system_prompt_file` | COMBO | [`system_prompts/`](modules/yoshiaki_llm/system_prompts) フォルダ内の `.txt` から選択 |
| `lemonade_host` / `lemonade_port` / `lemonade_api_key` | STRING/INT/STRING | Lemonade ServerのAPI接続先 |
| `model` | COMBO | 接続先から取得したモデル一覧 |
| `temperature` / `max_tokens` / `timeout_sec` / `max_retries` 等 | — | 生成パラメータ・リトライ回数の設定 |

**出力**: `caption_text` (STRING) — `image`と同じ枚数・同じ順序のキャプション文字列リスト

### 動作の仕組み

- `system_prompt_file` で選んだ `.txt` の1行目（`<!-- output_mode: tags_only|caption_only|both -->`）から出力モードを自動判定します。ウィジェットではなくファイル側の指定です
- 接続失敗・タイムアウト・応答フォーマット不正などを分類し、パラメータを調整しながら`max_retries`回まで自動リトライします
- 実行結果は `modules/yoshiaki_llm/logs/`（`.gitignore`対象）にログとして残ります。`log_prompt`をONにすると送信内容と生応答も記録されます

### 前提条件

- LAN上（またはlocalhost）で **Lemonade Server** が起動している必要があります。既定の接続先は開発時の環境に合わせたLAN内IPになっているため、`lemonade_host` / `lemonade_port` ウィジェットで自分の環境に合わせて変更してください
- ComfyUI-Impact-Pack等のような他のカスタムノードパックへのコード依存はありません（`tags`入力にWD14 Taggerを繋ぐのはワークフロー上の運用であり、コード上の依存ではありません）

---

## Yoshiaki LoRA Caption Load / Save

LoRA学習用データセットの準備（画像 + キャプションのペア作成）を補助する2ノードです。WD14 Taggerと組み合わせて使うことを想定しています。

```
[Yoshiaki LoRA Caption Load] → Image list ──────────→ [WD14Tagger] → tags
       ├─ Name list ─────────────────────────────────────────────────┐
       └─ path ──────────────────────────────────────────────────┐   │
                                                                   ▼   ▼
                                                        [Yoshiaki LoRA Caption Save]
```

- **Yoshiaki LoRA Caption Load**: `path`で指定したフォルダ内のPNG画像を全て読み込み、`Image list`（画像バッチ）と`Name list`（ファイル名一覧、改行区切り）、`path`（そのまま）を出力する
- **Yoshiaki LoRA Caption Save**: `Name list`・`path`・`text`（キャプション文字列）を受け取り、画像ファイルと同じ名前の`.txt`を保存する。`prefix`（任意）を指定すると、トリガーワード等をキャプションの先頭に自動で付加できる
  - `output_path`（任意）: 保存先フォルダを`path`と別にしたい場合に指定する。空欄なら従来通り`path`にのみ`.txt`を保存する（画像コピーは発生しない）。指定すると、そのフォルダへ`.txt`と**元画像ファイルのコピー**の両方を書き出す（元画像は再エンコードせずそのままコピーするので画質劣化なし）
  - `overwrite`（任意、既定OFF）: OFFのときは今まで通り「まだ`.txt`が無い最初のファイル」を自動で探して1件処理する（既存ファイルには一切触れない）。ONにすると`Name list`の順番通りに、既存ファイルの有無を無視して`.txt`と画像コピーを上書きする。同じモデルの比較のため、出力先を変えずに何度も captioning をやり直したい場合などに使う

**既知の制約（本家・フォーク由来、今回の統合ではそのまま維持）**:
- 画像は**PNGのみ**対応
- 同名の`.txt`が既にあるフォルダに対して`Yoshiaki LoRA Caption Load`→`Yoshiaki LoRA Caption Save`を実行するとエラーになる（先に`.txt`を消してから再実行する必要がある）

**yoshiaki-comfy側で修正済みの点（本家・フォークにあった潜在バグ）**:
- フォルダ内にPNG画像が1枚も無い場合、以前は分かりにくいエラーで落ちていたが、明確な`FileNotFoundError`（「No PNG images found in path ...」）で止まるようにした
- フォルダ内の画像が**ちょうど1枚**のときに出力の型が壊れる不具合を修正（1枚でも複数枚でも同じ処理になるよう統一）
- `Yoshiaki LoRA Caption Load`のノード上に、読み込んだ画像枚数を表示するようにした（他のノードには渡らない、このノード自身の表示のみ）

---

## Yoshiaki WD14 Tagger

画像をWD14系のONNXタグ分類モデルでbooruタグ形式にタグ付けするノードです。`YoshiakiLoRACaptionSave`や`YoshiakiLLMCaptionGenerator`の`tags`入力に繋いで使う想定です。

**入力（抜粋）**: `image` (IMAGE) / `model`（COMBO、選択したモデルが未取得ならHugging Faceから自動ダウンロード） / `threshold` / `character_threshold` / `replace_underscore` / `trailing_comma` / `exclude_tags`（`fnmatch`のワイルドカード対応。例: `"* hair"`で`"brown hair"`等をまとめて除外）

**出力**: `STRING`（画像枚数分のリスト）

**独自機能**:
- **タグの優先順位並べ替え**: [modules/yoshiaki_wd14tagger/priority.json](modules/yoshiaki_wd14tagger/priority.json) で定義したカテゴリ順（髪→目→表情→体→服→アクセサリ→ポーズ→背景→品質メタ、の順）にgeneralタグを並べ替える。キャラクター名タグは常に先頭固定
- **モデルの保存先**: `modules/yoshiaki_wd14tagger/models/`（このノード専用。`.gitignore`対象）。個別設定は[`config.user.json.example`](modules/yoshiaki_wd14tagger/config.user.json.example)をコピーして`config.user.json`を作ると上書きできる（`.gitignore`対象）
- **推論はCPU限定**（`config.json`の`ortProviders`が`CPUExecutionProvider`のみ）

**前提条件・注意点**:
- 元の [ComfyUI-WD14-Tagger](https://github.com/pythongosssss/ComfyUI-WD14-Tagger) にあった「ComfyUI上のどの画像でも右クリックしてその場でタグ付けする」機能（キャンバス全体に影響するコンテキストメニュー拡張）は、このリポジトリでは統合していません。ワークフロー上に`Yoshiaki WD14 Tagger`ノードを置いて使う通常の使い方には影響ありません
- 選択したモデルが未ダウンロードの場合、実行時にHugging Faceから自動でダウンロードします（数百MB程度になることがあります）

---

## インストール

このリポジトリをComfyUIの `custom_nodes` フォルダ内にクローン（またはシンボリックリンク）し、以下を実行してください。

```bash
pip install -r requirements.txt
```

依存パッケージは `pyyaml`, `numpy`, `Pillow`, `onnxruntime`, `tqdm` です。`pyyaml`/`numpy`/`Pillow`はComfyUI本体が通常インストール済みですが、`onnxruntime`（`Yoshiaki WD14 Tagger`が使用）と`tqdm`（モデルダウンロードの進捗表示用）は追加インストールが必要な場合があります。`YoshiakiLLMCaptionGenerator` はLemonade Serverとの通信に標準ライブラリの`urllib`/`http.client`のみを使っており、追加のSDK等は不要です。

---

## ライセンス

`YoshiakiWildcardProcessor` / `YoshiakiWildcardEncode` は [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack)（GPLv3）からのコードを含みます。`YoshiakiLLMCaptionGenerator` は自作の [ComfyUI-LLM-Tagger](https://github.com/Yoshiaki21/ComfyUI-LLM-Tagger) からの移植です。`YoshiakiLoRACaptionLoad` / `YoshiakiLoRACaptionSave` は [LarryJane491/Image-Captioning-in-ComfyUI](https://github.com/LarryJane491/Image-Captioning-in-ComfyUI) を自分がフォークしたものからの移植です（本家・フォークともにOSSライセンスの明記なし）。`YoshiakiWD14Tagger` は [pythongosssss/ComfyUI-WD14-Tagger](https://github.com/pythongosssss/ComfyUI-WD14-Tagger)（MITライセンス）を自分がフォークしたものからの移植です。個人利用のみで配布予定はありません。
