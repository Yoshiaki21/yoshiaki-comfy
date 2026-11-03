# YoshiakiSaveImageJXL 指示書

作成日: 2026-11-01
対象リポジトリ: https://github.com/Yoshiaki21/yoshiaki-comfy
配置先（この指示書）: `docs/yoshiaki/JXL_Save_Node_指示書.md`

---

## 0. 目的と前提

- [save-image-extended-comfyui](https://github.com/audioscavenger/save-image-extended-comfyui)（以下「本家」）と同じ方式でファイル名・フォルダを指定し、**JPEG XL（.jxl）だけ**を保存するノードを yoshiaki-comfy に追加する。
- 画像を再生成するのに必要な情報を、JXLのXMPに書き込む。ただし**ワークフロー本体は書き込まない**。ワークフローは保存フォルダごとに別途保存して管理しているため。
- XMPの仕様（第5章）は**確定仕様**とする。後で作る画像ロードノード（XMPを読み取って表示・出力するノード）はこの仕様を前提にするので、勝手に変更しないこと。
- 自分専用で、配布はしない。本家はGPL-3.0だが、yoshiaki-comfyには既にGPLv3のコード（Impact-Pack由来）が含まれているため、ロジックの移植は問題ない。READMEのライセンス欄に追記すること。
- 動作環境は Windowsネイティブ版ComfyUI と、Linuxのpodmanコンテナ版ComfyUI の両方。どちらでも動くこと。

---

## 1. 配置・命名

| 項目 | 値 |
|---|---|
| クラス名 / ノードID | `YoshiakiSaveImageJXL` |
| 表示名 | `Yoshiaki Save Image JXL` |
| モジュール | `modules/yoshiaki_save_jxl/` |
| カテゴリ | 既存のyoshiaki-comfyノードに合わせる |
| 登録 | 既存の `__init__.py` の登録方式（`NODE_CLASS_MAPPINGS` など）に合わせる |
| ノードバージョン | モジュール内に `NODE_VERSION = "1.0.0"` を定義し、XMPに書き込む |

---

## 2. 入出力

### 必須入力

| 名前 | 型 | 既定値 | 説明 |
|---|---|---|---|
| `images` | IMAGE | — | 保存する画像（バッチ対応） |
| `filename_prefix` | STRING | 本家と同じ | 本家と同じ |
| `filename_keys` | STRING (multiline) | 本家と同じ | 本家と同じ |
| `foldername_prefix` | STRING | 本家と同じ | 本家と同じ |
| `foldername_keys` | STRING (multiline) | 本家と同じ | 本家と同じ |
| `delimiter` | STRING | 本家と同じ | 本家と同じ |
| `counter_digits` | INT | 本家と同じ | 0で連番なし |
| `counter_position` | COMBO | 本家と同じ | 本家と同じ |
| `named_keys` | BOOLEAN | 本家と同じ | 本家と同じ |
| `image_preview` | BOOLEAN | True | 本家と同じ |
| `quality` | INT 1〜100 | 90 | JXLの品質 |
| `lossless` | BOOLEAN | False | Trueのときはロスレス保存（`quality`は無視） |
| `effort` | INT 1〜9 | 7 | エンコードの労力 |
| `write_xmp` | BOOLEAN | True | XMPを書き込むかどうか |
| `primary_node` | STRING | "" | 主サンプラーのノードID（例: `3`）。空欄なら自動判定（6.2節） |

### 任意入力

| 名前 | 型 | 説明 |
|---|---|---|
| `positive_text` | STRING（接続専用・`forceInput`） | 実際に使われたポジティブプロンプト。ワイルドカードの解決結果、`Yoshiaki-PromptTranslator`の`combined_prompt`などをつなぐ |
| `negative_text` | STRING（接続専用・`forceInput`） | 実際に使われたネガティブプロンプト |
| `xmp_note` | STRING | 自由記述のメモ。XMPに書き込む |

### hidden入力

`prompt`（PROMPT）、`extra_pnginfo`（EXTRA_PNGINFO）、`unique_id`（UNIQUE_ID）

### 出力

なし（`OUTPUT_NODE = True`）。プレビューのUI返却は本家と同じ。

### 本家から削除するもの

`output_ext`、`save_job_data`、`job_data_per_image`、`job_custom_text`、`one_counter_per_folder`、`save_metadata`（EXIFへのprompt/workflow埋め込み）、`positive_text_opt` / `negative_text_opt`（`positive_text` / `negative_text`に置き換え）。

---

## 3. ファイル名・フォルダ処理

本家 `save_image_extended.py` の次のロジックを移植し、動作を同一にする。

- `filename_keys` / `foldername_keys` の解決
  - `id.widget` 形式の指定
  - widget名だけの指定
  - 未知のキーは固定文字列として扱う
  - `/` や `../` でサブフォルダを作る
  - `.custom_string` の扱い
  - `ckpt_path` / `lora_path` / `control_net_path`
  - 日時書式（`%F`、`%Y`など）
  - `named_keys`
  - `resolution`
- 連番の処理（`get_latest_counter` 相当）
  - 対象は `.jxl` ファイルのみ
  - 0桁なら連番なし
- 出力フォルダ外への書き込み防止（本家で修正済みの `/name` 問題を含む）

移植の方針：

- 本家のバグ修正履歴（2.73〜2.88）を反映した最新版を基準にする。
- 本家にある拡張子分岐やjobs.json関連のコードは削除する。

---

## 4. JXLエンコード

- 使用ライブラリは **`pillow-jxl-plugin`**（検証済みバージョン 1.3.8）。検証結果は 7章のタスク0を参照。
- 保存は次のように呼び出す。

  ```python
  import pillow_jxl  # noqa: F401  インポートするだけでPillowにJXL形式が登録される
  img.save(
      path,
      format="JXL",
      lossless=lossless,          # Trueならロスレス
      quality=quality,            # lossless=True のときはプラグイン内部で100に置き換わる
      effort=effort,
      xmp=xmp_bytes,              # write_xmp=False のときは渡さない
      compress_metadata=False,    # XMPを非圧縮の "xml " ボックスにする（既定値だが明示する）
  )
  ```

- `lossless=True` のときは数学的にロスレスで保存する。それ以外は `quality` と `effort` を使う。
- XMPは**非圧縮の `xml ` ボックス**に書き込む（`brob`で圧縮しない）。exiftool、exiv2、XnViewなどとの互換性を優先するため。
- コンテナ形式（ISOBMFF）で出力する。XMPボックスを持たせるために必須。`xmp=` を渡すとプラグインが自動でコンテナ形式にするため、`use_container` の指定は不要。
- 出力されるボックスの並びは `JXL ` → `ftyp` → `jxlp` → `xml ` → `jxlp` になる（画像データが2つの `jxlp` に分割され、その間にXMPが入る）。JXLの仕様上は正しい形式なので、このままでよい。
  - 注意：exiftoolはこの分割形式への**書き込み**をエラーにする仕様。読み取りは可能。本ノードではexiftoolで後から書き込むことはしない。
- RGBAの画像が入力された場合は、アルファチャンネルを保持する。プラグインが受け付けるモードは `RGB` / `RGBA` / `L` / `LA` / `I;16` / `F`。

---

## 5. XMP仕様 v1（確定）

### 5.1 名前空間

| 接頭辞 | URI |
|---|---|
| `x` | `adobe:ns:meta/` |
| `rdf` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` |
| `dc` | `http://purl.org/dc/elements/1.1/` |
| `xmp` | `http://ns.adobe.com/xap/1.0/` |
| `ycomfy` | `https://github.com/Yoshiaki21/yoshiaki-comfy/ns/1.0/` |

### 5.2 パケット構造

- UTF-8で書く。`<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>` で始め、`<?xpacket end="w"?>` で閉じる。
- `rdf:RDF` の中に `rdf:Description rdf:about=""` を**1つだけ**置き、すべてのプロパティをその中に入れる。
- プロパティはすべて**要素形式**で書く（属性形式は使わない）。改行を含む長い文字列があるため。
- 文字列のエスケープは、XMLライブラリ（`xml.etree.ElementTree` など）で行う。手作業で文字列を連結しない。

### 5.3 プロパティ一覧

| プロパティ | 型 | 必須 | 内容 |
|---|---|---|---|
| `dc:description` | rdf:Alt (`xml:lang="x-default"`) | 任意 | ポジティブプロンプト（汎用ビューアで表示させるため）。空なら省略 |
| `xmp:CreatorTool` | Text | ○ | `ComfyUI / yoshiaki-comfy YoshiakiSaveImageJXL {NODE_VERSION}` |
| `xmp:CreateDate` | Date | ○ | 保存日時。ISO 8601形式、タイムゾーン付き（例: `2026-11-01T22:19:05+09:00`） |
| `ycomfy:SchemaVersion` | Text | ○ | `"1"` |
| `ycomfy:Seed` | Text | 任意 | 主seedを10進数の**文字列**で書く。見つからない場合は省略 |
| `ycomfy:PositivePrompt` | Text | 任意 | ポジティブプロンプト。空なら省略 |
| `ycomfy:NegativePrompt` | Text | 任意 | ネガティブプロンプト。空なら省略 |
| `ycomfy:Note` | Text | 任意 | `xmp_note` の内容。空なら省略 |
| `ycomfy:Parameters` | Text | ○ | 5.4節のJSON。**正となるデータはこれ** |

運用ルール：

- **ロードノードは `ycomfy:Parameters` だけを正として読む。** 他のプロパティは、人間やexiftoolで見るための重複情報。
- 値が重複していて食い違った場合は、`ycomfy:Parameters` を優先する。

### 5.4 `ycomfy:Parameters` のJSONスキーマ（v1）

```json
{
  "schema": "yoshiaki-comfy/jxl-params",
  "version": 1,
  "generator": {
    "node": "YoshiakiSaveImageJXL",
    "node_version": "1.0.0",
    "comfyui_version": "0.x.x または unknown"
  },
  "created_at": "2026-11-01T22:19:05+09:00",
  "image": {
    "filename": "PREFIX-0001.jxl",
    "subfolder": "a/b",
    "width": 1024,
    "height": 1536,
    "batch_index": 0,
    "batch_size": 1,
    "lossless": false,
    "quality": 90
  },
  "prompt": {
    "positive": "…",
    "negative": "…",
    "positive_source": "input",
    "negative_source": "auto"
  },
  "seed": {
    "value": "123456789012345",
    "node_id": "3",
    "class_type": "KSampler",
    "widget": "seed",
    "candidates": [
      {"node_id": "3", "class_type": "KSampler", "widget": "seed", "value": "123456789012345", "distance": 1},
      {"node_id": "12", "class_type": "YoshiakiWildcardEncode", "widget": "seed", "value": "42", "distance": 3}
    ]
  },
  "sampler": {
    "node_id": "3",
    "class_type": "KSampler",
    "steps": 30,
    "cfg": 5.0,
    "sampler_name": "euler",
    "scheduler": "normal",
    "denoise": 1.0
  },
  "models": [
    {"node_id": "4", "class_type": "CheckpointLoaderSimple", "kind": "checkpoint", "name": "xxx.safetensors"},
    {"node_id": "10", "class_type": "LoraLoader", "kind": "lora", "name": "yyy.safetensors", "strength_model": 0.8, "strength_clip": 0.8}
  ],
  "note": "…",
  "nodes": {
    "3": {
      "class_type": "KSampler",
      "title": "KSampler",
      "inputs": {"seed": 123456789012345, "steps": 30, "cfg": 5.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}
    }
  }
}
```

各フィールドの規則：

| キー | 規則 |
|---|---|
| `schema` / `version` | 固定値。ロードノードはまずこの2つで判定する |
| `generator.comfyui_version` | `comfyui_version.py` などから取得する。取得できなければ `"unknown"` |
| `created_at` | ローカル時刻、タイムゾーン付き。`xmp:CreateDate` と同じ値 |
| `image.subfolder` | ComfyUIのoutputフォルダからの相対パス。区切りは `/` に統一 |
| `image.batch_index` / `batch_size` | バッチ内の位置（0始まり）と、バッチの総数 |
| `prompt.*_source` | `"input"`（入力ソケットから取得）、`"auto"`（6.3節の自動取得）、`"unresolved"`（リンク先が文字列ウィジェットではなく取得できなかった）、`"none"`（該当なし）のいずれか |
| `seed.value` / `candidates[].value` | **10進数の文字列**。seedは2^53を超えることがあり、JavaScriptで扱うと精度が落ちるため |
| `seed.distance` | 6.2節の上流探索で数えたホップ数 |
| `seed` | 見つからない場合は `null` |
| `sampler` | 主サンプラーのノードが持つ値のうち、`steps` / `cfg` / `sampler_name` / `scheduler` / `denoise` に該当するものだけ。存在しないキーは省略する。主サンプラーがなければ `null` |
| `models` | 6.4節の規則で抽出する。`kind` は `checkpoint` / `unet` / `clip` / `vae` / `lora` / `other` のいずれか。数値の強度があれば併記する |
| `note` | `xmp_note` の内容。空なら空文字 |
| `nodes` | 6.1節で収集した全ノードの値。キーはノードID（文字列） |

### 5.5 バージョン管理ルール

- **キーの追加は互換性のある変更**とし、`version` は1のまま。ロードノードは知らないキーを無視すること。
- キーの削除、型の変更、意味の変更をする場合は `version: 2` にする。ロードノードは自分が対応していないバージョンなら警告を出し、読める範囲だけ表示する。
- XMPの名前空間URIの `1.0` は変更しない。スキーマの版は `version` で管理する。

### 5.6 XMPの例（短縮版）

```xml
<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:ycomfy="https://github.com/Yoshiaki21/yoshiaki-comfy/ns/1.0/">
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">1girl, …</rdf:li></rdf:Alt></dc:description>
   <xmp:CreatorTool>ComfyUI / yoshiaki-comfy YoshiakiSaveImageJXL 1.0.0</xmp:CreatorTool>
   <xmp:CreateDate>2026-11-01T22:19:05+09:00</xmp:CreateDate>
   <ycomfy:SchemaVersion>1</ycomfy:SchemaVersion>
   <ycomfy:Seed>123456789012345</ycomfy:Seed>
   <ycomfy:PositivePrompt>1girl, …</ycomfy:PositivePrompt>
   <ycomfy:NegativePrompt>…</ycomfy:NegativePrompt>
   <ycomfy:Parameters>{"schema":"yoshiaki-comfy/jxl-params","version":1, …}</ycomfy:Parameters>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
```

---

## 6. 値の収集ロジック

### 6.1 全ノードの値（`nodes`）

hidden入力の `prompt`（API形式）を走査して収集する。

- `class_type` と `_meta.title` を記録する。
- `inputs` のうち、次の型の値だけを記録する。
  - int / float / bool / str
- **リンクは除外する。** リンクとは `[ "ノードID", 出力番号 ]` 形式の、要素が2つのリストのこと。
- 16,384文字を超える文字列は、次の形に置き換える（Inspire PackのLoad Imageが埋め込むbase64対策）。
  - `{"_truncated": true, "length": N, "sha256": "…"}`
- このノード自身（`unique_id`）も記録対象に含める。

### 6.2 主seedと主サンプラーの決定

1. `primary_node` が指定されていれば、そのノードを主サンプラーとする。
2. 指定がなければ、このノードの `images` 入力から**リンクを上流へ幅優先探索**し、`seed` または `noise_seed` を持つノードをすべて候補（`candidates`）として集める。各候補には到達までのホップ数（`distance`）を記録する。
3. 候補の中から主seedを次の順で選ぶ。
   - (a) `class_type` に `Sampler` または `Noise` を含むもの（大文字小文字は区別しない）のうち、`distance` が最小のもの
   - (b) (a)に該当がなければ、`distance` が最小のもの
   - 同点の場合は、ノードIDを数値として比較し、小さい方を選ぶ
4. 主サンプラーの決め方
   - `SamplerCustomAdvanced` 系のように、seedを `RandomNoise` などが持つ構成もある。
   - そのため `sampler` 欄（5.4節）には、上流探索で最初に見つかった `class_type` に `Sampler` を含むノードを使う。
   - seedのノードとサンプラーのノードが違っていてもよい。

### 6.3 プロンプトの取得

- `positive_text` / `negative_text` が接続されていれば、その値を使う（`source: "input"`）。バッチやリストで渡された場合は、`batch_index` に対応する要素を使う。要素数が足りなければ最後の要素を使う。
- 未接続の場合は、主サンプラーの `positive` / `negative` 入力からリンクを上流へたどり、最初に見つかった文字列ウィジェットを使う（`source: "auto"`）。
  - 文字列ウィジェットは `populated_text`、`text`、`prompt` の優先順で探す。
  - `YoshiakiWildcardEncode` は `wildcard_text` ではなく `populated_text` を使うこと。
- 探索途中で文字列ウィジェットがリンクになっていて実際の値が得られない場合は、空文字とし `source: "unresolved"` にする（例: PromptTranslatorの出力がつながっている場合）。
- 該当がなければ空文字で `source: "none"` にする。

### 6.4 モデルの抽出（`models`）

`nodes` の中から、次のウィジェット名を持つノードを抽出する。

| ウィジェット名 | kind |
|---|---|
| `ckpt_name` | checkpoint |
| `unet_name` | unet |
| `clip_name`、`clip_name1`、`clip_name2`… | clip |
| `vae_name` | vae |
| `lora_name` | lora |
| その他の `*_name` で、値の拡張子が `.safetensors` / `.gguf` / `.ckpt` / `.pt` / `.pth` / `.sft` のもの | other |

- 強度のウィジェット（`strength_model`、`strength_clip`、`strength`）があれば併記する。
- `YoshiakiWildcardEncode` の `<lora:…>` 構文で適用されたLoRAは `populated_text` に含まれているため、ここでは抽出しない。プロンプト側に残っていれば再現できる。

---

## 7. 実装の進め方

1. **タスク0（検証済み・2026-11-01）**：XMPの書き込みは **`pillow-jxl-plugin` の `xmp=` 引数**で行う（第4章の呼び出し方）。検証結果は次の通り。実装前に、手元の環境で最後の未確認項目だけ確認すること。
   - 検証環境：pillow-jxl-plugin 1.3.8 / Pillow 12.3.0 / Python 3.13（Linux）
   - `xmp=` で渡したバイト列が、そのまま `xml ` ボックスに格納される（`compress_metadata=False` の場合）。`True` にすると `brob` ボックスになる。
   - 日本語、`<&>"`、改行を含むプロンプトや、2^64-1 のseed文字列が、そのまま読み戻せる。
   - ロスレス保存（RGB / RGBA）は元画像と完全に一致する。quality=90の非可逆保存でもXMPを付けられる。
   - Windows（Python 3.12 / 3.13、win_amd64）用のビルド済みパッケージがPyPIで配布されている。
   - Pillow本体（12.3.0）にはJXLの機能がないため、Pillow単体では実現できない。
   - **未確認**：`exiftool -XMP:all -G1 xxx.jxl` での読み取り。手元のWindows版exiftoolで1回確認し、結果を `docs/yoshiaki/` 配下のタスク記録に残すこと。
   - `requirements.txt` に `pillow-jxl-plugin` を追加する。
2. ファイル名・フォルダ処理を移植する（第3章）。
3. JXLの保存とプレビューを実装する（第4章）。
4. XMPの生成を実装する（第5章・第6章）。
5. `requirements.txt` と README（ノード一覧と説明、ライセンス欄）を更新する。

---

## 8. 受け入れ基準

- [ ] 本家と同じ `filename_keys` / `foldername_keys` の指定で、同じフォルダ構成・ファイル名になる（本家READMEの例3つで確認）
- [ ] `counter_digits=0` で連番なしになる。既存の `.jxl` があれば、その最大番号の次から連番が続く
- [ ] `lossless=True` で保存した画像をデコードすると、元のテンソルと一致する（8bit変換後）
- [ ] `exiftool -XMP:all` で `ycomfy:*` と `dc:description` が読める
- [ ] `ycomfy:Parameters` がJSONとしてパースでき、`schema` / `version` が正しい
- [ ] seedに `randomize` を設定した場合、ワークフロー上の値ではなく実際に使われた値が記録される
- [ ] `positive_text` に PromptTranslator の `combined_prompt` をつないだ場合、翻訳後の文字列が記録される
- [ ] 未接続でも、CLIPTextEncode と YoshiakiWildcardEncode の構成ではプロンプトが自動で取得できる
- [ ] KSampler構成と SamplerCustomAdvanced + RandomNoise構成の両方で、主seedが正しく選ばれる
- [ ] バッチサイズ4で保存すると、各ファイルの `batch_index` が0〜3になる
- [ ] `write_xmp=False` のときはXMPなしで保存される
- [ ] Windowsネイティブ版とpodmanコンテナ版の両方で動作する

---

## 9. 次の段階（この指示書の範囲外）

XMPを読み取る**画像ロードノード**は、別の指示書で作る。前提は次の通り。

- `xml ` ボックス（と、念のため `brob` ボックス）からXMPを取り出し、`ycomfy:Parameters` を正として読む。
- **`Image.open()` ではXMPを取得できない。** pillow-jxl-pluginの読み込み処理はEXIFしか `im.info` に入れないため（`im.info` には `icc_profile` しかないことを確認済み）。
  - XMPは `pillow_jxl.Decoder()(バイト列)` の戻り値の5番目（ボックス一覧）から、`box_type == b"xml "` のボックスの `data` を取り出す。
  - `brob` ボックスは圧縮されたまま返ってくるので、読む場合は自前でBrotliを展開する必要がある（先頭4バイトが元のボックス種別）。本ノードは `brob` を書かないため、対応は任意とする。
  - 画像そのものは、これまで通り `Image.open()` で読み込んでよい。
- 出力：`IMAGE`、`seed`（INT）、`positive_text` / `negative_text`（STRING）、パラメータJSON（STRING）
- ノード上には主要パラメータを表示する。
- そのため本指示書の第5章は変更しないこと。変更が必要になった場合は、5.5節のルールに従うこと。
