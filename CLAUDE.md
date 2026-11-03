# yoshiaki-comfy

これは、ComfyUIようのカスタムノードです。
ノードを追加した場合、下の含まれるカスタムノードの仕様に合わせて追記、同じノードを変更した場合は、変更後の内容に修正
ノード追加や修正をした履歴は、/docs/yoshiaki/tasks_done.mdに履歴を追記していってください。

---

## 含まれるカスタムノード

- **実装日**: YYYY-MM-DD
- **カスタムノードの機能の概要**:
  - 箇条書きでどんな機能があるか
- **備考**: 使う際の気を付けることがある場合は記述、なければ空白で
```

<!-- 以下に含まれるカスタムノードを追記 -->

---

### YoshiakiWildcardProcessor / YoshiakiWildcardEncode

- **実装日**: 2026-09-02
- **カスタムノードの機能の概要**:
  - ComfyUI-Impact-Packの`ImpactWildcardProcessor`/`ImpactWildcardEncode`を個人利用向けに切り出して単独パック化したもの
  - `wildcard_text`にワイルドカード構文（`__name__`, `{a|b}`, `N#__name__`, `__name#N__`固定行選択など）を書くと`populated_text`に解決結果を生成
  - `YoshiakiWildcardEncode`はさらに`<lora:name>` / `<lora:name:weight>` / `<lora:name:model_weight:clip_weight>`構文でLoRA適用し、CLIP条件付けまで出力
  - `mode`（populate/fixed/reproduce）による実行前自動生成・固定・再現の切り替えに対応（サーバーフック込みで移植済み）
  - ワイルドカードファイルの置き場所は`wildcards/`フォルダがデフォルト。ルート直下に`yoshiaki-wildcard.ini`を作り`custom_wildcards`キーで別フォルダを指定すると、そちらのみを参照する（custom-onlyモード）
- **備考**:
  - 元のImpact-Packと異なり、ワイルドカード内容は毎回ディスクから読み直す（no-cache固定、キャッシュ設定なし）
  - Inspire Pack連携（LBW=構文）・nunchaku専用ローダー連携（LOADER=構文）は含まれていない（未使用のため意図的に省略）
  - `class_type`名を`YoshiakiWildcardProcessor`/`YoshiakiWildcardEncode`にしているため、元のComfyUI-Impact-Packと同時にインストールしてもノード名は衝突しない
  - 配布予定なし、個人利用限定

---

### Yoshiaki-LLMCaptionGenerator

- **実装日**: 2026-09-03（別リポジトリ[ComfyUI-LLM-Tagger](https://github.com/Yoshiaki21/ComfyUI-LLM-Tagger)からyoshiaki-comfyへ統合）
- **カスタムノードの機能の概要**:
  - 画像とWD14 Tagger等のタグ文字列を、LAN上の**Lemonade Server**（AMDのローカルLLM推論サーバー、OpenAI互換API）に送り、タグ補正・キャプション文生成を行う
  - `system_prompts/`フォルダ内の`.txt`ファイル（1行目の`<!-- output_mode: ... -->`メタデータで`tags_only`/`caption_only`/`both`を判定）でプロンプトを切り替え可能
  - 接続失敗・タイムアウト・応答フォーマット不正を分類し、パラメータ調整しながら自動リトライ
  - 実行ログを`modules/yoshiaki_llm/logs/`に出力（`.gitignore`対象）
  - `model`コンボは`lemonade_host`/`lemonade_port`/`lemonade_api_key`を編集する（確定時。テキストは blur/Enter、数値は変更確定時）たびにLemonade Serverへ再問い合わせして選択肢を更新する。加えて`model`直後の「Refresh Models」ボタンで手動再取得も可能。ワークフロー読み込み直後にも一度自動実行される（2026-09-05追加。`INPUT_TYPES`はサーバー起動時／ブラウザF5時に固定の`DEFAULT_LEMONADE_HOST`/`DEFAULT_LEMONADE_PORT`でしか評価されないため、動的な追従は`js/yoshiaki-llm.js`＋`modules/yoshiaki_llm/server.py`の`/yoshiaki/llm/models`ルートで実現している）。再取得の結果は成否によらずComfyUIのログに1行出る（2026-09-19追加。それ以前は成功時に何も出ず「ボタンが効いていない」ように見えた）
  - **起動時・F5時・キュー投入時の接続先**（2026-09-19追加）: `INPUT_TYPES`はクラスメソッドでノード個別のウィジェット値を見られないため、**最後にモデル一覧の再取得へ成功した接続先をルート直下の`yoshiaki-llm.ini`（自動生成、`.gitignore`対象）に記録し、次回以降はそれを使う**。記録が無い／壊れている場合のみ`DEFAULT_LEMONADE_HOST`/`DEFAULT_LEMONADE_PORT`（`192.168.85.57:8080`。2026-09-19にLemonade Serverの13305から変更）へフォールバックする。記録した値は`model`コンボの取得先と`lemonade_host`/`lemonade_port`ウィジェットの既定値の両方に使われる（新規配置したノードの接続先とコンボの中身が食い違わないようにするため）。書き込むのは**取得に成功したときだけ**で、値が変わったときのみ一時ファイル＋`os.replace`で原子的に置き換える。`api_key`は平文で残さないため保存しない
  - **`model`はコンボの厳密一致検証から除外している**（2026-09-19追加）: ComfyUIはキュー投入のたびに`INPUT_TYPES()`を再評価し、`model`の値がその一覧に含まれるかを検証する。両ノードに`VALIDATE_INPUTS(cls, model)`（常に`True`を返す）を定義して、この`model`に対する汎用検証だけを無効化している
  - ノード上の表記調整（2026-09-08、見た目のみで機能変更なし）: `tags`入力は`forceInput`の接続専用ソケットにし`display_name`を`文字列`（WD14 Taggerの出力ラベルと同じ）に、`image_names`入力も`forceInput`にし`display_name`を`Name list`（LoRA Caption Loadの出力ラベルと同じ）に、出力`RETURN_NAMES`を`caption_text`から`text`（LoRA Caption Saveの`text`入力と同じ）に変更。`reference_tags`には空欄時の説明文（`placeholder`）を設定。Python側の引数名（`tags`/`image_names`）とワークフローJSON上の入力名は変わらない
  - `reference_tags`（optional、複数行STRING、既定空欄、2026-09-06追加）: 衣装LoRA用。衣装生成時に使った基準タグ列を渡すと、`tags`と同じ規則（`resolve_tags_per_image`。1件なら全画像へブロードキャスト、複数件なら画像ごとに1:1対応）で画像に対応付けられ、システムプロンプト側（`caption_training_costume.txt`）で「WD14候補タグのうち衣装そのものを指すものを除外する」判断材料として使われる。空欄なら従来通りプロンプトへのブロック追加自体を行わず、既存の人物用ワークフロー・システムプロンプト（`caption_training_both.txt`等）への影響はゼロ
  - **llama-server（ルータモード）対応**（2026-09-19追加）: 接続先が Lemonade でも llama-server でも動く。`lemonade_host`/`lemonade_port` を llama-server に向けるだけで切り替わり、サーバー種別は `/v1/models` の応答の形から自動判別する（判別専用のリクエストは発行しない）。SSEストリーミング・`stream_options.include_usage`・`reasoning_content` 分離・`chat_template_kwargs.enable_thinking`・画像のdata URI入力はいずれも両サーバー共通で動作する
  - **画像対応モデルのみをコンボに表示**（2026-09-19追加、llama-server接続時のみ）: 本ノードは画像を必須入力とするため、サーバーがモデルごとの対応modality情報を返す場合（llama-server の `architecture.input_modalities`）は画像入力に対応したモデルだけを `model` コンボに出す。Lemonade はこの情報を返さないため従来どおり全件が出る。繋がっているが画像対応モデルが0件の場合は `(no vision-capable model on this server)` と表示し、サーバーに繋がらない場合の表示と区別する
  - **コンテキスト長の取得**（2026-09-19追加）: 13.6.1 の `max_tokens` 自動増量のクランプに使うコンテキスト長を、`max_context_window`（Lemonade）→ `meta.n_ctx`（llama-server、ロード中のモデルのみ）→ `status.args` の `--ctx-size`（llama-server、全モデル）の順に解決する
- **備考**:
  - `class_type`は`YoshiakiLLMCaptionGenerator`、表示名は`Yoshiaki-LLMCaptionGenerator`、`CATEGORY`は`yoshiaki-comfy/LLM`
  - 他のComfyUIカスタムノードパックへのコード依存なし（`tags`入力はワークフロー上でWD14Tagger等を繋ぐ運用であり、コード上のimport依存ではない）
  - 「Refresh Models」ボタン追加により、既存の保存済み`YoshiakiLLMCaptionGenerator`ワークフローで`model`より後ろのウィジェット（`enable_thinking`以降）の位置が1つずれる可能性がある（Wildcard Folder等追加時と同種の影響）
  - 2026-09-08の`tags`/`image_names`の`forceInput`化でこれらのウィジェットが無くなるため、`widgets_values`を位置で復元する古いフロントエンドでは保存済みワークフローの値が2つ分ずれる可能性がある（`widgets_values_named`を持つ新しいフロントエンドでは名前で復元されるため影響なし）。また`tags`は必須入力のため、未接続だと実行時に「入力が不足」エラーになる（以前は空欄のまま実行できた）
  - 統合元リポジトリの開発履歴は[docs/yoshiaki/tasks_done.LLM.md](docs/yoshiaki/tasks_done.LLM.md)、詳細仕様書は[docs/yoshiaki/LLM_Caption_Node_指示書.md](docs/yoshiaki/LLM_Caption_Node_指示書.md)として本リポジトリに保存（本体の`docs/yoshiaki/tasks_done.md`には統合せず、別ファイルとして参照用に保管）
  - 2026-09-06、Lemonade Server呼び出し・リトライ／タイムアウト分類・ログ書き込み・システムプロンプトのメタデータ判定など画像非依存の共通ロジックを`modules/yoshiaki_llm/llm_common.py`に切り出した（`YoshiakiPromptTranslator`との共有のため）。本ノード固有のロジック（画像前処理・PART1/PART2分割・trigger_word処理等）は`llm_caption_node.py`にそのまま残っており、本ノードの入出力・挙動に変更はない
  - 2026-09-19の llama-server 対応でウィジェットの追加・削除・並べ替えは行っていないため、保存済みワークフローの位置ずれは発生しない。ただし llama-server 接続時は `model` の候補が画像対応モデルだけに減るため、画像非対応モデルを選んで保存していたワークフローは JS 側の既存ロジック（候補に無ければ先頭を選ぶ）で別モデルへ切り替わる
  - llama.cpp のコンテキスト超過の実挙動（2026-09-19 実機確認）: `max_tokens` 単体が `n_ctx` を超えてもサーバーはエラーにせず内部で丸める。HTTP 400（`exceed_context_size_error`）になるのは**プロンプト自体**が `n_ctx` を超えた場合で、`classify_error` では `http_400`＝13.2 の縮小対象外になりリトライしても回復しない。クランプの効果は「13.6 の倍増が実際のコンテキスト長で頭打ちになる」点にある
  - `status.args` の `--ctx-size` は起動時の要求値であり、VRAM不足等で llama.cpp 側が小さく確保することがある（実測: `--ctx-size 65536` に対し実際の `meta.n_ctx` は 40960）。このため `--ctx-size` 由来の値は暫定値として扱い、モデルがロードされた後の呼び出しで `meta.n_ctx` の確定値へ差し替える
  - `VALIDATE_INPUTS`には**`model`だけを宣言すること**。`**kwargs`を付けると全入力の検証が無効になり、`temperature`の範囲チェックや`system_prompt_file`のコンボ検証まで効かなくなる（ComfyUIの判定は`execution.py`の`if x not in validate_function_inputs and not validate_has_kwargs:`）。検証に失敗したときのComfyUIの挙動は「プロンプト自体はHTTP 200で受理し、**その出力系統だけを黙って捨てる**」（ログに`Output will be ignored`が出るだけ）なので、原因に気づきにくい
  - `yoshiaki-llm.ini`が保持できる接続先は**1組だけ**。同じクラスのノードを複数置いて別々のサーバーへ向けた場合、記録されるのは最後に再取得へ成功した1つだけになる（F5時は全ノードが再取得するため順序は非決定的）。ただし`VALIDATE_INPUTS`で`model`の検証を外してあるため、記録から漏れたノードでもキュー投入が弾かれることはない
  - 自動生成ファイルを`yoshiaki-wildcard.ini`と同居させてはいけない。あちらは手書きの設定ファイルで、`configparser`で書き戻すとユーザーが書いたコメント行が消える（実測: ヘッダのコメントが消え、インラインコメントは値へ混入する）
  - 配布予定なし、個人利用限定

---

### Yoshiaki-PromptTranslator

- **実装日**: 2026-09-06
- **カスタムノードの機能の概要**:
  - 日本語プロンプトをAnima等の画像生成モデル向け英語プロンプトに変換する
  - `fixed_tags`（翻訳不要の品質タグ・score系・人数/構図タグ等、そのまま先頭に使われる）と`japanese_prompt`（翻訳対象の日本語本文）を別入力にして、日本語部分だけをLLMに渡す
  - `system_prompts_translate/`フォルダ内の`.txt`ファイル（1行目`<!-- output_mode: prompt_translation -->`）でプロンプトを切り替え可能。**変換先モデル（Anima／Krea2／Qwen-Image-Editなど）ごとに別ファイルを用意し、ここで切り替える想定**（ノードのコード変更は不要）
  - 出力は`combined_prompt`（`fixed_tags`＋翻訳結果を結合した完成形）と`translated_prompt`（翻訳結果のみ、デバッグ用）の2つ
  - `japanese_prompt`が空欄のときはLLMを呼ばず`fixed_tags`のパススルーとして扱う。`system_prompt_file`が不正なときは`fixed_tags`の有無に関わらず両出力とも空文字にする
  - `YoshiakiLLMCaptionGenerator`と共通のLemonade Server呼び出し・リトライ／タイムアウト分類・ログ書き込みロジック（`modules/yoshiaki_llm/llm_common.py`）を再利用。画像バッチという処理軸が無いため`INPUT_IS_LIST`は宣言していない（ウィジェット値はスカラーのまま届く）
  - 実行ログを`modules/yoshiaki_llm/logs_translate/`に出力（`.gitignore`対象。キャプションノードの`logs/`とは別フォルダ）
  - `model`コンボの「Refresh Models」ボタン・host/port変更時の自動再取得は`YoshiakiLLMCaptionGenerator`と共通の仕組み（`js/yoshiaki-llm.js`）で本ノードにも対応済み
  - **llama-server（ルータモード）対応**（2026-09-19追加）: 共通ロジック（`llm_common.py`）側の対応により、本ノードも Lemonade / llama-server のどちらにも接続できる。ただし本ノードは画像を扱わないため、`YoshiakiLLMCaptionGenerator` で有効にしている**画像対応モデルへの絞り込みは行わず、常に全モデルが `model` コンボに出る**
  - 起動時・F5時・キュー投入時の接続先を`yoshiaki-llm.ini`から解決する仕組みと、`VALIDATE_INPUTS(cls, model)`による`model`のコンボ検証除外も`YoshiakiLLMCaptionGenerator`と共通（詳細は同ノードの項を参照）。`yoshiaki-llm.ini`は両ノードで共有する1ファイルで、どちらのノードの再取得でも更新される
- **備考**:
  - `class_type`は`YoshiakiPromptTranslator`、表示名は`Yoshiaki-PromptTranslator`、`CATEGORY`は`yoshiaki-comfy/LLM`
  - `system_prompts_translate/`は`YoshiakiLLMCaptionGenerator`用の`system_prompts/`とは物理的に別フォルダ。互いのコンボボックスに相手のファイルは表示されず、`output_mode`の値を間違えて逆フォルダに置いた場合も`INVALID_PROMPT_FILE`扱いで即座に失敗する（安全側）
  - `prompt_translation`用システムプロンプトファイルの内容そのもの（Anima版・Krea2版・Qwen-Image-Edit版）は本タスクのスコープ外。配置するだけでコンボボックスに表示される
  - バッチ処理（複数プロンプト一括変換）、翻訳結果の後処理（禁止語チェック等）は未対応
  - 配布予定なし、個人利用限定

---

### YoshiakiLoRACaptionLoad / YoshiakiLoRACaptionSave

- **実装日**: 2026-09-04（自分のフォーク[Image-Captioning-in-ComfyUI](https://github.com/Yoshiaki21/Image-Captioning-in-ComfyUI)からyoshiaki-comfyへ統合。本家は[LarryJane491/Image-Captioning-in-ComfyUI](https://github.com/LarryJane491/Image-Captioning-in-ComfyUI)）
- **カスタムノードの機能の概要**:
  - `YoshiakiLoRACaptionLoad`: 指定フォルダ内のPNG画像を読み込み、画像バッチ・ファイル名一覧・pathを出力
  - `YoshiakiLoRACaptionSave`: ファイル名一覧・path・キャプション文字列を受け取り、画像と同名の`.txt`をプレフィックス付きで保存（LoRA学習用データセット準備）
  - WD14 Taggerと組み合わせて使う想定（コード上の依存ではなくワークフロー上の連携）
  - `YoshiakiLoRACaptionSave`に`output_path`（保存先を`path`と分けて指定、指定時は元画像もコピーする）と`overwrite`（既存ファイルを無視して`Name list`順に上書きする）を追加（2026-09-04）
  - `YoshiakiLoRACaptionLoad`の潜在バグを修正（2026-09-04）: 画像0枚時（PNGが1枚も無い場合）に明確な`FileNotFoundError`を出すようにした、画像1枚のときに出力の型が壊れる不具合を修正（1枚/複数枚を統一処理）、画像枚数をノード自身のUI表示にのみ出すようにした（`{"ui": {"text": [...]}, "result": (...)}`形式。他ノードへは渡らず`RETURN_TYPES`は3出力のまま変更なし）
  - ファイル名とキャプションのずれを修正（2026-09-08）: `YoshiakiLoRACaptionSave`は`INPUT_IS_LIST = True`で`text`のリスト全件を1回で受け取り、`Name list`のi番目とキャプションのi番目を位置ベースで1対1対応させて書き出す（インスタンス内カウンター`_overwrite_index`は廃止）。`overwrite`はOFFで「既に`.txt`がある名前をスキップ」、ONで「上書き」のみを意味し、対応付けには影響しない。件数不一致は警告して少ない方の件数分だけ書く。`YoshiakiLoRACaptionLoad`は`Name list`と`Image list`を`list_image_files()`による単一走査（拡張子の大文字小文字を無視、ディレクトリ除外、ファイル名順ソート）から作る
- **備考**:
  - `class_type`/表示名は`YoshiakiLoRACaptionLoad`/`YoshiakiLoRACaptionSave`(表示名は`Yoshiaki LoRA Caption Load`/`Yoshiaki LoRA Caption Save`)、`CATEGORY`は`yoshiaki-comfy/LoRA`
  - フォーク元の3つの既存パッチ（`cstr`未import対策、prefix空文字対策、`IS_CHANGED`未定義対策）をそのまま維持して移植
  - PNGのみ対応の制約は本家のまま。「同名`.txt`が既存のフォルダに対して実行するとエラー」という制約は2026-09-08の修正で解消（OFF時はスキップ、ON時は上書き）
  - ComfyUIはノードオブジェクトを`caches.objects`にノードID単位でキャッシュし、キュー実行をまたいで同じインスタンスを再利用する（`--cache-none`起動時を除く）。このパック内のノードで`self.xxx`に実行状態を持たせる設計は避けること（2026-09-08のずれ不具合の直接原因）
  - 配布予定なし、個人利用限定

---

### YoshiakiWD14Tagger

- **実装日**: 2026-09-04（自分のフォーク[ComfyUI-WD14-Tagger](https://github.com/Yoshiaki21/ComfyUI-WD14-Tagger)からyoshiaki-comfyへ統合。本家は[pythongosssss/ComfyUI-WD14-Tagger](https://github.com/pythongosssss/ComfyUI-WD14-Tagger)、MITライセンス）
- **カスタムノードの機能の概要**:
  - 画像をWD14系ONNXモデルでbooruタグ形式にタグ付け
  - フォーク独自機能: タグの優先順位並べ替え（`priority.json`定義のカテゴリ順）、`exclude_tags`のワイルドカード対応（`fnmatch`）、推論をCPU限定（`ortProviders`）
  - 選択したモデルが未取得の場合、実行時にHugging Faceから自動ダウンロード（`modules/yoshiaki_wd14tagger/models/`に保存、`.gitignore`対象）
- **備考**:
  - `class_type`/表示名は`YoshiakiWD14Tagger`/`Yoshiaki WD14 Tagger`、`CATEGORY`は`yoshiaki-comfy/LLM`（画像タグ分類モデルでありLLMではないが、ユーザー希望によりLLMカテゴリに配置）
  - 本家の`pysssss.py`が提供していた「ComfyUI上のどの画像でも右クリックしてその場でタグ付けする」というキャンバス全体に影響する機能と、それが使う`/pysssss/wd14tagger/tag`サーバールートは**未使用のため統合せず削除**（ユーザーは`Yoshiaki WD14 Tagger`ノードをワークフロー上に置いて使う通常の方法のみ利用。この削除はノードとしての通常動作には無関係）
  - 本家の`pysssss.py`が持っていたレガシーJSインストール機構（`web/extensions/pysssss`へのシンボリックリンク作成）も、yoshiaki-comfyが既にモダンな`EXTENSION_WEB_DIRS`方式を使っているため不要と判断し統合せず（`modules/yoshiaki_wd14tagger/helpers.py`に必要な部分のみ再実装）
  - 新規pip依存: `onnxruntime`, `tqdm`（`requirements.txt`に追加）
  - モデル保存先はComfyUI共通の`models/`フォルダではなく、拡張機能フォルダ内（`modules/yoshiaki_wd14tagger/models/`）を選択（このノードでしか使わないため。ユーザー確認済み）
  - 設定は`config.json`（既定値・既知モデル一覧）＋任意の`config.user.json`（ローカル上書き、`.gitignore`対象、`config.user.json.example`参照）
  - 配布予定なし、個人利用限定

---

### LoRA Info（YoshiakiWildcardEncode の付随機能。ノードではない）

- **実装日**: 2026-09-04
- **機能の概要**:
  - `YoshiakiWildcardEncode`の「Select to add LoRA」の下に「LoRA Info」「LoRA Add」の2ボタンを追加
  - `Select to add LoRA`で選んでも即座にはプロンプトへ追加されず、選択中のLoRA名がコンボの表示に反映されるだけ（2026-09-04変更、下記タスク参照）。「LoRA Info」で内容確認、「LoRA Add」を押したときだけ`<lora:名前>`が`wildcard_text`へ追加される
  - [rgthree-comfy](https://github.com/rgthree/rgthree-comfy)（MIT）のPower Lora Loaderにある同種機能を参考に、**独自に書き直した縮小版**（コードの移植ではない）
- **備考**:
  - モジュールは`modules/yoshiaki_lora_info/lora_info.py`（新規パッケージ、ノードではないため`NODE_CLASS_MAPPINGS`には登録しない）。サーバールートは`/yoshiaki/lora_info`（取得）・`/yoshiaki/lora_info/refresh`（Civitaiへ強制再取得）
  - 新規pip依存なし（本家rgthree-comfyは同期的な`requests`を使うが、こちらは既存の`aiohttp`で非同期に書き直した）
  - キャッシュは`modules/yoshiaki_lora_info/cache/`（ハッシュ単位、`.gitignore`対象）に完全に独立して保存。本家rgthree-comfyの`<LoRA名>.rgthree-info.json`サイドカーファイルや専用userdataディレクトリには一切触れない（同じ環境に両方入っていても干渉しない）
  - 含めなかったもの: 編集可能なメモ欄、独自の動画再生コントロール（ブラウザ標準の`<video controls>`で代替）、開発者向けメニュー、モデル一覧取得/削除/保存等の管理系API
  - ユーザー追加要望として「全トリガーワードを一括コピー」ボタンを追加（本家rgthree-comfyには無い機能）
  - JS側で「Select to add LoRA」の直後にボタンウィジェットを挿入するため、既存の保存済み`YoshiakiWildcardEncode`ワークフローで`seed`の位置がさらに1つずれる可能性がある（Wildcard Folder・LoRA Folder追加時と同様の影響。「LoRA Add」追加で4回目、読み取り専用「LoRA Selected」表示欄追加で5回目の位置ずれ）
  - `Select to add LoRA`は、ComfyUIの「モデルファイル不足」チェック対象となる本体ウィジェット（`combo`タイプ、フォルダ込みフルパスを保持、非表示化）と、ユーザーが実際に操作する表示用ウィジェット（`button`タイプ＋`LiteGraph.ContextMenu`による自前ポップアップ、ファイル名のみ表示、`Select to add LoRA`という名前・表示は一切持たない）の2つに分離して実装（`js/yoshiaki-wildcard.js`）。見た目上は行が増えず、警告も出ない
  - 配布予定なし、個人利用限定

---


### YoshiakiSaveImageJXL

- **実装日**: 2026-11-03
- **カスタムノードの機能の概要**:
  - 画像をJPEG XL（`.jxl`）だけで保存する。ファイル名・フォルダの決め方は[save-image-extended-comfyui](https://github.com/audioscavenger/save-image-extended-comfyui)（2.88、GPL-3.0）の`generate_custom_name`／`get_latest_counter`等を移植（`modules/yoshiaki_save_jxl/naming.py`）。`id.widget`、widget名、未知キー＝固定文字列、`/`・`../`でサブフォルダ、`.custom_string`、`ckpt_path`/`lora_path`/`control_net_path`、日時書式、`named_keys`、`resolution`に対応
  - 連番は`.jxl`ファイルだけを数える。`counter_digits=0`で連番なし
  - エンコードは`pillow-jxl-plugin`（`quality`/`lossless`/`effort`）。RGBAはアルファを保持
  - `write_xmp=True`で、再生成に必要な情報をXMP（非圧縮の`xml `ボックス）に書き込む。**ワークフロー本体は書き込まない**。XMP仕様v1（名前空間`ycomfy`、正となるデータは`ycomfy:Parameters`のJSON）は指示書第5章の**確定仕様**
  - seed／主サンプラーは`images`入力から上流への幅優先探索で自動判定（`primary_node`で上書き可）。プロンプトは`positive_text`/`negative_text`入力が優先、未接続なら主サンプラー（またはその上流のCFGGuider等）の`positive`/`negative`から`populated_text`→`text`→`prompt`の順で自動取得
  - 詳細仕様は[docs/yoshiaki/JXL_Save_Node_指示書.md](docs/yoshiaki/JXL_Save_Node_指示書.md)
- **備考**:
  - `class_type`は`YoshiakiSaveImageJXL`、表示名は`Yoshiaki Save Image JXL`、`CATEGORY`は`yoshiaki-comfy/image`、`NODE_VERSION = "1.0.0"`（`save_jxl.py`。XMPに書き込まれる）
  - **XMPの構造・`ycomfy:Parameters`のJSONスキーマを変えるときは指示書5.5節に従う**（キー追加は`version: 1`のまま、削除・型や意味の変更は`version: 2`）。後で作る画像ロードノードがこの仕様に依存する
  - `INPUT_IS_LIST = True`（リスト出力の`positive_text`を画像と添字で対応付けるため）。ウィジェット値・hidden入力もリストで届くので`_first()`で取り出す。画像は全バッチを平坦化して`batch_index`を振る
  - `pillow-jxl-plugin`が無い環境では、ルートの`__init__.py`がこのノードだけを登録せずにエラーログを出す（パック全体は止めない）
  - 本家との違い: 保存先がoutputフォルダ外になる`../`はエラーにする。本家がimport時に行う`locale.setlocale(LC_TIME, '')`はプロセス全体に影響するため移植していない（`%a`/`%b`/`%c`/`%p`などロケール依存の日時書式だけ結果が変わり得る）
  - XMPの名前空間宣言は`ElementTree`の仕様で`x:xmpmeta`にまとめて出力される（指示書5.6の例では`rdf:Description`上だが、XMLとして等価）
  - `pillow-jxl-plugin`の`Image.open()`はXMPを`im.info`に入れない。読み取りは`pillow_jxl.Decoder()(bytes)`の5番目の戻り値（ボックス一覧）から`box_type == b"xml "`を探す
  - 配布予定なし、個人利用限定

---
