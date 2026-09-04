# 完了タスク記録

## 記録フォーマット
完了タスクは以下の形式で追記すること。


```
---

## タスク[番号]: [タイトル]

- **完了日**: YYYY-MM-DD
- **動作確認**: ✅済み / ⬜未確認
- **新規ファイル**:
  - `パス/ファイル名` : 用途
- **修正ファイル**:
  - `パス/ファイル名` : 変更内容を一言で
- **変更内容**:
  - 箇条書きで何をしたか
- **備考**: ハマった点・注意事項（なければ省略）
```

<!-- 以下に完了タスクを追記 -->

---

## タスク: YoshiakiLoRACaptionLoad の画像枚数表示が空になる不具合を修正（OUTPUT_NODE未設定が原因）

- **完了日**: 2026-09-04
- **動作確認**: ⬜未確認（コード修正のみ。ユーザー側で実機確認予定）
- **新規ファイル**: なし
- **修正ファイル**:
  - `modules/yoshiaki_loracaption/lora_caption.py` : `YoshiakiLoRACaptionLoad`に`OUTPUT_NODE = True`を追加
  - `js/yoshiaki-loracaption.js` : `widget.inputEl.value`も明示的に設定、`setDirtyCanvas`で再描画を強制するよう堅牢化
- **変更内容**:
  - 前タスクでJSを追加したところ、表示欄自体は作られるが中身が空という報告を受けた
  - 原因調査の結果、ComfyUIは`{"ui": {...}}`の中身を、`OUTPUT_NODE = True`が指定されているノード（`SaveImage`や`YoshiakiLoRACaptionSave`等）以外には転送しない可能性が高いと判断。`YoshiakiLoRACaptionLoad`には`OUTPUT_NODE`が未設定だったため、`onExecuted`は呼ばれるがメッセージの中身が空になっていたと推測される
  - `OUTPUT_NODE = True`を追加して対応
- **備考**: 実機確認待ち。これでも解消しない場合は、`api.addEventListener("executed", ...)`で実際のメッセージ内容をログ出力して原因を再調査する

---

## タスク: YoshiakiLoRACaptionLoad の画像枚数表示にJSを追加（ui.textが自動描画されなかったため）

- **完了日**: 2026-09-04
- **動作確認**: ⬜未確認（コード修正のみ。ユーザー側で実機確認予定 — 前タスクで実機確認した際、`ui.text`だけでは画面に何も表示されないことが判明したための対応）
- **新規ファイル**:
  - `js/yoshiaki-loracaption.js` : `YoshiakiLoRACaptionLoad`実行後、読み取り専用のテキストウィジェットを追加/更新して画像枚数を表示する
- **修正ファイル**: なし（`__init__.py`の`EXTENSION_WEB_DIRS`は既に`js/`フォルダ全体を指しているため、ファイル追加のみで反映される）
- **変更内容**:
  - Python側が返す`{"ui": {"text": [...]}}`は、ComfyUIコアが画像プレビュー(`ui.images`)のようには自動描画してくれないことが実機確認で判明
  - ComfyUI-Custom-Scripts の `ShowText` ノードと同じ手法（`nodeType.prototype.onExecuted`をフックし、`ComfyWidgets["STRING"]`で読み取り専用ウィジェットを都度作り直す）で対応
  - `path`ウィジェット（INPUT_TYPESで宣言された唯一のウィジェット）は残し、それより後ろのウィジェット（前回実行時の表示用ウィジェット）だけを毎回クリアしてから新しいものを追加するため、実行を繰り返しても表示が積み重ならない
- **備考**: なし

---

## タスク: YoshiakiLoRACaptionLoad の潜在バグ修正（画像0枚・1枚のケース）

- **完了日**: 2026-09-04
- **動作確認**: ✅済み（スタンドアロンスクリプトで3パターンを検証: ①PNGが1枚も無いフォルダを渡すと明確な`FileNotFoundError`になること、②画像がちょうど1枚のフォルダで`RETURN_TYPES`(3出力)と一致した正しい戻り値になること、③画像が複数枚の既存動作に影響が無いこと。いずれも`ui`の画像枚数表示が正しい値になることも確認。ComfyUI実機での確認はユーザー側で実施予定）
- **新規ファイル**: なし
- **修正ファイル**:
  - `modules/yoshiaki_loracaption/lora_caption.py` : `YoshiakiLoRACaptionLoad.captionload()`を修正
- **変更内容**:
  - **画像0枚（PNGが1枚も無い）の場合**: 拡張子フィルタ後のファイル数チェックを追加し、`FileNotFoundError(f"No PNG images found in path '{path}'.")`を明示的に送出するようにした（修正前は`image1`が未定義のまま参照され、分かりにくい`UnboundLocalError`になっていた）
  - **画像がちょうど1枚の場合**: `if len(images)==1: return (images[0], 1)`という、`RETURN_TYPES`（3出力: Name list, path, Image list）と噛み合わない特殊分岐を削除。1枚でも複数枚でも同じバッチ化ループで処理する統一実装に変更（ループは`images[1:]`が空なら自然に1回も回らないだけなので、1枚のケースも複数枚のケースと同じコードパスで正しく動く）
  - **戻り値の形**: 従来`return text, path, image1, len(images)`と`RETURN_TYPES`(3個)に対して4値returnしていた食い違いを解消。`len(images)`（画像枚数）は他ノードへの出力にはせず、`{"ui": {"text": [...]}, "result": (text, path, image1)}`という ComfyUI標準の「ui表示専用」形式で`YoshiakiLoRACaptionLoad`自身のノード上にのみ表示するようにした（`RETURN_TYPES`は3出力のまま変更なし、既存ワークフローの出力配線に影響なし）
  - ついでに、実質到達不能だった`os.path.ex`という存在しない属性への参照（`if os.path.isdir(image_path) and os.path.ex:`）も、意図を保ったまま`if os.path.isdir(image_path): continue`に修正（今回のリファクタ対象コードに含まれていたため合わせて修正。動作は変わらない）
- **備考**:
  - `ui`によるノード上のテキスト表示が実際にComfyUIのフロントエンドで見えるかは、ComfyUIのバージョンに依存する可能性がある（ユーザーと合意済みの方針: まずJS無しの標準的な`ui`形式で実装し、実機で表示されなければ専用のJSを追加する）。実機での見た目確認が必要
  - 配布予定なし、個人利用限定

---

## タスク: YoshiakiLoRACaptionSave に output_path（保存先分離＋画像コピー）と overwrite（上書き）を追加

- **完了日**: 2026-09-04
- **動作確認**: ✅済み（スタンドアロンスクリプトで4パターンを検証: ①`output_path`未指定時は従来通りの挙動を維持しコピーも発生しないこと、②`output_path`指定時は`.txt`と元画像コピーの両方が新フォルダに書き出され、複数回呼び出しても正しく次のファイルへ進むこと、③`overwrite=True`で`Name list`の順番通りに既存ファイルの中身を実際に上書きできること、④新しい`YoshiakiLoRACaptionSave`インスタンスを作るとカウンターが0にリセットされること。ComfyUI実機でのキュー実行を跨いだインスタンス再生成の確認はユーザー側で実施予定）
- **新規ファイル**: なし
- **修正ファイル**:
  - `modules/yoshiaki_loracaption/lora_caption.py` : `YoshiakiLoRACaptionSave`に`optional`入力`output_path`（STRING, 既定空文字）・`overwrite`（BOOLEAN, 既定False）を追加。`copy_source_image()`メソッドを新設し、`output_path`が`path`と異なる場合に元画像ファイルを`shutil.copy2`でそのままコピー（再エンコードなし）。`__init__`に`self._overwrite_index`カウンターを追加
  - `README.md` : `Yoshiaki LoRA Caption Load / Save`セクションに`output_path`/`overwrite`の説明を追加
  - `CLAUDE.md` : 該当ノードの備考を更新
- **変更内容**:
  - 従来`YoshiakiLoRACaptionSave`は「`.txt`が無い最初のファイル名」を毎回探して1件処理する仕組みで、画像ファイル自体はコピーしていなかった（`path`に`.txt`を書くのみ）
  - `output_path`を空欄のままにすれば完全に従来通りの挙動（画像コピー無し）。指定すると、そのフォルダへ`.txt`と元画像コピーの両方を書き出す設計にし、既存ワークフローへの互換性を確保した
  - `overwrite`のデフォルトはOFF（既存ファイルを残す、ユーザー確定事項）。ONの場合の.txt選択ロジックが技術的な検討事項になった: このノードは画像何枚分もの`text`をComfyUIの`map_node_over_list`機構（`text`がWD14Tagger等のリスト出力に接続されている場合、ComfyUIが画像枚数分Saveノードを自動的に繰り返し呼ぶ）で1件ずつ受け取り、「.txtが無い最初のファイル」という判定だけで「今回はどの画像か」を推測している。`overwrite=True`で単純に「存在を無視して書く」だけにすると毎回同じ1件目を上書きし続けてしまうため、ノードインスタンスの`self._overwrite_index`カウンターを使い、`Name list`の順番通りに1件ずつ進める方式にした
  - 画像コピー側にも同じ`overwrite`設定を適用（OFF:コピー先に同名ファイルがあればスキップ、ON:上書き）
- **備考**:
  - `self._overwrite_index`によるカウンター方式は、「ComfyUIはキュー実行ごとにノードインスタンスを新しく作り直す」という前提に依存している。この前提はComfyUIの一般的な実行モデルとして妥当だが、実機での複数回キュー実行（特に同一ワークフローを続けて何度も投入するケース）での動作確認を推奨
  - ユーザーの実際の利用目的: 同じ画像セットに対し複数のLLMモデルでキャプションを生成し比較する実験用途。「最悪上書きされて消えても問題ない」との実験目的での利用であることを確認済み

---

## タスク: Image-Captioning-in-ComfyUI(フォーク)を yoshiaki-comfy へ統合(YoshiakiLoRACaptionLoad / YoshiakiLoRACaptionSave)

- **完了日**: 2026-09-04
- **動作確認**: ✅済み（`modules/yoshiaki_loracaption/lora_caption.py`を単体importし、`comfy`をスタブ化した上で実際に2枚のPNG画像を生成→`YoshiakiLoRACaptionLoad`で読み込み→`YoshiakiLoRACaptionSave`でprefix付きキャプションを`.txt`保存するまでの一連の動作を確認。ComfyUI実機でのWD14 Tagger連携込みの確認はユーザー側で実施予定）
- **新規ファイル**:
  - `modules/yoshiaki_loracaption/lora_caption.py` : [Yoshiaki21/Image-Captioning-in-ComfyUI](https://github.com/Yoshiaki21/Image-Captioning-in-ComfyUI)（本家: [LarryJane491/Image-Captioning-in-ComfyUI](https://github.com/LarryJane491/Image-Captioning-in-ComfyUI)）の`LoRAcaption.py`を移植。クラス名を`LoRACaptionSave`/`LoRACaptionLoad`→`YoshiakiLoRACaptionSave`/`YoshiakiLoRACaptionLoad`に変更、`CATEGORY`を`LJRE/LORA`→`yoshiaki-comfy/LoRA`に変更、`NODE_CLASS_MAPPINGS`のキーをPascalCase形式に統一、`NODE_DISPLAY_NAME_MAPPINGS`を新規追加（元は空だった）
- **修正ファイル**:
  - `__init__.py` : `yoshiaki_loracaption.lora_caption`の`NODE_CLASS_MAPPINGS`/`NODE_DISPLAY_NAME_MAPPINGS`を他2パックとマージするよう変更
  - `README.md` : ノード一覧に追加、`Yoshiaki LoRA Caption Load / Save`セクション（使い方・ワークフロー図・既知の制約）を追加、ライセンス節に統合元を追記
  - `CLAUDE.md` : 「含まれるカスタムノード」セクションに追記
- **変更内容**:
  - フォーク元（本家からの差分3箇所: `cstr`未import対策、`prefix`空文字対策、`IS_CHANGED`未定義対策、いずれも機能追加ではなくバグ回避パッチ）をGitHub API経由で調査し、本家との差分をdiffで確認した上でそのまま移植
  - 依存関係を確認した結果、標準ライブラリ＋`PIL`/`numpy`（既存の`requirements.txt`でカバー済み）＋ComfyUI本体が提供する`torch`/`comfy`のみで完結しており、他のComfyUIカスタムノードパックへのコード依存はゼロと判断
  - JSファイル（独自フロントエンドUI）は無いため、今回の統合ではPython側のみの追加で完結（既存ワークフローへの互換性リスクなし）
- **備考**:
  - **既知の未修正バグをそのまま移植**: `YoshiakiLoRACaptionLoad.captionload()`は、画像がちょうど1枚のフォルダを渡すと戻り値の要素数が`RETURN_TYPES`(3種)と合わず壊れる（`return (images[0], 1)`のみ返す分岐）。また画像が0枚（PNGが1つも無い）場合は`image1`が未定義のまま参照され`UnboundLocalError`になる別の潜在バグも発見。どちらも本家・フォーク双方に存在する既存バグで、今回の統合では意図的に修正せずそのまま移植した（ユーザーの運用上、画像1枚・0枚のケースが無いため）。修正する場合は別タスクとして対応予定
  - フォーク元・本家ともにOSSライセンスの明記なし（`license: null`）。個人利用・非公開のためリスクは低いが留意事項として記録
  - 配布予定なし、個人利用限定

---

## タスク: LoRA選択にもフォルダ絞り込みを追加

- **完了日**: 2026-09-04
- **動作確認**: ⬜未確認（コード修正のみ。ユーザー側で再確認予定）
- **新規ファイル**: なし
- **修正ファイル**:
  - `js/yoshiaki-wildcard.js` : `YoshiakiWildcardEncode`の「Select to add LoRA」直上に「LoRA Folder」コンボを追加。ワイルドカード側の実装（`get_wildcard_folders`等）を汎用化（`folders_from_items`/`items_in_folder`/`default_folder`/`initial_folder`/`move_widget_above`）し、ワイルドカードとLoRAの両方で共通利用する形にリファクタリング
- **変更内容**:
  - LoRA一覧はワイルドカードと違い専用のサーバーAPIを新設せず、ノード生成時に既にPython側（`folder_paths.get_filename_list("loras")`）から渡されている`lora_widget.options.values`をJS側でそのままスナップショットして使用（サーバー変更なし）
  - フォルダ絞り込みの仕様（全階層フラット列挙・先頭に(no folder)・直下のみ絞り込み・中身のあるフォルダを自動初期選択・localStorageに`yoshiaki-lora-folder:`プレフィックスで記憶)はワイルドカードと同一
  - LoRAファイル名のパス区切り文字はWindows環境で`\`になる可能性があるため、`/`に正規化してから解析するようにした
- **備考**:
  - `Select to add LoRA`の直上に新規ウィジェットを挿入した結果、`YoshiakiWildcardEncode`内でそれより後ろにあるウィジェット（Wildcard Folder・Select to add Wildcard・seed）の配列位置がさらに1つずつ後ろにずれる。前回（Wildcard Folder追加時）に続き**2回目**の位置ずれとなるため、既存の保存済み`YoshiakiWildcardEncode`ワークフローを開いた際は`seed`の値を再度確認・入力し直す必要がある場合がある（ユーザー了承済み）
  - `YoshiakiWildcardProcessor`側はLoRA機能自体を持たないため影響なし

---

## タスク: 候補が多いときの検索一覧UIでワイルドカード/LoRA選択がテキストに挿入されない不具合を修正

- **完了日**: 2026-09-04
- **動作確認**: ⬜未確認（コード修正のみ。ユーザー側で再確認予定）
- **新規ファイル**: なし
- **修正ファイル**:
  - `js/yoshiaki-wildcard.js` : `wildcard_widget`/`lora_widget`の値反映処理を、別立ての`.callback`から`Object.defineProperty`の`value`セッター内に統合
- **変更内容**:
  - 候補が絞り込まれ「Select to add Wildcard」の候補は空でなくなったが、今度は候補を選んでも`wildcard_text`にテキストが追加されない不具合が発生（ユーザー報告、スクリーンショット添付あり）
  - 原因: 「Select to add Wildcard」の候補数が多いため、ComfyUIが検索ボックス付きの一覧UI（"Filter list"）でコンボを描画するようになっており、このUIは選択時に`widget.value`のみを更新し、`widget.callback`を呼び出さない実装だった。テキスト追加処理は`.callback`側にのみ実装していたため反映されなかった
  - `value`のセッター（両UIパターンで確実に呼ばれる）内でテキスト追加処理を直接行うように変更し、`.callback`には依存しない実装にした。同じ構造だった「Select to add LoRA」（`YoshiakiWildcardEncode`）も同様に修正
- **備考**: 候補数が少なかった開発初期の動作確認時は簡易な一覧UIが使われていたため`.callback`でも問題なく動いていたと考えられる。候補数が今後さらに増減しても、この修正後はどちらのUIパターンでも動作する

---

## タスク: フォルダ絞り込み追加後、ワイルドカード選択が効かなくなる不具合を修正

- **完了日**: 2026-09-03
- **動作確認**: ⬜未確認（コード修正のみ。ユーザー側で再確認予定）
- **新規ファイル**: なし
- **修正ファイル**:
  - `js/yoshiaki-wildcard.js` : 「Wildcard Folder」の初期選択を`NO_FOLDER_LABEL`固定から`get_default_folder()`（実際に中身があるフォルダを自動選択、無ければ`NO_FOLDER_LABEL`）に変更
- **変更内容**:
  - 直前のタスクで追加した「Wildcard Folder」フォルダ絞り込み機能で、初期選択を常に「(no folder)」にしていたため、ワイルドカードを全てサブフォルダに置いているユーザー環境では「Select to add Wildcard」の候補が最初から空になり、「選んでもテキストに追加されない」ように見える不具合が発生していた
  - 「(すべて表示)」は追加せず、代わりに「実際に選択肢があるフォルダ」を自動的に初期選択することで解決
- **備考**: `wildcard_widget`のクリック→テキスト追加のロジック自体にバグはなかった（候補が空だったことが原因）

---

## タスク: ワイルドカード選択コンボにフォルダ絞り込みを追加

- **完了日**: 2026-09-03
- **動作確認**: ⬜未確認（コード修正のみ。ComfyUI実機でのフォルダ選択・絞り込み・localStorage永続化の確認はユーザー側で実施予定）
- **新規ファイル**: なし
- **修正ファイル**:
  - `js/yoshiaki-wildcard.js` : 「Select to add Wildcard」直上に「Wildcard Folder」コンボを追加。フォルダ一覧は`wildcards_list`から全階層のフォルダパスをJS側でフラット抽出（サーバー側の変更は不要）。既存の「Select to add Wildcard」「Select to add LoRA」の参照も配列インデックスから`widget.name`によるlookupに変更
- **変更内容**:
  - ワイルドカードファイルが増えて「Select to add Wildcard」の選択肢が探しにくくなった問題に対応
  - 「Wildcard Folder」で選んだフォルダの**直下**にあるワイルドカードのみが「Select to add Wildcard」の候補になる（サブフォルダの中身は含まない。深い階層を見たい場合はその階層自体をフォルダ一覧から選ぶ）
  - フォルダ一覧の先頭は常に「(no folder)」（サブフォルダに属さないワイルドカードを絞り込む選択肢）で固定。「(すべて表示)」のような選択肢は無し（絞り込みが目的のため）
  - 選択したフォルダは`localStorage`にノードID単位で保存し、ページ再読み込み後も復元（ワークフローJSON自体には保存しない）
  - `YoshiakiWildcardProcessor` / `YoshiakiWildcardEncode` の両方に適用
- **備考**:
  - Python側（`INPUT_TYPES`、サーバールート）は一切変更していない。新しいウィジェットは`nodeCreated`時にJS側で動的追加し、ワークフロー保存データには意味を持たせていない（folderの実体はlocalStorage）
  - **`YoshiakiWildcardEncode`のみ既存の保存済みワークフローに影響の可能性あり**: 新ウィジェットを「Select to add LoRA」と「Select to add Wildcard」の間に挿入する都合上、それより後ろにある`seed`ウィジェットの配列位置が1つずれる。ComfyUIは`widgets_values`をウィジェット定義順（配列インデックス）で復元するため、本更新後に古い`YoshiakiWildcardEncode`ワークフローを開くと`seed`の値が意図しないものになっている可能性がある（実行が壊れるわけではなく、`seed`欄を目視確認・再入力すれば解消）。`YoshiakiWildcardProcessor`は`seed`が新ウィジェットより前に位置するため影響なし

---

## タスク: YoshiakiLLMCaptionGenerator の CATEGORY を yoshiaki-comfy 配下に統一

- **完了日**: 2026-09-03
- **動作確認**: ⬜未確認（文字列変更のみ。ComfyUI実機でのカテゴリ表示確認は未実施）
- **新規ファイル**: なし
- **修正ファイル**:
  - `modules/yoshiaki_llm/llm_caption_node.py` : `CATEGORY`を`"LLM"`→`"yoshiaki-comfy/LLM"`に変更
  - `CLAUDE.md` : 上記変更に合わせて記載を修正
- **変更内容**:
  - `YoshiakiWildcardProcessor`/`YoshiakiWildcardEncode`の`CATEGORY`（`yoshiaki-comfy/Prompt`）と揃え、ノード一覧で`yoshiaki-comfy`配下にまとまって表示されるようにした
- **備考**: なし

---

## タスク: ComfyUI-LLM-Tagger を yoshiaki-comfy へ統合（YoshiakiLLMCaptionGenerator）

- **完了日**: 2026-09-03
- **動作確認**: ✅済み（`modules/yoshiaki_llm/llm_caption_node.py`を単体importし、`INPUT_TYPES()`実行時にWD14タグ用のsystem_promptsファイル一覧が正しく読めること、および実際にLemonade Server（LAN上）へ接続してモデル一覧を取得できることを確認。ComfyUI実機での画像入力込みの動作確認は未実施）
- **新規ファイル**:
  - `modules/yoshiaki_llm/llm_caption_node.py` : 元`ComfyUI-LLM-Tagger`の`llm_caption_node.py`を移植。クラス名を`LLMCaptionGenerator`→`YoshiakiLLMCaptionGenerator`に変更（ログ出力中の全プレフィックス文字列も含め置換）、`CATEGORY`を`Image-Captioning-in`→`LLM`に変更、末尾に`NODE_CLASS_MAPPINGS`/`NODE_DISPLAY_NAME_MAPPINGS`を追加
  - `modules/yoshiaki_llm/system_prompts/caption_tags_only.txt` : 元リポジトリからそのまま移植
  - `modules/yoshiaki_llm/system_prompts/caption_text_only.txt` : 元リポジトリからそのまま移植
  - `docs/yoshiaki/tasks_done.LLM.md` : 元`ComfyUI-LLM-Tagger`の`docs/yoshiaki/tasks_done.md`をそのまま保存（本体のtasks_done.mdには統合せず、別ファイルとして参照用）
  - `docs/yoshiaki/LLM_Caption_Node_指示書.md` : 元リポジトリの詳細仕様書をそのまま保存
- **修正ファイル**:
  - `__init__.py` : `yoshiaki_wildcard.nodes`と`yoshiaki_llm.llm_caption_node`の両方の`NODE_CLASS_MAPPINGS`/`NODE_DISPLAY_NAME_MAPPINGS`をマージして公開するよう変更
  - `requirements.txt` : `Pillow`を追加（`llm_caption_node.py`が画像処理に使用。numpy/pyyamlは既存）
  - `.gitignore` : `modules/yoshiaki_llm/logs/`（実行時ログ出力先）を追加
  - `README.md` : ノード一覧に追加、`Yoshiaki-LLMCaptionGenerator`セクション（入出力・仕組み・前提条件）を追加、インストール節の依存パッケージ表記を更新、ライセンス節に統合元リポジトリを追記
  - `CLAUDE.md` : 「含まれるカスタムノード」セクションに追記
- **変更内容**:
  - [github.com/Yoshiaki21/ComfyUI-LLM-Tagger](https://github.com/Yoshiaki21/ComfyUI-LLM-Tagger)（画像+WD14タグをローカルLLM「Lemonade Server」に渡してタグ補正・キャプション生成するノード、単一ファイル1254行）をGitHub API経由で取得・調査
  - 依存関係を確認した結果、標準ライブラリ＋numpy＋Pillowのみで完結しており、他のComfyUIカスタムノードパックへのコード依存はゼロ（README記載の「WD14 Taggerと組み合わせて使う」はワークフロー上の運用であり、コード上のimport依存ではないことを確認）と判断し、そのまま`modules/yoshiaki_llm/`として統合
- **備考**:
  - デフォルトの接続先（Lemonade Server）はローカルLAN内の固定IPが設定されているため、別環境で使う場合は`lemonade_host`/`lemonade_port`ウィジェットの変更が必要
  - 元リポジトリ`ComfyUI-LLM-Tagger`は統合後アーカイブ予定（削除ではなく読み取り専用化。ユーザー判断待ち）
  - 配布予定なし、個人利用限定

---

## タスク: README.md 作成

- **完了日**: 2026-09-02
- **動作確認**: ✅済み（記載したワイルドカード構文例をスタブ環境で実際に`process()`に通し、説明と実挙動が一致することを確認）
- **新規ファイル**:
  - `README.md` : GitHubリポジトリ表示用。含まれるノード一覧、`YoshiakiWildcardProcessor`/`YoshiakiWildcardEncode`の入出力・LoRA構文・`mode`挙動・ワイルドカード構文リファレンス・設定ファイルの使い方・インストール手順を記載
- **修正ファイル**: なし
- **変更内容**:
  - ワイルドカード構文（`__name__`, `__name#N__`固定行, `{a|b}`, 重み付け`{2::a|1::b}`, 複数選択`{2$$a|b|c}`/範囲/区切り文字指定, 繰り返し`N#__name__`, YAMLネストキー）をそれぞれ実際に解決させて検証しながら記載
- **備考**:
  - 検証の過程で、繰り返し構文`N#__name__`は**単体で書いた場合**は3回分の独立抽選結果を`|`で連結したテキストになり（「1つに絞られる」わけではない）、**`{}`で囲んだ場合**（`{N#__name__}`）にのみその中から1つを選ぶ挙動になることが判明。README初稿の説明が誤っていたため修正した

---

## タスク: yoshiaki-wildcard.ini のひな型ファイル追加

- **完了日**: 2026-09-02
- **動作確認**: ✅済み（`configparser`で`.example`ファイルが問題なくパースできることを確認）
- **新規ファイル**:
  - `yoshiaki-wildcard.ini.example` : `yoshiaki-wildcard.ini`のひな型。`custom_wildcards`キーの書き方をコメントで説明
- **修正ファイル**: なし
- **変更内容**:
  - `yoshiaki-wildcard.ini`は`.gitignore`対象かつ未作成時はデフォルト値で動くため、設定ファイルの書き方が分かるようにexampleファイルを追加
  - 使い方: `yoshiaki-wildcard.ini.example`を`yoshiaki-wildcard.ini`にコピーして`custom_wildcards`にパスを記入
- **備考**: なし

---

## タスク: YoshiakiWildcardProcessor / YoshiakiWildcardEncode ノードパックの新規作成

- **完了日**: 2026-09-02
- **動作確認**: ⬜未確認（コード生成のみ。実機ComfyUIでの動作確認はユーザー側で実施予定）
- **新規ファイル**:
  - `__init__.py` : ComfyUIエントリポイント（NODE_CLASS_MAPPINGS登録、EXTENSION_WEB_DIRS登録）
  - `requirements.txt` : pyyaml, numpy
  - `modules/yoshiaki_wildcard/config.py` : `yoshiaki-wildcard.ini`の`custom_wildcards`設定読み込み
  - `modules/yoshiaki_wildcard/wildcards.py` : ワイルドカード解決本体ロジック（`process`, `process_with_loras`等）
  - `modules/yoshiaki_wildcard/nodes.py` : `YoshiakiWildcardProcessor`/`YoshiakiWildcardEncode`ノード定義
  - `modules/yoshiaki_wildcard/server.py` : `/yoshiaki/wildcards/list`・`/yoshiaki/wildcards/refresh`ルートと、`populate`モードの実行前自動生成onpromptフック
  - `js/yoshiaki-wildcard.js` : ワイルドカード/LoRA選択コンボボックス、mode切り替えのフロントエンド挙動
  - `wildcards/example.txt` : 動作確認用のサンプルワイルドカードファイル
- **修正ファイル**:
  - `.gitignore` : `/yoshiaki-wildcard.ini`（環境依存のカスタムパス設定）を追加
  - `CLAUDE.md` : 「含まれるカスタムノード」セクションに本ノードの説明を追記
- **変更内容**:
  - ComfyUI-Impact-Pack ([D:\GitHub_data\ComfyUI-Impact-Pack](../../../ComfyUI-Impact-Pack)) の`ImpactWildcardProcessor`/`ImpactWildcardEncode`を調査し、実際に必要なロジック（`impact/wildcards.py`のワイルドカード展開・LoRA適用部分のみ）を特定
  - segment-anything/sam2/piexif/opencv/scikit-image等、他ノード群のためだけの重い依存を排除し、pip依存を`pyyaml`と`numpy`のみに削減
  - ノード名衝突を避けるため`class_type`を`YoshiakiWildcardProcessor`/`YoshiakiWildcardEncode`に変更、Pythonパッケージ名も`yoshiaki_wildcard`（元は`impact`）に変更、サーバールートも`/yoshiaki/wildcards/*`（元は`/impact/wildcards/*`）に変更し、元のImpact-Packと同一ComfyUI環境に共存インストール可能な設計にした
  - ユーザーとの相談の結果、以下の仕様で実装：
    - ワイルドカードのキャッシュ機構は撤廃し、常にディスクから再読込（no-cache固定、設定項目なし）
    - `populate`モードの実行前自動生成（サーバーフック＋JS連携）は元と同じ使い勝手で移植
    - LoRA構文（`<lora:...>`）は維持するが、Inspire Pack LBW連携・nunchaku専用ローダー連携は未実装（不要のため意図的に省略）
    - ワイルドカードファイルの場所は`custom_wildcards`設定（`yoshiaki-wildcard.ini`）で切り替え可能な仕組みを踏襲。デフォルトはパック内`wildcards/`フォルダの空状態とし、既存Impact-Packのwildcardsフォルダとは独立させた
- **備考**:
  - GPLv3ライセンスのComfyUI-Impact-Packからの派生コードを含むが、配布予定はなく個人利用限定
  - 実機でのComfyUI起動・ワイルドカード解決・LoRA適用・populateモードのUI動作は未検証。custom_nodesフォルダへの配置（シンボリックリンク等）を含め、動作確認はユーザー側で実施予定

---
