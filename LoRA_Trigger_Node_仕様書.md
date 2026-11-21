# Yoshiaki Wildcard トリガーワード自動挿入 仕様書

## 1. 目的

diffusion-pipeコンテナの `lora-finalize` がsafetensorsに書き込んだトリガーワードを、Yoshiaki Wildcard Encode の「LoRA Add」で `<lora:...>` を挿入するときに、一緒に `wildcard_text` へ自動で挿入する。
あわせて「LoRA Info」でトリガーワードを確認できるようにする。

- 対象リポジトリ: `github.com/Yoshiaki21/yoshiaki-comfy`
- 実装: Claude Code
- 新しいノードは作らず、既存の `yoshiaki_lora_info` と `yoshiaki-lora-info.js` を拡張する

## 2. 現状（実装前の確認事項）

| ファイル | 現在の動作 |
|---|---|
| `modules/yoshiaki_lora_info/lora_info.py` | `read_safetensors_metadata()` がヘッダーの `__metadata__` を読む（JSONとして読める値はデコードする）。`ss_tag_frequency` とCivitaiの `trainedWords` を合わせて `info["trainedWords"]` を作る。sha256をキーにしてキャッシュする。API: `/yoshiaki/lora_info`, `/yoshiaki/lora_info/refresh` |
| `js/yoshiaki-lora-info.js` | 「LoRA Info」ボタンでダイアログを表示（trained wordsのコピーなど）。「LoRA Add」ボタンで、`insert_at_cursor(wildcard_text_widget, "<lora:${lora_name}>")` を実行する |
| `modules/yoshiaki_wildcard/wildcards.py` | 実行時に `<lora:...>` を取り出してLoRAを適用し、タグはプロンプトから取り除く |

## 3. バックエンド（lora_info.py）

### 3.1 `info["triggerWords"]` を追加する

`_build_info()` で次の順に探し、最初に見つかったものを `triggerWords`（文字列の配列）にする。

| 順位 | 取得元 | 処理 |
|---|---|---|
| 1 | `metadata["modelspec.trigger_phrase"]` | カンマで分割し、前後の空白を除く |
| 2 | `metadata["ss_tag_frequency"]["trigger_words"]` | lora-finalizeが書いたバケット。キーをすべて使う |
| 3 | Civitaiの `trainedWords`（キャッシュにある場合のみ） | Civitaiで公開されているLoRA用 |
| — | どれも無い | 空の配列 |

- 重複は除き、最初に出た順を保つ
- kohyaの `ss_tag_frequency`（学習タグがすべて入っているもの）はトリガーワードとして扱わない。これまでどおり `trainedWords` にだけ入れる
- `info["triggerSource"]` に取得元（`"modelspec"` / `"ss_tag_frequency"` / `"civitai"` / `null`）を入れる

### 3.2 表示用の学習情報

`info["training"]` に、`ss_output_name` / `ss_steps` / `ss_network_dim` / `ss_network_alpha` / `ss_learning_rate` のうち存在するものを入れる。

### 3.3 キャッシュ

- 今のsha256キーのキャッシュをそのまま使う。lora-finalizeでメタデータを書き直すとファイルのハッシュも変わるため、自動で別のキャッシュになる
- 既存のキャッシュに `triggerWords` が無くても、`_build_info()` で毎回メタデータから組み立てるため、移行の処理は不要

## 4. フロントエンド（yoshiaki-lora-info.js）

### 4.1 「LoRA Add」の動作変更

1. これまでどおり、カーソル位置に `<lora:${lora_name}>` を挿入する
2. 続けて `/yoshiaki/lora_info?file=...` を呼び、`triggerWords` があれば、`<lora:...>` の直後に `insert_at_cursor(widget, words.join(", "), ", ")` で挿入する
   - 結果の例: `<lora:Einhart_step1500_RANK16-lr3e-5>, Einhart`
3. `wildcard_text` にすでに含まれているトリガーワードは挿入しない
   - `,` と改行で区切った単語ごとに比較し、大文字・小文字は区別しない
   - `__wildcard__` や `{a|b}` の中の文字列は考慮しない（単純に比較する）
4. APIの呼び出しに失敗した場合や、`triggerWords` が空の場合は、`<lora:...>` だけを挿入して終わる（エラーのダイアログは出さない。コンソールに警告を出す）
5. 処理の順番: LoRAタグの挿入をAPIの応答で遅らせないように、先にタグを挿入し、応答が届いてからトリガーワードを挿入する。応答を待っている間にカーソルが動いた場合は、`<lora:...>` タグの直後に挿入する（タグの位置を探して、その後ろに入れる）

### 4.2 自動挿入のオン/オフ

- ノードにトグルのウィジェット「Add trigger words」（初期値オン）を追加する。置く場所は「LoRA Add」ボタンの直前
- ワークフローに保存される値にする（serializeする）
- Python側の `INPUT_TYPES` には追加しない（JSだけのウィジェット）。既存のLoRA picker/folderのウィジェットと同じ扱いにし、実行には影響させない

### 4.3 「LoRA Info」ダイアログ

- trained wordsの上に「Trigger words」の欄を追加する
  - トリガーワードを表示し、「Copy」と「Insert」（カーソル位置に挿入）のボタンを付ける
  - 取得元（modelspec / ss_tag_frequency / civitai）を小さく表示する
  - 無い場合は「(no trigger words)」と表示する
- `training` の情報（steps / rank / alpha / lr）を1行で表示する

## 5. 実行時の処理（wildcards.py）

変更しない。トリガーワードは編集するときに `wildcard_text` へ目に見える形で挿入されるので、`populated_text` や再現（reproduce）モードとの整合性もそのまま保てる。

## 6. 運用上の注意

- lora-finalizeはファイル名を変更するため、変更前の名前で `<lora:adapter_model>` などと書かれた古いワークフローは、LoRAが見つからなくなる（`LORA NOT FOUND` の警告が出る）。新しく保存したLoRAには新しい名前を使う
- diffusion-pipeの出力は、どのフォルダのファイルも `adapter_model.safetensors` という同じ名前だったため、名前を変えずにComfyUIへコピーすると見分けがつかなかった。名前を変えてからコピーすれば、この問題もなくなる

## 7. テスト項目

1. lora-finalizeで処理したLoRAで「LoRA Add」→ `<lora:Einhart_step1500_RANK16-lr3e-5>, Einhart` が挿入される
2. すでに `Einhart` が書かれた状態で「LoRA Add」→ `<lora:...>` だけが挿入される
3. トリガーワードが複数（`Einhart_aged_up, Einhart_child`）→ 両方が挿入される
4. メタデータが `{'format': 'pt'}` だけのLoRA → `<lora:...>` だけが挿入され、エラーにならない
5. kohyaで学習したLoRA（`ss_tag_frequency` のみ）→ トリガーワードは挿入されず、Info画面のtrained wordsには今までどおり表示される
6. Civitaiの情報を取得済みのLoRA → Civitaiの `trainedWords` が挿入される
7. 「Add trigger words」をオフにする → `<lora:...>` だけが挿入される。ワークフローを保存して読み込み直しても、オフのまま
8. lora-finalizeでトリガーワードを書き直した後 → 新しい値が挿入される（ハッシュが変わるため）
9. 「LoRA Info」でTrigger wordsの欄が表示され、Copy/Insertが動く
