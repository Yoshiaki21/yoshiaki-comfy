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
