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
- **備考**:
  - `class_type`は`YoshiakiLLMCaptionGenerator`、表示名は`Yoshiaki-LLMCaptionGenerator`、`CATEGORY`は`yoshiaki-comfy/LLM`
  - 他のComfyUIカスタムノードパックへのコード依存なし（`tags`入力はワークフロー上でWD14Tagger等を繋ぐ運用であり、コード上のimport依存ではない）
  - 統合元リポジトリの開発履歴は[docs/yoshiaki/tasks_done.LLM.md](docs/yoshiaki/tasks_done.LLM.md)、詳細仕様書は[docs/yoshiaki/LLM_Caption_Node_指示書.md](docs/yoshiaki/LLM_Caption_Node_指示書.md)として本リポジトリに保存（本体の`docs/yoshiaki/tasks_done.md`には統合せず、別ファイルとして参照用に保管）
  - 配布予定なし、個人利用限定

---

### YoshiakiLoRACaptionLoad / YoshiakiLoRACaptionSave

- **実装日**: 2026-09-04（自分のフォーク[Image-Captioning-in-ComfyUI](https://github.com/Yoshiaki21/Image-Captioning-in-ComfyUI)からyoshiaki-comfyへ統合。本家は[LarryJane491/Image-Captioning-in-ComfyUI](https://github.com/LarryJane491/Image-Captioning-in-ComfyUI)）
- **カスタムノードの機能の概要**:
  - `YoshiakiLoRACaptionLoad`: 指定フォルダ内のPNG画像を読み込み、画像バッチ・ファイル名一覧・pathを出力
  - `YoshiakiLoRACaptionSave`: ファイル名一覧・path・キャプション文字列を受け取り、画像と同名の`.txt`をプレフィックス付きで保存（LoRA学習用データセット準備）
  - WD14 Taggerと組み合わせて使う想定（コード上の依存ではなくワークフロー上の連携）
  - `YoshiakiLoRACaptionSave`に`output_path`（保存先を`path`と分けて指定、指定時は元画像もコピーする）と`overwrite`（既存ファイルを無視して`Name list`順に上書きする）を追加（2026-09-04）
- **備考**:
  - `class_type`/表示名は`YoshiakiLoRACaptionLoad`/`YoshiakiLoRACaptionSave`(表示名は`Yoshiaki LoRA Caption Load`/`Yoshiaki LoRA Caption Save`)、`CATEGORY`は`yoshiaki-comfy/LoRA`
  - フォーク元の3つの既存パッチ（`cstr`未import対策、prefix空文字対策、`IS_CHANGED`未定義対策）をそのまま維持して移植
  - **既知の未修正バグ**: `YoshiakiLoRACaptionLoad`は画像がちょうど1枚のフォルダを渡すと戻り値の数が`RETURN_TYPES`と合わず壊れる（本家・フォーク由来の既存バグ）。実用上1枚だけを指定するケースが無いため、今回は修正せずそのまま移植。修正は別タスクとして保留
  - PNGのみ対応、同名`.txt`が既存のフォルダに対して実行するとエラーになる制約は本家のまま
  - 配布予定なし、個人利用限定

---

