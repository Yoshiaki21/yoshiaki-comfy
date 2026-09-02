# yoshiaki-comfy

個人利用のためのComfyUIカスタムノード集です。配布は行っていません。

## 含まれるノード

| ノード | 概要 |
|---|---|
| **Yoshiaki Wildcard Processor** (`YoshiakiWildcardProcessor`) | ワイルドカード構文のテキストを解決して文字列を出力する |
| **Yoshiaki Wildcard Encode** (`YoshiakiWildcardEncode`) | ワイルドカード構文とLoRA構文を解決し、LoRA適用済みの `MODEL`/`CLIP` とCLIP条件付け(`CONDITIONING`)を出力する |

[ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) の `ImpactWildcardProcessor` / `ImpactWildcardEncode` を、この2ノードだけ使う用途に切り出して単独パック化したものです（詳細は [docs/yoshiaki/tasks_done.md](docs/yoshiaki/tasks_done.md) 参照）。ノード名・Pythonパッケージ名・サーバールート名を独自のものに変更しているため、元のComfyUI-Impact-Packと同一環境に共存インストールしても衝突しません。

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

---

## インストール

このリポジトリをComfyUIの `custom_nodes` フォルダ内にクローン（またはシンボリックリンク）し、以下を実行してください。

```bash
pip install -r requirements.txt
```

依存パッケージは `pyyaml` と `numpy` のみです。

---

## ライセンス

[ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack)（GPLv3）からのコードを含みます。個人利用のみで配布予定はありません。
