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
  - 「Select to add Wildcard」で選んだワイルドカードは`wildcard_text`の**カーソル位置**へ挿入される（範囲選択中はその部分を置き換え）。区切りの`, `は前後に必要なときだけ自動で付く（先頭・改行直後・既に`,`がある位置には付けない）。テキストエリアに一度もカーソルを置いていない場合は従来どおり末尾へ`, `区切りで追記（2026-11-14変更）。挿入処理は「LoRA Add」と共通の`js/yoshiaki-text-insert.js`
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
  - **`top_p`は送信しない**（2026-11-22変更）: リクエストに`top_p`を含めず、サーバー側の設定（llama-serverの`presets.ini`等）の値をそのまま使わせる。以前は内部固定値`1.0`を常に送っていたため、preset側の`top_p`が上書きされていた。開始時のサマリ行は`top_p=server`と表示する。`YoshiakiPromptTranslator`も共通の`build_chat_payload()`を使うため同じ挙動
  - **`temperature`は0なら送信しない**（2026-11-22変更、既定値も0.3→0に変更）: `temperature`が0のときはリクエストに含めず、サーバー側の設定（presets.ini等）の値を使わせる。0より大きい値を入れたときだけその値を送る（presetと違う値を試したいとき用）。リトライ時の「+0.2ずつ上げる」調整（13.2）は、0（送らない）のときは行わず`max_tokens`の縮小だけにする（サーバー側の実際の値が分からないため）。ログでは送らない場合`temp=server`と表示する。ウィジェットに「0 = 送信しない」のtooltipを追加
  - **コンテキスト長の取得**（2026-09-19追加）: 13.6.1 の `max_tokens` 自動増量のクランプに使うコンテキスト長を、`max_context_window`（Lemonade）→ `meta.n_ctx`（llama-server、ロード中のモデルのみ）→ `status.args` の `--ctx-size`（llama-server、全モデル）の順に解決する
- **備考**:
  - `class_type`は`YoshiakiLLMCaptionGenerator`、表示名は`Yoshiaki-LLMCaptionGenerator`、`CATEGORY`は`yoshiaki-comfy/LLM`
  - 他のComfyUIカスタムノードパックへのコード依存なし（`tags`入力はワークフロー上でWD14Tagger等を繋ぐ運用であり、コード上のimport依存ではない）
  - 「Refresh Models」ボタン追加により、既存の保存済み`YoshiakiLLMCaptionGenerator`ワークフローで`model`より後ろのウィジェット（`enable_thinking`以降）の位置が1つずれる可能性がある（Wildcard Folder等追加時と同種の影響）
  - 2026-09-08の`tags`/`image_names`の`forceInput`化でこれらのウィジェットが無くなるため、`widgets_values`を位置で復元する古いフロントエンドでは保存済みワークフローの値が2つ分ずれる可能性がある（`widgets_values_named`を持つ新しいフロントエンドでは名前で復元されるため影響なし）。また`tags`は必須入力のため、未接続だと実行時に「入力が不足」エラーになる（以前は空欄のまま実行できた）
  - 統合元リポジトリの開発履歴は[docs/yoshiaki/tasks_done.LLM.md](docs/yoshiaki/tasks_done.LLM.md)、詳細仕様書は[docs/yoshiaki/LLM_Caption_Node_指示書.md](docs/yoshiaki/LLM_Caption_Node_指示書.md)として本リポジトリに保存（本体の`docs/yoshiaki/tasks_done.md`には統合せず、別ファイルとして参照用に保管）
  - 2026-09-06、Lemonade Server呼び出し・リトライ／タイムアウト分類・ログ書き込み・システムプロンプトのメタデータ判定など画像非依存の共通ロジックを`modules/yoshiaki_llm/llm_common.py`に切り出した（`YoshiakiPromptTranslator`との共有のため）。本ノード固有のロジック（画像前処理・PART1/PART2分割・trigger_word処理等）は`llm_caption_node.py`にそのまま残っており、本ノードの入出力・挙動に変更はない
  - `temperature`=0 は「greedyを送る」ではなく「送らない」の意味になった。greedy相当にしたいときは0.01等を入れるか、preset側で設定する。既定値の変更は新規配置のノードにだけ効き、保存済みワークフローの値（0.3等）はそのまま送られる
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
  - `system_prompts_translate/`フォルダ内の`.txt`ファイル（1行目`<!-- output_mode: prompt_translation -->`）でプロンプトを切り替え可能。**作風（アニメ調／実写）ごとに別ファイルを用意し、ここで切り替える**（2026-11-14にモデル別から作風別へ方針変更。モデル固有の調整が必要になったらファイルを追加する。ノードのコード変更は不要）
  - 出力は`combined_prompt`（`fixed_tags`＋翻訳結果を結合した完成形）と`translated_prompt`（翻訳結果のみ、デバッグ用）の2つ。`combined_prompt`では`fixed_tags`と翻訳結果の間を**改行＋空行1つ**で区切る（2026-11-14変更、それ以前は`, `で1行につないでいた）。`fixed_tags`は末尾の`,`も含めて書かれたまま使い（前後の空白・改行だけ落とす）、翻訳結果は末尾の`,`を取り除く。片方が空ならもう片方だけを出す
  - `japanese_prompt`が空欄のときはLLMを呼ばず`fixed_tags`のパススルーとして扱う。`system_prompt_file`が不正なときは`fixed_tags`の有無に関わらず両出力とも空文字にする
  - `YoshiakiLLMCaptionGenerator`と共通のLemonade Server呼び出し・リトライ／タイムアウト分類・ログ書き込みロジック（`modules/yoshiaki_llm/llm_common.py`）を再利用。画像バッチという処理軸が無いため`INPUT_IS_LIST`は宣言していない（ウィジェット値はスカラーのまま届く）
  - 実行ログを`modules/yoshiaki_llm/logs_translate/`に出力（`.gitignore`対象。キャプションノードの`logs/`とは別フォルダ）
  - `model`コンボの「Refresh Models」ボタン・host/port変更時の自動再取得は`YoshiakiLLMCaptionGenerator`と共通の仕組み（`js/yoshiaki-llm.js`）で本ノードにも対応済み
  - **llama-server（ルータモード）対応**（2026-09-19追加）: 共通ロジック（`llm_common.py`）側の対応により、本ノードも Lemonade / llama-server のどちらにも接続できる。ただし本ノードは画像を扱わないため、`YoshiakiLLMCaptionGenerator` で有効にしている**画像対応モデルへの絞り込みは行わず、常に全モデルが `model` コンボに出る**
  - `top_p`はリクエストに含めない。`temperature`も0（既定値）なら送らず、リトライ時の温度上げもしない（2026-11-22変更、`YoshiakiLLMCaptionGenerator`と共通。サーバー側の設定値が使われる）
  - 起動時・F5時・キュー投入時の接続先を`yoshiaki-llm.ini`から解決する仕組みと、`VALIDATE_INPUTS(cls, model)`による`model`のコンボ検証除外も`YoshiakiLLMCaptionGenerator`と共通（詳細は同ノードの項を参照）。`yoshiaki-llm.ini`は両ノードで共有する1ファイルで、どちらのノードの再取得でも更新される
- **備考**:
  - `class_type`は`YoshiakiPromptTranslator`、表示名は`Yoshiaki-PromptTranslator`、`CATEGORY`は`yoshiaki-comfy/LLM`
  - `system_prompts_translate/`は`YoshiakiLLMCaptionGenerator`用の`system_prompts/`とは物理的に別フォルダ。互いのコンボボックスに相手のファイルは表示されず、`output_mode`の値を間違えて逆フォルダに置いた場合も`INVALID_PROMPT_FILE`扱いで即座に失敗する（安全側）
  - 同梱のシステムプロンプトは`translate_anime.txt`（アニメ調向け、Anima等）と`translate_photo.txt`（実写向け）の2つ（2026-11-14追加）。どちらもキャラ定義・タグは`fixed_tags`側で別に書く前提で、構図・背景・光・雰囲気などの日本語を**英語の自然文1段落**に翻訳する（タグ列にはしない。人物描写が含まれていればそれも翻訳し、入力に無い品質タグ・作風の言葉は足さない）。違いは役割の説明と使う語彙だけで、実写版は撮影用語（`shallow depth of field`、`bokeh`、`golden hour`など）を使ってよく、レンズ・カメラ・フィルム名は入力に書かれたときだけ使う。`.txt`を配置するだけでコンボボックスに表示される
  - `scene_from_toriigate.txt`（2026-11-14追加）は翻訳ではなく、ToriiGate-0.5が出力したmin_structured_md形式の**英文**からキャラ固有の要素を消すプロンプト。同じ構図・背景で別キャラの画像を作るためのもの。`japanese_prompt`にToriiGateの文章（英文のままでよい）、`fixed_tags`に新しいキャラの定義を入れる。`# 1. Thoughts about characters`を削除、キャラ名は`she`/`the girl`等に置き換え、キャラ名の見出しは`## Character`にし、ほかの見出しは残す。消すのは体の特徴（髪・瞳・肌の色、髪の長さ・髪型、獣耳・角・尻尾・翼、体型・胸の大きさ、タトゥー・ほくろ・傷）だけで、服装・小物・持ち物・ポーズ・表情・構図・背景・エフェクトは残す。出力が複数行のMarkdownになるため、応答が短すぎてリトライしたときにノードが付け足す「no markdown」の念押し（`FORMAT_CORRECTION_NOTE`）とは相性が悪い（その回だけ見出しが消える可能性がある）
  - `translate_anime.txt`は当初`translate_anima.txt`という名前だった（2026-11-14に改名）。旧名を選んで保存したワークフローは選び直しが必要。選び直さないとキュー投入時の`system_prompt_file`のコンボ検証で弾かれ、その出力系統が黙って捨てられる（`VALIDATE_INPUTS`で検証を外しているのは`model`だけ）
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
  - `Select to add LoRA`で選んでも即座にはプロンプトへ追加されず、選択中のLoRA名がコンボの表示に反映されるだけ（2026-09-04変更、下記タスク参照）。「LoRA Info」で内容確認、「LoRA Add」を押したときだけ`<lora:名前>`が`wildcard_text`の**カーソル位置**へ挿入される（範囲選択中はその部分を置き換え。テキストエリアに一度もカーソルを置いていない場合は末尾へ追記。2026-11-14変更、それ以前は常に末尾へ追記）
  - [rgthree-comfy](https://github.com/rgthree/rgthree-comfy)（MIT）のPower Lora Loaderにある同種機能を参考に、**独自に書き直した縮小版**（コードの移植ではない）
  - **トリガーワード表示**（2026-11-21追加）: 「LoRA Add」の下に**1行の**読み取り専用の欄を置き（2026-11-23に1行化。長いときはマウスを乗せると全文が出る）、`Select to add LoRA`でLoRAを選ぶたびに、そのsafetensorsのヘッダー（`__metadata__`）から読んだトリガーワードを`, `区切りで表示する（無ければ`(no trigger words)`）。**表示だけで、`wildcard_text`へ自動挿入はしない**。探す順は`modelspec.trigger_phrase`（カンマ分割）→`ss_tag_frequency["trigger_words"]`バケットのキー（lora-finalizeが書くもの）。kohyaの通常の`ss_tag_frequency`（学習タグ全部）はトリガーワード扱いしない。「LoRA Info」ダイアログにもTrigger Words欄（Copy／カーソル位置へInsert、取得元の表示）を追加
- **備考**:
  - トリガーワード欄は専用ルート`/yoshiaki/lora_trigger`を使う。`/yoshiaki/lora_info`は毎回ファイル全体のsha256を計算するため、選ぶたびに呼ぶと大きいLoRAで待たされる。こちらはヘッダーだけ読み、ハッシュもキャッシュも使わない（Civitaiの`trainedWords`はハッシュが要るので欄には出さず、Infoダイアログだけに出る）
  - トリガーワード欄は`serialize = false`（`widgets_values`にもpromptにも入らない）なので保存済みワークフローの位置ずれは起きないが、ノードが1行ぶん縦に伸びる。欄は標準の複数行STRINGではなく`addDOMWidget`の1行`<input>`で、`getMinHeight`/`getMaxHeight`を同じ値（ボタンの高さ`LiteGraph.NODE_WIDGET_HEIGHT`＋margin×2）にして高さを固定している。フロントエンドはDOMウィジェットを上下左右`margin`（既定10px）ずつ内側に縮めて置くので、高さを決めるときはmargin分を足すこと（標準の複数行欄は最小の高さがあり、ノードを広げると伸びるため1行にできない）。選択中のLoRA自体がワークフローに保存されない（`serializeValue`が常にラベルを返す）ため、読み込み直後の欄は空
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

### YoshiakiLoadImageJXL

- **実装日**: 2026-11-03
- **カスタムノードの機能の概要**:
  - ComfyUIの`input`フォルダ（サブフォルダ含む、拡張子の大文字小文字無視）の`.jxl`・`.png`・`.jpg`・`.jpeg`を読み込む（2026-11-28にPNG/JPG対応、それ以前は`.jxl`のみ）。値は`/`区切りの相対パス
  - **PNG/JPGは画像（IMAGE/MASK）だけ**: メタデータ（PNGのtEXtやJPGのEXIF等）は読まず、テキスト・数値の出力は常に空文字／0。概要欄には「PNG/JPG: メタデータ読み込み非対応（画像のみ）」と出る。標準`LoadImage`と同じく、全形式でEXIFの回転情報（`ImageOps.exif_transpose`）を適用し、パレット＋`transparency`のPNGは透過をMASKにする
  - 出力は`IMAGE`/`MASK`/`positive_text`/`negative_text`/`seed`(INT)/`steps`(INT)/`cfg`(FLOAT)/`note`/`parameters_json`（`ycomfy:Parameters`の元の文字列）。値が無ければ空文字／0でエラーにしない
  - `YoshiakiSaveImageJXL`のXMP（保存指示書第5章 v1）を`ycomfy:Parameters`優先で読み、無い・壊れている場合は`ycomfy:Seed`等の重複プロパティから読む（`status: partial`）。`version > 1`は警告付きで読める範囲だけ読む
  - JSで「画像をアップロード」ボタン（標準`/upload/image`へ送信。2026-11-28に「JXLをアップロード」から改名、PNG/JPGも選べる）、サーバー変換のWebPプレビュー、ポジティブ／ネガティブ／概要の読み取り専用欄をノードに追加。ファイル選択時・ワークフロー読み込み時に実行前でも表示を更新する
  - サーバールート: `/yoshiaki/jxl/list`・`/yoshiaki/jxl/preview`（長辺512pxのWebP）・`/yoshiaki/jxl/info`（画像をデコードせずXMPだけ読む）
  - 詳細仕様は[docs/yoshiaki/JXL_Load_Node_指示書.md](docs/yoshiaki/JXL_Load_Node_指示書.md)
- **備考**:
  - `class_type`は`YoshiakiLoadImageJXL`、表示名は`Yoshiaki Load Image JXL`（PNG/JPG対応後も保存済みワークフロー互換のため据え置き。サーバールート名`/yoshiaki/jxl/*`も同様）、`CATEGORY`は`yoshiaki-comfy/image`、`NODE_VERSION = "1.0.0"`（`modules/yoshiaki_load_jxl/load_jxl.py`）
  - 名前空間URI・`SCHEMA_ID`・`SCHEMA_VERSION`は`yoshiaki_save_jxl.metadata`からimportしている（二重定義しない）。保存ノードのコードは変更していない
  - `xmp_read.normalize()`がノード出力と`/info`ルートの共通の唯一の変換元。表示と出力を食い違わせないため、片方だけで値を加工しないこと
  - XMPはISOBMFFボックスを自前で走査して取り出す（`jxl_boxes.py`。`pillow_jxl.Decoder()`は画像全体をデコードするため使わない）。`brob`（圧縮XMP）は`brotli`がある場合のみ読む
  - 表示用ウィジェット（アップロードボタン・プレビュー・3つのテキスト欄）はすべて`serialize = false`かつ`options.serialize = false`。`widgets_values`にもAPIのpromptにも入らない
  - アルファなしのMASKは**64×64の全0**（指示書は「画像と同じサイズ」を想定していたが、タスク0で確認した現行の標準`LoadImage`が64×64のため、標準に合わせた）
  - pillow-jxl-plugin 1.3.8は**アニメーション非対応**（`n_frames`が常に1）で、**16bitのRGB/RGBAは8bitに丸めて返す**。16bitグレースケールだけ`I;16`で来るので65535で割る
  - `filename`の検証は`files.resolve()`に集約（絶対パス・ドライブレター・`..`・realpathがinput外になるシンボリックリンクを拒否）。ルートは400、`VALIDATE_INPUTS`はエラーメッセージを返す
  - `pillow-jxl-plugin`が無い環境ではこのノードとルートだけ登録しない（保存ノードと同じ方式）。PNG/JPGだけ使う場合も同じく登録されない
  - 対応拡張子は`files.py`の`IMAGE_EXTS`とJSの`IMAGE_EXTS`の2か所で定義している（増やすときは両方直す）。XMPを読むのは`files.is_jxl()`が真のときだけ
  - 配布予定なし、個人利用限定

---

### Yoshiaki-ResolutionLatent

- **実装日**: 2026-11-23
- **カスタムノードの機能の概要**:
  - 標準の「Resolution Selector」と「Empty Latent Image」を1つにまとめたノード。モデル別プリセット（TOML）からアスペクト比・メガピクセル・倍数を選び、幅・高さ（INT）と全ゼロの潜在画像（LATENT）を出力する
  - プリセットはルート直下の`yoshiaki-resolution-latent.toml`（`.gitignore`対象）。無ければ起動時に`yoshiaki-resolution-latent.toml.example`をコピーして作る。以後は手書きファイル扱いで、ノードから書き戻さない。起動時に1回だけ読む（編集後はComfyUI再起動）
  - アスペクト比の書式: `16:9` / `2.39:1` / `1.85`（`:1`扱い） / 固定解像度`1152x896`（`x`・`×`）。半角スペース以降はラベル。横長と正方形だけ書き、縦長は「向き」欄で作る（固定解像度にも適用）。「カスタム」を選ぶと「カスタム比率」欄の文字列を使う
  - サイズ計算: `scale = sqrt(mp×1024² / (rw×rh))`、各辺を倍数へ**四捨五入**（`floor(x/m+0.5)*m`。Pythonの`round()`は偶数丸めでJSとずれるため使わない）。16:9・1.00MP・倍数16 → 1360×768
  - 倍数は必要倍数（汎用＝実際の縮小率、それ以外＝`lcm(preset.multiple, 実際の縮小率)`）の倍数へ切り上げる（警告付き）
  - 潜在画像の形状: VAE接続時はVAEの`latent_channels`・`spacial_compression_encode()`、未接続時はプリセットの`latent_channels`・`downscale`。`[batch, C, h/d, w/d]`の4次元で、`{"samples", "downscale_ratio_spacial": d}`を返す（標準EmptyLatentImageと同じキー・device・dtype）
  - 確定したプリセット値（ComfyUI 0.46.2の`comfy/supported_models.py`・`latent_formats.py`で確認）: Anima・Krea2 → `Wan21`（16ch・1/8・3次元）、MOSS-Image → `Flux2`（128ch・1/16・2次元）、汎用 → 4ch・1/8（標準Empty Latent Imageと同じ。本体の自動補正に任せる）
  - 推奨解像度（2026-11-23に各公式情報で調整。出典は`.example`のコメントに記載）: Anima `mp_range = [0.25, 2.25]`（公式「512²〜1536²で動作」）、Krea2 `[1.0, 4.0]`（ComfyUI公式「1K〜2K」、公式カードの例は1024²/2048²）、MOSS-Image `[1.0, 2.0]`（公式USERGUIDE「1M/1.5M/2M推奨、0.25M〜4Mまで外挿可、辺は16の倍数」）。MOSS-Imageのアスペクト比は公式Gradioプリセットの横長・正方形（1:1, 4:3, 3:2, 16:9, 2:1, 3:1, 4:1, 8:1）で、公式の`fit_size`と全画素数プリセット×比率で同じサイズになることを確認済み。Anima・Krea2は公式の解像度リストが無いため、アスペクト比は指示書の初期値のまま。既定MPは3モデルとも1.0
  - **Illustrious**（2026-11-23追加）: SDXL系なので`SDXL`形式（4ch・1/8、ComfyUI 0.46.2で確認）。`mp_range = [0.25, 2.25]`（公式モデルカードOnomaAIResearch/Illustrious-XL-v1.0のネイティブ1536×1536を上限、下限512²は公式記載が無くコミュニティガイドの「512x512〜1536x1536」に合わせた）。既定MPは1.0（v0.1系の派生モデルは1MP前後が基本のため）。アスペクト比は比率6種＋SDXL標準バケットの固定解像度4種（`1152x896`・`1216x832`・`1344x768`・`1536x640`、ラベル`SDXL`）。汎用ではなくモデルプリセット扱いなので、4ch・1/8以外のVAEをつなぐと食い違い警告が出る
  - JS（`js/yoshiaki-resolution-latent.js`）: ユーザーが「モデル」を変えるとアスペクト比の選択肢をそのモデルのリスト＋「カスタム」に差し替え、「倍数」「メガピクセル」にプリセット値を入れる。ワークフロー読み込み時は選択肢の差し替えだけで値は上書きしない（リストに無い保存値は一時的に選択肢へ追加して警告）。ノード下部に幅・高さ・MP・潜在形状のライブ表示（プリセット値）、実行後はPythonの`ui`から実際の形状・決定元（VAE／プリセット／汎用）・警告を表示
  - サーバールート: `GET /yoshiaki/resolution_latent/presets`
  - 計算部分は`modules/yoshiaki_resolution_latent/calc.py`（ComfyUI非依存）と`js/yoshiaki-resolution-latent-calc.js`の二重実装。テストケース`tests/cases.json`を両方で共有している
  - 詳細仕様は[docs/yoshiaki/ResolutionLatent_Node_指示書.md](docs/yoshiaki/ResolutionLatent_Node_指示書.md)
- **備考**:
  - `class_type`は`YoshiakiResolutionLatent`、表示名は`Yoshiaki-ResolutionLatent`、`CATEGORY`は`yoshiaki-comfy/latent`。入力の表示名は日本語（`display_name`）、出力の`RETURN_NAMES`は`潜在画像`/`幅`/`高さ`
  - 実装前確認（ComfyUI 0.46.2）: `fix_empty_latent_channels`（KSampler・SamplerCustom系の両方から呼ばれる）は、全ゼロの潜在画像のチャンネル数をモデルに合わせ、`downscale_ratio_spacial`が違えばnearest-exactでリサイズし、`latent_dimensions==3`なら次元を足す。そのため4次元で出せば十分で、5次元出力は実装していない（Anima・Krea2・MOSSの3モデルで、標準Empty Latentと補正後の形状が一致することを確認済み）
  - `VALIDATE_INPUTS(cls, model_preset, aspect_ratio)`でこの2つだけCOMBOの標準チェックを外している（プリセットから消したモデル名・アスペクト比で保存したワークフローも警告付きで実行できる）。**`**kwargs`を付けないこと**（他の入力のmin/maxチェックまで外れる）
  - 汎用プリセットではVAEとの食い違い警告を出さない（汎用は4ch・1/8なので、最近のVAEをつなぐと必ず食い違うため）
  - 汎用プリセット（1/8）を縮小率16のモデル（MOSS等）で使うと、本体が潜在画像を1/2にリサイズする。倍数8で`幅/8`が奇数になると、出力の幅・高さと実際の画像サイズが8pxずれる（標準Empty Latentと同じ挙動）。既定の倍数16なら起きない
  - 「カスタム比率」欄は「カスタム」以外のとき`widget.disabled`でグレーアウトする（非表示にはしていない）
  - 表示用DOMウィジェットは`serialize = false`。`widgets_values`にもpromptにも入らない
  - 単体テストは`pytest modules/yoshiaki_resolution_latent/tests`（`tests/pytest.ini`でrootdirを固定。無いとpytestがルートの`__init__.py`をimportして`folder_paths`が無いと失敗する）
  - 動作確認したフロントエンド: `comfyui_frontend_package` 1.59.6（ComfyUI 0.46.2、2026-11-23 ユーザーが実機確認）
  - 本ノードの読み込み失敗でパック全体は止めない（ルート`__init__.py`で`try`）
  - 配布予定なし、個人利用限定

---
