# YoshiakiLoadImageJXL 指示書

作成日: 2026-11-03
対象リポジトリ: https://github.com/Yoshiaki21/yoshiaki-comfy
配置先（この指示書）: `docs/yoshiaki/JXL_Load_Node_指示書.md`
前提となる指示書: `docs/yoshiaki/JXL_Save_Node_指示書.md`（以下「保存指示書」）

---

## 0. 目的と前提

- ComfyUI標準の `Load Image`（`LoadImage`）と同じ使い勝手で、**JPEG XL（.jxl）だけ**を読み込むノードを yoshiaki-comfy に追加する。
- `YoshiakiSaveImageJXL` がXMPに書き込んだ再現用情報（ポジティブ/ネガティブプロンプト、seed、サンプラー設定、モデルなど）を読み取り、**ノード上に表示**し、**出力ソケットからも取り出せる**ようにする。
- 対応形式は .jxl のみ。PNG/JPEG/WebPなどは扱わない（保存は今後JXLに統一するため）。
- XMPの仕様は保存指示書の第5章（XMP仕様 v1）を**唯一の正**とする。本ノード側の都合で第5章を変更しないこと。
- 自分専用で、配布はしない。
- 動作環境は Windowsネイティブ版ComfyUI と、Linuxのpodmanコンテナ版ComfyUI の両方。どちらでも動くこと。
- ブラウザがJXLを表示できるかどうかに**依存しない**こと（プレビューはサーバー側で変換して返す。3章）。

---

## 1. 配置・命名

| 項目 | 値 |
|---|---|
| クラス名 / ノードID | `YoshiakiLoadImageJXL` |
| 表示名 | `Yoshiaki Load Image JXL` |
| モジュール | `modules/yoshiaki_load_jxl/` |
| カテゴリ | `yoshiaki-comfy/image`（保存ノードと同じ） |
| 登録 | `__init__.py` の保存ノードと同じ方式。`pillow-jxl-plugin` が無い場合はこのノードだけ無効化し、ログにエラーを出す（保存ノードの `try/except ImportError` と同じ形） |
| フロントエンド | `js/yoshiaki-load-jxl.js` |
| ノードバージョン | モジュール内に `NODE_VERSION = "1.0.0"` を定義 |

モジュール構成（目安）:

| ファイル | 役割 |
|---|---|
| `load_jxl.py` | ノード本体（入出力、画像デコード、テンソル化） |
| `jxl_boxes.py` | JXLコンテナのボックス走査とXMPの取り出し（4.1節） |
| `xmp_read.py` | XMPの解析と `ycomfy:Parameters` の読み取り・正規化（4.2〜4.4節） |
| `server.py` | 一覧・プレビュー・メタデータ取得のサーバールート（3章） |

- 名前空間URI・`SCHEMA_ID`・`SCHEMA_VERSION` などの定数は、`yoshiaki_save_jxl.metadata` から**importして使う**。値をコピーして二重定義しないこと。

---

## 2. 入出力

### 必須入力

| 名前 | 型 | 説明 |
|---|---|---|
| `image` | COMBO | ComfyUIの `input` フォルダ内の .jxl ファイル一覧（2.1節） |

### hidden入力

なし。

### 出力

| 順 | 名前 | 型 | 内容 |
|---|---|---|---|
| 0 | `IMAGE` | IMAGE | 画像（標準Load Imageと同じ形式） |
| 1 | `MASK` | MASK | アルファから作るマスク（標準Load Imageと同じ規則） |
| 2 | `positive_text` | STRING | ポジティブプロンプト。無ければ空文字 |
| 3 | `negative_text` | STRING | ネガティブプロンプト。無ければ空文字 |
| 4 | `seed` | INT | 主seed。無ければ `0` |
| 5 | `steps` | INT | `sampler.steps`。無ければ `0` |
| 6 | `cfg` | FLOAT | `sampler.cfg`。無ければ `0.0` |
| 7 | `note` | STRING | `note`（保存時の `xmp_note`）。無ければ空文字 |
| 8 | `parameters_json` | STRING | `ycomfy:Parameters` の**元の文字列そのまま**。無ければ空文字 |

- `sampler_name` / `scheduler` は出力ソケットにしない。KSamplerのCOMBO型と型が一致せず接続できないため。値はノード上の表示と `parameters_json` で確認する。
- 値が無い場合（XMPなし、キーなし）は**エラーにしない**。上記の既定値を返し、ノード上に「メタデータなし」等を表示する。
- `seed` は `seed.value`（10進数文字列）を `int()` で変換する。変換できない場合は `0` とし、ログに警告を出す。

### 2.1 ファイル一覧

- 対象は `folder_paths.get_input_directory()` 配下の .jxl ファイル（拡張子の大文字小文字は区別しない）。
- **サブフォルダも再帰的に含める**。値は input フォルダからの相対パスで、区切りは `/` に統一する（例: `chara_a/0001.jxl`）。
- 名前順でソートする。
- `folder_paths.filter_files_content_types()` は使わない。.jxl のMIMEタイプが環境によって判定されず、一覧から消えるため。
- 一覧は `INPUT_TYPES()` で毎回作り直す（ComfyUIのF5や「Refresh」で更新される標準の挙動に合わせる）。

### 2.2 実行時の挙動（標準Load Imageに合わせる）

- `IS_CHANGED`：ファイル内容のSHA-256を返す（標準と同じ）。
- `VALIDATE_INPUTS`：ファイルが存在し、拡張子が `.jxl` で、input フォルダの外を指していないことを確認する。満たさなければエラーメッセージを返す。
- 画像のデコードは `pillow_jxl` を明示的にimportしたうえで `Image.open()` で行う（保存指示書9章の通り、画像はこれで読める）。
- 複数フレーム（アニメーションJXL）の場合は、標準Load Imageと同じく `ImageSequence` でフレームを列挙し、最初のフレームと同じサイズのものだけをバッチにまとめる。pillow-jxl-pluginが複数フレームに対応していない場合は1フレーム目だけでよい（タスク0で確認）。
- モードごとの変換:

| モード | IMAGE | MASK |
|---|---|---|
| `RGB` | そのまま 0〜1 に正規化 | 全0（64×64ではなく画像と同じサイズの全0。標準の現行実装に合わせる。タスク0で確認） |
| `RGBA` | RGBに変換 | `1 - alpha` |
| `L` | RGBに変換 | 全0 |
| `LA` | RGBに変換 | `1 - alpha` |
| `I;16` / `I` | **65535で割って** 0〜1 にしてからRGB化（8bitに丸めない） | 全0 |
| `F` | 0〜1にクリップしてRGB化 | 全0 |

- 16bitを8bitに丸めると保存側でロスレス保存した値が再現できなくなるため、`I;16` は `convert("RGB")` に直接渡さないこと。
- XMPの読み取り（4章）に失敗しても、画像の読み込みは続行する。ログに警告を出し、メタデータなしとして扱う。

---

## 3. サーバールートとフロントエンド

### 3.1 なぜ標準のアップロード・プレビューを使わないか

- 標準Load Imageのプレビューは、ブラウザが `/view` から元ファイルを直接表示する仕組み。ブラウザがJXLに対応していないとプレビューが壊れる。
- そのため **`image_upload: True` は付けない**。アップロードボタンとプレビューは本ノードのJSで実装する。

### 3.2 ルート

すべて `PromptServer.instance.routes` に登録する。パスは既存ノードに合わせて `/yoshiaki/jxl/...` とする。

| メソッド・パス | 内容 |
|---|---|
| `GET /yoshiaki/jxl/list` | 2.1節の一覧をJSON配列で返す |
| `GET /yoshiaki/jxl/preview?filename=...` | プレビュー画像を返す。長辺512pxに縮小したWebP（品質85）。アルファは保持する |
| `GET /yoshiaki/jxl/info?filename=...` | 4章で読み取ったメタデータを、4.4節の正規化した形のJSONで返す |

- `filename` は2.1節の相対パス。**inputフォルダの外を指すパス（`..`、絶対パス、ドライブレター等）は400を返す**。`os.path.realpath` で解決した結果がinputフォルダ配下であることを確認する。
- `preview` と `info` は `(パス, 更新日時, サイズ)` をキーにメモリ内でキャッシュしてよい（上限は数十件程度。LRUで十分）。
- `info` は**画像をデコードせずに**XMPだけを読む（4.1節のボックス走査を使う）。ファイル選択のたびに呼ばれるため。

### 3.3 アップロード

- JSでノードに「JXLをアップロード」ボタンを追加する。
- 選択できるファイルは `.jxl` のみ（`accept=".jxl"`）。
- ComfyUI標準の `POST /upload/image` に送り、成功したら一覧を再取得して、アップロードしたファイルを選択状態にする。
- `/upload/image` がJXLを拒否する場合（タスク0で確認）は、`POST /yoshiaki/jxl/upload` を自作する。保存先はinputフォルダ直下、同名ファイルがあれば標準と同じく連番を付ける。
- キャンバスへの.jxlのドラッグ＆ドロップでノードを作る機能は**範囲外**（9章）。

### 3.4 ノード上の表示

- ファイルを選択したとき（コンボの値が変わったとき、およびワークフロー読み込み時）に `/yoshiaki/jxl/info` と `/yoshiaki/jxl/preview` を呼び、**実行しなくても**表示を更新する。
- 実行後の `onExecuted` でも同じ内容で更新する（サーバーから `ui` でinfoを返す）。
- 表示する内容:

| 欄 | 内容 |
|---|---|
| プレビュー | `/yoshiaki/jxl/preview` の画像 |
| ポジティブ | 読み取り専用の複数行テキスト |
| ネガティブ | 読み取り専用の複数行テキスト |
| 概要 | 読み取り専用の複数行テキスト。次の項目を1行ずつ。値が無い項目は行ごと省略する |

概要の項目と並び順:

```
seed: 123456789012345 (KSampler #3)
steps: 30 / cfg: 5.0 / sampler: euler / scheduler: normal / denoise: 1.0
size: 1024 x 1536 (lossless) または (quality 90)
models: xxx.safetensors / yyy.safetensors (lora 0.8/0.8)
created: 2026-11-01 22:19:05 +09:00
note: …
saved by: YoshiakiSaveImageJXL 1.0.0 / ComfyUI 0.x.x
schema: v1
```

- メタデータが無い場合は概要欄に「XMPメタデータなし」、`ycomfy:Parameters` が無く他のXMPプロパティだけ読めた場合は「簡易メタデータ（Parametersなし）」と表示する。
- 対応していないスキーマバージョン（`version` > 1）の場合は、概要の先頭に「⚠ 未対応のスキーマ v{version}。読める範囲だけ表示」と表示する。
- **表示用のウィジェットは `serialize = false` にして、ワークフローの `widgets_values` に入れない**。保存済みワークフローでウィジェットの位置がずれる問題（CLAUDE.mdの過去事例）を避けるため。
- テキスト欄は選択してコピーできること。
- 既存の `js/yoshiaki-wd14tagger.js` の `ComfyWidgets["STRING"]` を使った表示方法を参考にする。

---

## 4. XMPの読み取り

### 4.1 ボックス走査（`jxl_boxes.py`）

`pillow_jxl.Decoder()` でもボックス一覧は取れるが、画像全体をデコードするため遅い。ファイル選択のたびに呼ぶ `info` のために、**ISOBMFFのボックスを自前で走査**する。

- ファイル先頭が `FF 0A`（コンテナなしの素のコードストリーム）の場合は、ボックスが無いのでXMPなしとする。
- ファイル先頭が `00 00 00 0C 4A 58 4C 20 0D 0A 87 0A`（`JXL ` シグネチャボックス）の場合にボックスを順に読む。
  - ボックスヘッダ: 4バイトのサイズ（ビッグエンディアン）＋4バイトの種別。
  - サイズが `1` のときは、続く8バイトが64bitのサイズ。
  - サイズが `0` のときは、ファイル末尾まで。
  - サイズがヘッダ長より小さい、またはファイル末尾を超える場合は、そこで走査を打ち切る（壊れたファイル対策）。
- `xml ` ボックスが見つかったら、その中身をXMPとして返す。複数ある場合は最初のもの。
- `brob` ボックスで、中身の先頭4バイトが `xml ` の場合は、残りをBrotliで展開してXMPとして使う。`brotli` パッケージが無ければ、ログに警告を出してスキップする（保存ノードは `brob` を書かないため任意対応）。
- 画像データ（`jxlc` / `jxlp`）は読み飛ばす。ファイル全体をメモリに読み込まないこと（`seek` で飛ばす）。
- テストでは、同じファイルに対して `pillow_jxl.Decoder()` の戻り値の5番目から取った `xml ` ボックスの中身と、バイト単位で一致することを確認する。

### 4.2 XMPの解析（`xmp_read.py`）

- `xml.etree.ElementTree.fromstring()` にバイト列のまま渡して解析する（`<?xpacket ...?>` は処理命令なのでそのまま解析できる）。
- 名前空間URIで要素を探す。接頭辞の文字列では探さない（他のツールが別の接頭辞で書き直す可能性があるため）。
- `rdf:Description` が複数ある場合も、すべての中から探す。
- 読み取る要素:

| 要素 | 用途 |
|---|---|
| `ycomfy:Parameters` | **正**。中身をJSONとして読む |
| `ycomfy:SchemaVersion` | `Parameters` が無いときの参考 |
| `ycomfy:Seed` / `ycomfy:PositivePrompt` / `ycomfy:NegativePrompt` / `ycomfy:Note` | `Parameters` が無い、または壊れているときの代替 |
| `dc:description` の `rdf:Alt/rdf:li` | ポジティブプロンプトの最終手段 |
| `xmp:CreatorTool` / `xmp:CreateDate` | 表示用の代替 |

- XMPとして解析できない場合は、例外を投げずに「メタデータなし」として扱い、ログに警告を出す。

### 4.3 `ycomfy:Parameters` の扱い

- まず `schema == "yoshiaki-comfy/jxl-params"` と `version` を確認する。
  - `schema` が違う：Parametersなしとして扱い、4.2節の代替要素を使う。
  - `version == 1`：そのまま読む。
  - `version > 1`：警告を表示し（3.4節）、v1と同じキー名で読める範囲だけ読む。
- **知らないキーは無視する**（保存指示書5.5節。キーの追加は互換性のある変更）。
- 値が重複していて食い違った場合は `Parameters` を優先する（保存指示書5.3節）。
- `seed.value` は文字列のまま保持し、INT出力するときだけ `int()` する。JSに渡すときは**文字列のまま**渡す（2^53を超えるseedの精度落ち対策）。
- `nodes` は大きくなりうるので、`info` ルートの応答には含めない（`parameters_json` 出力には元の文字列ごと含まれる）。

### 4.4 正規化した形（`info` ルートの応答・ノード内部で共通に使う）

```json
{
  "status": "ok | partial | none | unsupported_version",
  "schema_version": 1,
  "positive": "…",
  "negative": "…",
  "seed": "123456789012345",
  "seed_source": {"node_id": "3", "class_type": "KSampler"},
  "sampler": {"steps": 30, "cfg": 5.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0},
  "image": {"width": 1024, "height": 1536, "lossless": false, "quality": 90, "filename": "…", "subfolder": "…"},
  "models": [{"kind": "checkpoint", "name": "xxx.safetensors"}, {"kind": "lora", "name": "yyy.safetensors", "strength_model": 0.8, "strength_clip": 0.8}],
  "created_at": "2026-11-01T22:19:05+09:00",
  "note": "…",
  "generator": {"node": "YoshiakiSaveImageJXL", "node_version": "1.0.0", "comfyui_version": "…"},
  "warnings": ["…"]
}
```

- `status` の意味:
  - `ok`：`Parameters` を読めた
  - `partial`：`Parameters` が無い／壊れていて、代替要素から読んだ
  - `none`：XMPが無い、またはyoshiaki-comfyの情報が無い
  - `unsupported_version`：`version > 1`（読める範囲は埋める）
- 値が無いキーは `null` または省略する。表示側は両方を「無し」として扱う。
- 実行時の出力（2章）と `info` ルートは、**同じ正規化関数**から作る。表示と出力が食い違わないようにするため。

---

## 5. 依存パッケージ

- `pillow-jxl-plugin`：既に `requirements.txt` にある（保存ノードと共通）。
- `brotli`：任意。`requirements.txt` には追加せず、無い場合は `brob` ボックスを読まないだけにする。
- それ以外の新しい依存は追加しない。

---

## 6. 実装の進め方

1. **タスク0（確認）**：実装前に、手元の環境で次を確認し、結果を `docs/yoshiaki/tasks_done.md` のタスク記録に残すこと。
   - 現在のComfyUIの `LoadImage`（`nodes.py`）の実装を読み、MASKの既定値、フレーム処理、`IS_CHANGED`/`VALIDATE_INPUTS` を本ノードに合わせる。
   - `POST /upload/image` が .jxl ファイルを受け付けるか。
   - pillow-jxl-plugin（1.3.8）で、アニメーションJXLの複数フレームを `ImageSequence` で列挙できるか。
   - pillow-jxl-pluginで16bitのJXLを開いたときのモード（`I;16` 等）。保存ノードで16bit保存はしていないので、テスト用ファイルは別途作る。
2. `jxl_boxes.py` を実装し、保存ノードで作ったファイルで4.1節のテストを行う。
3. `xmp_read.py` を実装する（4.2〜4.4節）。
4. ノード本体 `load_jxl.py` を実装する（2章）。
5. `server.py` のルートを実装する（3.2節）。
6. `js/yoshiaki-load-jxl.js` でアップロード・プレビュー・表示を実装する（3.3〜3.4節）。
7. `__init__.py` への登録、`CLAUDE.md` の「含まれるカスタムノード」、`docs/yoshiaki/tasks_done.md`、READMEを更新する。

---

## 7. 受け入れ基準

- [ ] input フォルダ（サブフォルダ含む）の .jxl だけが一覧に出る。.png などは出ない
- [ ] `YoshiakiSaveImageJXL` で保存したファイルを選ぶと、**実行前に**プレビュー・ポジティブ・ネガティブ・概要が表示される
- [ ] ブラウザがJXLに対応していなくてもプレビューが表示される（Chrome／Edgeで確認）
- [ ] 実行すると、各出力ソケットに4.4節と同じ値が出る。表示と出力が一致する
- [ ] `seed` 出力をKSamplerの `seed` に接続でき、2^53を超えるseedでも保存時の値と一致する
- [ ] `positive_text` を `CLIPTextEncode` の `text`（入力化したもの）に接続して、元の画像を再生成できる
- [ ] ロスレス保存した画像を読み込むと、保存前のテンソルと一致する（8bit変換後）
- [ ] RGBAの画像で、MASKが `1 - alpha` になる
- [ ] `write_xmp=False` で保存したファイル、XMPの無いJXL、コンテナ形式でない素のJXLを読んでもエラーにならず、「XMPメタデータなし」と表示される
- [ ] `ycomfy:Parameters` を削除したXMPのファイルでも、代替要素からプロンプトとseedが表示される（`status: partial`）
- [ ] `version: 2` に書き換えたファイルで警告が表示され、読める範囲は表示される
- [ ] `filename=../../xxx` や絶対パスを指定したルート呼び出しが400になる
- [ ] 「JXLをアップロード」で追加したファイルが一覧に出て、選択状態になる
- [ ] 表示用ウィジェットが `widgets_values` に入らない（ワークフローを保存して再読み込みしても `image` の値がずれない）
- [ ] Windowsネイティブ版とpodmanコンテナ版の両方で動作する

---

## 8. 既存ノードへの影響

- `YoshiakiSaveImageJXL` のコード・XMP仕様は変更しない。定数のimportのみ。
- 定数以外に保存ノードの関数を流用したい場合は、保存ノードの挙動を変えない範囲で `yoshiaki_save_jxl/metadata.py` から共通関数として切り出してよい。その場合は保存ノードの受け入れ基準を再確認する。

---

## 9. 範囲外（この指示書では作らない）

- キャンバスへの .jxl のドラッグ＆ドロップでノードを作る機能
- JXLからのワークフロー復元（保存ノードはワークフローを書き込まない）
- XMPの編集・書き戻し
- outputフォルダから直接読み込む機能（必要になったら別途検討。当面はinputフォルダへコピーまたはアップロードして使う）
- PNG等、JXL以外の形式
- `YoshiakiLoRACaptionLoad` のJXL対応（別タスク）
