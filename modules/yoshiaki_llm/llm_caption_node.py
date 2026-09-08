import base64
import io
import os
import re
import time
import uuid

import numpy as np
from PIL import Image

from .llm_common import (
    CAPTION_OUTPUT_MODES, CLAMP_LOG_NOTE, DEFAULT_LEMONADE_HOST, DEFAULT_LEMONADE_PORT,
    DEFAULT_MAX_RETRIES, ERROR_LOG_FILENAME, FALLBACK_MODEL_LABEL, FALLBACK_SYSTEM_PROMPT_LABEL,
    FIXED_TOP_P, INVALID_PROMPT_FILE_REASON, MAX_MAX_RETRIES, MIN_MAX_RETRIES,
    MIN_VALID_RESPONSE_CHARS, REASON_INVALID_PROMPT_FILE, REASON_PARSE_FORMAT, REASON_TIMEOUT,
    RETRYABLE_EXCEPTIONS, SYSTEM_PROMPTS_DIR, CaptionParseError,
    build_chat_payload, cancel_request, classify_error, classify_parse_failure,
    describe_params_source, estimate_prompt_tokens, extract_response_text, fetch_lemonade_models,
    first_value, format_duration, format_response_for_log, format_response_timing,
    get_model_context_window, list_system_prompt_files, next_attempt_params,
    parse_system_prompt_file, request_chat_completion, resolve_max_retries, strip_thinking,
    write_log, write_prompt_log,
)

# 5.1 画像前処理：長辺がこの値を超える場合のみリサイズする（以下ならそのまま送信）
MAX_IMAGE_LONG_EDGE = 1024
IMAGE_FORMAT = "PNG"
IMAGE_MIME_TYPE = "image/png"

# PART1 / PART2 の区切り行（"---" のみの行。ハイフン3個以上を許容）
PART_SEPARATOR_PATTERN = re.compile(r"^[ \t]*-{3,}[ \t]*$", re.MULTILINE)
# 6.1 結合フォーマットの区切り文字
TAG_DELIMITER = ", "
TAGS_CAPTION_DELIMITER = ". "

# 自然文に literal な "@" + trigger_word が混入したときに取り除くための保険。
# システムプロンプトの例示（旧: "@charactername stands in..."）を字義通りに解釈した
# モデルが "@she" のような文字列を出力する事例が実運用ログで確認されたため。
# プロンプト側の例示は修正済みだが、再発しうるためノード側でも後処理する。
# "@" の直後が trigger_word で、かつその後ろに英数字・アンダースコアが続かない場合のみ対象。
# 大文字小文字は無視し、置換時はモデルが出した表記（文頭の大文字など）を保つ。
LITERAL_AT_TRIGGER_NOTE = "stripped_literal_at_trigger_word"

# 6.1.2 応答に混入するシステムプロンプトの節見出しの除去。
# both モードのプロンプトが節見出しに使っている
# "PART 1 — CORRECTED TAGS (Danbooru-style):" / "PART 2 — NATURAL LANGUAGE:" を
# モデルがそのまま複写して出力する事例が実運用ログで確認された（237応答中46件＝約19%）。
# 見出し行はタグ列の先頭・自然文の先頭に紛れ込み、学習用キャプションを直接壊す。
# プロンプト側でも「見出しは出力しない」と明示したが、再発しうるためノード側でも後処理する
# （6.1.1 の "@" + trigger_word 除去と同じ方針）。
# 誤爆防止のため「行頭が PART + 1桁 で始まり、その行が ":" で終わる」行だけを見出しとみなす
# （markdown の "**" / "#" 装飾は許容する）。自然文の途中に出る "part 1" は対象外。
PART_HEADER_PATTERN = re.compile(
    r"^[ \t]*[#*]{0,4}[ \t]*PART[ \t]*([12])\b[^\n]*:[ \t]*[*]{0,2}[ \t]*$",
    re.MULTILINE | re.IGNORECASE)
PART_HEADER_NOTE = "stripped_part_header"

# 7.3 ログの出力先。指示書は「入力画像と同じフォルダ」だが、ComfyUI の IMAGE 型には
# パス情報が含まれないため、ノードディレクトリ直下の logs/ に固定する（運用上の決定）。
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# 5.2 parse_format で失敗した直後のリトライにだけ user message 末尾へ追記する訂正指示。
# temperature の上げ下げはランダムな揺さぶりでしかなく、同じ崩れ方が3回とも再現する事例が
# 実運用ログで確認されたため、何が足りなかったかを具体的にモデルへ伝える。
FORMAT_CORRECTION_NOTE = (
    'Note: Your previous response did not follow the required output format. Output PART 1 '
    '(the corrected tag list) first, then a line containing only "---", then PART 2 (the natural '
    'language sentences). Do not swap the order of the two parts, and do not output the section '
    'headings themselves (no "PART 1 ...:" or "PART 2 ...:" line) — output only the tags, the '
    '"---" line, and the sentences.'
)
FORMAT_CORRECTION_LOG_NOTE = "note=added_format_correction"


def iter_images(image):
    # ComfyUI の IMAGE は通常 [B, H, W, C] のバッチテンソルで渡ってくるが、
    # 上流ノードが OUTPUT_IS_LIST の場合はテンソルのリストで渡ってくることもある。
    # どちらでも「1枚 = [H, W, C]」の単位に平坦化して yield する。
    if isinstance(image, (list, tuple)):
        for item in image:
            yield from iter_images(item)
        return

    if getattr(image, "ndim", None) == 4:
        for i in range(image.shape[0]):
            yield image[i]
    else:
        yield image


def tensor_to_pil(image_tensor):
    # ComfyUI の IMAGE は float32 0.0〜1.0、形状 [H, W, C]
    array = image_tensor.cpu().numpy() if hasattr(image_tensor, "cpu") else np.asarray(image_tensor)
    array = np.clip(array * 255.0, 0, 255).astype(np.uint8)

    if array.ndim == 2:
        return Image.fromarray(array, mode="L").convert("RGB")
    if array.shape[2] == 1:
        return Image.fromarray(array[:, :, 0], mode="L").convert("RGB")
    # RGBA で来た場合はアルファを捨てて RGB に揃える
    return Image.fromarray(array[:, :, :3], mode="RGB")


def resize_if_needed(pil_image, max_long_edge=MAX_IMAGE_LONG_EDGE):
    # 5.1 長辺が max_long_edge を超える場合のみアスペクト比維持でリサイズ
    width, height = pil_image.size
    long_edge = max(width, height)
    if long_edge <= max_long_edge:
        return pil_image

    scale = max_long_edge / long_edge
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return pil_image.resize(new_size, Image.LANCZOS)


def encode_image_base64(pil_image):
    buffer = io.BytesIO()
    pil_image.save(buffer, format=IMAGE_FORMAT)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def build_user_text(tags, trigger_word, format_correction=False, reference_tags=""):
    # 5.2 トリガーワードの有無で2パターン。
    # format_correction=True のときのみ、末尾に訂正指示を追記する（構成順序は変更しない）。
    # reference_tags が非空のときだけ「基準タグ列」ブロックを先頭に追加する
    # （衣装LoRA用システムプロンプト向け。空なら従来と完全に同じ文面＝後方互換）。
    tags_block = f"Candidate tags from WD14 (verify against the image, correct as needed):\n{tags}"
    reference_tags = (reference_tags or "").strip()
    if reference_tags:
        reference_block = (
            "Reference tags used to create the fixed element the trigger word represents "
            "(match by physical item, not exact string; use as exclusion guidance):\n"
            f"{reference_tags}"
        )
        tags_block = f"{reference_block}\n{tags_block}"

    trigger_word = (trigger_word or "").strip()
    if trigger_word:
        user_text = f"Trigger word: {trigger_word}\n{tags_block}"
    else:
        user_text = tags_block

    if format_correction:
        user_text = f"{user_text}\n{FORMAT_CORRECTION_NOTE}"
    return user_text


def build_messages(system_prompt_text, tags, trigger_word, image_base64, format_correction=False,
                    reference_tags=""):
    # 5.2 テキスト部と画像部は同一 user message 内のパートとして含める
    return [
        {"role": "system", "content": system_prompt_text},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": build_user_text(tags, trigger_word, format_correction,
                                                          reference_tags)},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{IMAGE_MIME_TYPE};base64,{image_base64}"},
                },
            ],
        },
    ]


def split_both_parts(text):
    # 6章 both モード：最初の "---" 行で PART1（タグ）/ PART2（自然文）に分割
    # 戻り値は (tags_part, caption_part, 見出しを除去したか)
    parts = PART_SEPARATOR_PATTERN.split(text, maxsplit=1)
    if len(parts) < 2:
        raise CaptionParseError("'---' 区切りが見つかりません")

    tags_part, caption_part = parts[0].strip(), parts[1].strip()

    # 6.1.2 見出しが複写されている場合、その「位置」から PART1/PART2 の順序崩れを検出できる。
    # 正しい順序なら PART 1 の見出しは区切りより前、PART 2 の見出しは区切りより後にしか出ない。
    # 順序が入れ替わった応答（自然文→区切り→タグ、実運用ログで1件確認）は見出しを落としても
    # 中身が入れ替わったままなので、除去せず parse_format として 7.1 のリトライに回す。
    if "1" in find_part_header_numbers(caption_part):
        raise CaptionParseError("'---' より後ろに PART 1 の見出しがあります（PART1/PART2の順序崩れ）")
    if "2" in find_part_header_numbers(tags_part):
        raise CaptionParseError("'---' より前に PART 2 の見出しがあります（PART1/PART2の順序崩れ）")

    # 順序が正しければ見出しだけを落として採用する（リトライを消費しない）
    tags_part, tags_stripped = strip_part_headers(tags_part)
    caption_part, caption_stripped = strip_part_headers(caption_part)

    if not tags_part:
        raise CaptionParseError("'---' より前（PART1: タグ）が空です")
    if not caption_part:
        raise CaptionParseError("'---' より後（PART2: 自然文）が空です")
    return tags_part, caption_part, tags_stripped or caption_stripped


def normalize_tag_list(tags_part, trigger_word):
    # 6.1 タグ区切りを ", " に正規化する。末尾のピリオドは自然文との区切りと重複するため落とす。
    tags = [tag.strip() for tag in tags_part.rstrip().rstrip(".").split(",")]
    tags = [tag for tag in tags if tag]

    # トリガーワードはプログラム側で先頭に挿入するため、
    # LLMが出力に含めてしまっていた場合は重複を避けて除去する
    trigger_word = (trigger_word or "").strip()
    if trigger_word:
        tags = [tag for tag in tags if tag.lower() != trigger_word.lower()]
    return tags


def find_part_header_numbers(text):
    # 6.1.2 テキスト中に現れた見出しの番号（"1" / "2"）の集合を返す。
    # 見出しの「位置」は PART1/PART2 の順序崩れの検出にも使う（split_both_parts）。
    return {match.group(1) for match in PART_HEADER_PATTERN.finditer(text or "")}


def strip_part_headers(text):
    """6.1.2 プロンプトの節見出し行（"PART 1 — ...:" / "PART 2 — ...:"）を落とす。

    戻り値は (text, 除去したか)。
    """
    if not text:
        return text, False
    stripped, count = PART_HEADER_PATTERN.subn("", text)
    if not count:
        return text, False
    return stripped.strip(), True


def strip_literal_at_trigger_word(text, trigger_word):
    """自然文中の literal な "@" + trigger_word から "@" を取り除く。

    戻り値は (text, 置換したか)。trigger_word が空の場合は何もしない。
    """
    trigger_word = (trigger_word or "").strip()
    if not trigger_word or not text:
        return text, False

    pattern = re.compile(r"@(" + re.escape(trigger_word) + r")(?![0-9A-Za-z_])", re.IGNORECASE)
    replaced, count = pattern.subn(r"\1", text)
    return replaced, count > 0


def combine_both_output(tags_part, caption_part, trigger_word):
    # 6.1 学習用結合フォーマット: {trigger_word}, {corrected_tags}. {natural_language_caption}
    # 戻り値は (結合結果, "@"付きtrigger_wordを除去したか)
    # 自然文を最終文字列へ組み込む「直前」に後処理する（タグ列側には影響させない）
    caption_part, stripped = strip_literal_at_trigger_word(caption_part, trigger_word)
    tags = normalize_tag_list(tags_part, trigger_word)

    trigger_word = (trigger_word or "").strip()
    if trigger_word:
        # トリガーワードは常にタグ列の先頭へ確実に挿入（LLM出力に依存しない）
        tags.insert(0, trigger_word)

    tag_line = TAG_DELIMITER.join(tags)
    if not tag_line:
        raise CaptionParseError("PART1 から有効なタグを抽出できませんでした")
    return f"{tag_line}{TAGS_CAPTION_DELIMITER}{caption_part}", stripped


def parse_response(raw_response, output_mode, trigger_word, failure_category=REASON_PARSE_FORMAT):
    # 6章 パース本体。失敗時は CaptionParseError を送出する（7.1 のリトライ対象）。
    # failure_category には 6.3 の分類を渡し、送出する例外に付与する。
    # 戻り値は (caption_text, notes)。notes は log.log に NOTE 行として残す注記のリスト
    # （6.1.1 の stripped_literal_at_trigger_word / 6.1.2 の stripped_part_header）。
    try:
        return _parse_response_body(raw_response, output_mode, trigger_word)
    except CaptionParseError as e:
        e.category = failure_category
        raise


def _parse_response_body(raw_response, output_mode, trigger_word):
    body = strip_thinking(raw_response).strip()
    if len(body) < MIN_VALID_RESPONSE_CHARS:
        raise CaptionParseError(f"応答が短すぎます ({len(body)}文字): {body!r}")

    notes = []
    if output_mode == "both":
        tags_part, caption_part, header_stripped = split_both_parts(body)
        if header_stripped:
            notes.append(PART_HEADER_NOTE)
        caption, at_stripped = combine_both_output(tags_part, caption_part, trigger_word)
        if at_stripped:
            notes.append(LITERAL_AT_TRIGGER_NOTE)
        return caption, notes

    # 6.1.2 tags_only / caption_only のプロンプトは PART 見出しを使わないが、
    # 見出しが混入したときにキャプションを壊すのは同じなので保険として同じ後処理を通す。
    body, header_stripped = strip_part_headers(body)
    if header_stripped:
        notes.append(PART_HEADER_NOTE)
        if len(body) < MIN_VALID_RESPONSE_CHARS:
            raise CaptionParseError(f"見出し行を除いた応答が短すぎます ({len(body)}文字): {body!r}")

    if output_mode == "caption_only":
        # caption_only も自然文を返すため both と同じ後処理を行う
        body, at_stripped = strip_literal_at_trigger_word(body, trigger_word)
        if at_stripped:
            notes.append(LITERAL_AT_TRIGGER_NOTE)

    # tags_only は </think> と見出し行を除いた応答全体をそのまま使う
    # （プロンプト側で "---" 区切りなしの単純テキストを返すよう指示している）
    return body, notes


def resolve_tags_per_image(tags, count):
    # WD14 Tagger は OUTPUT_IS_LIST=(True,) で「画像1枚につき1件」のタグ文字列を返すため、
    # i番目の画像に i番目のタグを対応させる。
    # 手入力やSTRING直結で1件しか来ない場合は、全画像に同じタグを適用する（従来の挙動）。
    entries = list(tags) if isinstance(tags, list) else [tags]
    entries = [entry if isinstance(entry, str) else "" for entry in entries]

    if not entries:
        return [""] * count
    if len(entries) == 1:
        return [entries[0]] * count
    # 件数が画像より多ければ切り捨て、少なければ空文字で埋める
    # （空文字は 7.2 の事前チェックで empty_tags としてスキップ・記録される）
    resolved = entries[:count]
    resolved.extend([""] * (count - len(resolved)))
    return resolved


def split_image_name_entries(image_names):
    # 改行区切り（カンマ区切りも許容）のファイル名／パス一覧を配列にする
    return [entry.strip() for entry in re.split(r"[\r\n,]+", image_names or "") if entry.strip()]


def ensure_log_dir():
    # 7.3 ログ出力先（LOG_DIR）を用意する。作成に失敗してもログ書き込み側で握りつぶすため、
    # ここでは警告を出すだけで本処理は止めない。
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError as e:
        print(f"[YoshiakiLLMCaptionGenerator] ログ出力先の作成に失敗しました ({LOG_DIR}): {e}")
    return LOG_DIR


def resolve_image_labels(image_name_entries, count):
    # ログに出す画像名。namelist が渡っていればそのファイル名、無ければ連番で補う。
    labels = []
    for i in range(count):
        if i < len(image_name_entries):
            labels.append(os.path.basename(image_name_entries[i]) or image_name_entries[i])
        else:
            labels.append(f"image_{i + 1:03d}")
    return labels


def describe_image_part(pil_image, image_base64):
    # 画像パートの base64 は1枚で1MBを超えるため、ログには要約だけを残す
    approx_kb = len(image_base64) * 3 // 4 // 1024
    width, height = pil_image.size
    return f"<image {width}x{height} {IMAGE_FORMAT} 約{approx_kb}KB / base64は省略>"


class YoshiakiLLMCaptionGenerator:
    # 1. 入力ウィジェット・入力ソケットの定義
    @classmethod
    def INPUT_TYPES(cls):
        model_list = fetch_lemonade_models(DEFAULT_LEMONADE_HOST, DEFAULT_LEMONADE_PORT)
        if not model_list:
            model_list = [FALLBACK_MODEL_LABEL]

        system_prompt_files = list_system_prompt_files(SYSTEM_PROMPTS_DIR)
        if not system_prompt_files:
            system_prompt_files = [FALLBACK_SYSTEM_PROMPT_LABEL]

        return {
            "required": {
                "image": ("IMAGE",),
                # 見た目のみの調整（2026-09-08）: forceInput で純粋な入力ソケットにし、
                # display_name で WD14 Tagger 側の出力ラベル（"STRING" の日本語表示 "文字列"）と
                # 同じ表記にして、どのソケット同士が繋がっているかを見て分かるようにする。
                # 受け取る値・処理内容は従来と同じ（multiline ウィジェットが無くなるだけ）。
                "tags": ("STRING", {"multiline": True, "default": "", "forceInput": True,
                    "display_name": "文字列",
                    "tooltip": "WD14 Tagger の出力（文字列）を接続。画像1枚につき1件のタグ列。"}),
                "trigger_word": ("STRING", {"default": ""}),
                # 4.1 output_mode ウィジェットは廃止。system_prompt_file 1行目の
                # メタデータ行（<!-- output_mode: ... -->）から自動判定する
                "system_prompt_file": (system_prompt_files,),
                "lemonade_host": ("STRING", {"default": DEFAULT_LEMONADE_HOST}),
                "lemonade_port": ("INT", {"default": DEFAULT_LEMONADE_PORT, "min": 1, "max": 65535}),
                "lemonade_api_key": ("STRING", {"default": ""}),
                "model": (model_list,),
                "enable_thinking": ("BOOLEAN", {"default": True}),
                "temperature": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 2.0, "step": 0.05}),
                # 13.6 これは固定の生成上限ではなく「自動増量の初期値」。
                # finish_reason=="length"（parse_length）で失敗すると次の試行で倍増する。
                "max_tokens": ("INT", {
                    "default": 8192, "min": 1, "max": 32768,
                    "tooltip": "生成トークン数の初期値。応答が尻切れ(finish_reason=length)に"
                               "なった場合、リトライで自動的に倍増します"
                               "（モデルの max_context_window でクランプ）。",
                }),
                "timeout_sec": ("INT", {"default": 120, "min": 1, "max": 3600}),
                # 8章 ON にすると IS_CHANGED が毎回異なる値を返しキャッシュを無効化する
                "always_regenerate": ("BOOLEAN", {"default": False}),
                # ON にすると LLM への送信内容と生応答を prompt.log に記録する（既定OFF）。
                # システムプロンプトの検証用。コンソールには出さない（7.4準拠）。
                "log_prompt": ("BOOLEAN", {"default": False}),
                # 7.1 1画像あたりの最大試行回数（初回送信を含む総回数）。
                # 【追加位置について】ComfyUI は保存済みワークフローの widgets_values を
                # ウィジェットの定義順で位置対応させるため、既存ウィジェットの間に挿入すると
                # 古いワークフローの値がずれる。そのため required の末尾に追加している。
                # 値が無い古いワークフローでは resolve_max_retries() が既定の3を使う。
                "max_retries": ("INT", {
                    "default": DEFAULT_MAX_RETRIES,
                    "min": MIN_MAX_RETRIES, "max": MAX_MAX_RETRIES,
                    "tooltip": "1画像あたりの最大試行回数（初回送信を含む）。"
                               "1でリトライなし（初回失敗で即スキップ）。"
                               "失敗分類（connection/timeout/parse_length/parse_format）は"
                               "このカウンタを共有します。",
                }),
            },
            # ログに出す画像のファイル名（任意）。ComfyUI の IMAGE 型にはパス情報が
            # 含まれないため、LoRA Caption Load の namelist 相当を別途受け取る。
            # 未指定の場合は image_001 形式の連番をログのラベルに使う。
            "optional": {
                # 見た目のみの調整（2026-09-08）: tags と同様に forceInput ソケット化し、
                # display_name で LoRA Caption Load 側の出力ラベル "Name list" と同じ表記にする。
                "image_names": ("STRING", {"default": "", "multiline": True, "forceInput": True,
                    "display_name": "Name list",
                    "tooltip": "LoRA Caption Load の Name list を接続（ログ表示用のファイル名一覧。任意）。"}),
                # 衣装LoRA等、トリガーワードが「固定要素（衣装など）」を表す場合に使う。
                # 生成/作成時に使った基準タグ列を渡すと、システムプロンプト側で
                # 「WD14候補タグのうちこれと同一物理アイテムを指すものは除外する」判断材料になる
                # （例: caption_training_costume.txt）。空文字なら従来通りブロック自体を追加しない
                # ＝人物用システムプロンプト・既存ワークフローへの影響はゼロ。
                # placeholder は空欄時にテキストエリア内へ薄く表示される説明文（見た目のみ、値には影響しない）
                "reference_tags": ("STRING", {"default": "", "multiline": True,
                    "placeholder": "system pronptのcaption_training_costumeを使用する際に使用し、"
                                   "可変したい要素の生成時に使ったプロントを入力",
                    "tooltip": "衣装タグ等、トリガーワードが表す固定要素の基準タグ一覧（除外判断の参考情報）。"
                               "空欄なら従来通り送信しません。"}),
            },
        }

    # 2. 出力ソケットの型（複数なら型のタプル）
    RETURN_TYPES = ("STRING",)
    # 出力ラベルは接続先（LoRA Caption Save の text 入力）と同じ表記にする（2026-09-08、旧: caption_text）。
    # 出力はスロット番号で結線されるため、保存済みワークフローの接続には影響しない。
    RETURN_NAMES = ("text",)

    # 9章 WD14 Tagger は OUTPUT_IS_LIST=(True,) で画像枚数分のタグをリストで返す。
    # INPUT_IS_LIST を宣言しないと ComfyUI がリスト要素ごとにノードを再実行してしまい
    # （execution.py の map_node_over_list）、タグと画像の対応が崩れて N×N 回 LLM を呼ぶことになる。
    # 全入力をリストで受け取り、対応付けはノード側で行う。
    INPUT_IS_LIST = True

    # caption_text は image と同じ枚数・同じ順序のリストとして返す（指示書2.2 / 9章）
    OUTPUT_IS_LIST = (True,)

    # 3. 実際の処理を行うメソッド名（ComfyUIがこの名前で呼び出す）
    FUNCTION = "generate"

    # 4. ノード一覧で表示されるカテゴリ（サイドバーの分類）
    CATEGORY = "yoshiaki-comfy/LLM"

    # 5. 8章 キャッシュ制御。引数は INPUT_TYPES と同じ並び（optional の image_names のみ既定値あり）。
    #    INPUT_IS_LIST = True のため IS_CHANGED にも全入力がリストで渡る（execution.py の
    #    IsChangedCache が generate() と同じ _async_map_node_over_list 経由で呼ぶため）。
    #    なお他ノードから接続された入力は IS_CHANGED 呼び出し時点では確定しておらず (None,) で届く。
    @classmethod
    def IS_CHANGED(cls, image, tags, trigger_word, system_prompt_file, lemonade_host,
                   lemonade_port, lemonade_api_key, model, enable_thinking, temperature, max_tokens,
                   timeout_sec, always_regenerate, log_prompt,
                   max_retries=DEFAULT_MAX_RETRIES, image_names="", reference_tags=""):
        if first_value(always_regenerate, False):
            # ON: NaN は自身との等値比較が成立しないため、ComfyUI は常に「変化あり」と判断する
            return float("nan")
        # OFF: 固定値を返して ComfyUI 標準のキャッシュ挙動に任せる。
        # キャッシュキーには IS_CHANGED の戻り値に加えて全入力値と上流ノードの署名が含まれるため
        # （comfy_execution/caching.py の get_immediate_node_signature）、入力が変われば再実行される。
        return False

    def generate(self, image, tags, trigger_word, system_prompt_file, lemonade_host,
                 lemonade_port, lemonade_api_key, model, enable_thinking, temperature, max_tokens,
                 timeout_sec, always_regenerate=False, log_prompt=False,
                 max_retries=DEFAULT_MAX_RETRIES, image_names="", reference_tags=""):
        # always_regenerate はキャッシュ制御（IS_CHANGED）専用のため、生成処理では使用しない
        run_started = time.monotonic()
        # INPUT_IS_LIST = True のため全入力がリストで届く。tags 以外は単一値として取り出す。
        trigger_word = first_value(trigger_word, "")
        system_prompt_file = first_value(system_prompt_file)
        lemonade_host = first_value(lemonade_host, DEFAULT_LEMONADE_HOST)
        lemonade_port = first_value(lemonade_port, DEFAULT_LEMONADE_PORT)
        lemonade_api_key = first_value(lemonade_api_key, "")
        model = first_value(model)
        enable_thinking = first_value(enable_thinking, True)
        temperature = first_value(temperature)
        max_tokens = first_value(max_tokens)
        timeout_sec = first_value(timeout_sec)
        log_prompt = first_value(log_prompt, False)
        # 7.1 max_retries が無い古いワークフローでも落とさず既定の3回にフォールバックする
        max_retries = resolve_max_retries(first_value(max_retries, DEFAULT_MAX_RETRIES))
        image_names = first_value(image_names, "")
        reference_tags = first_value(reference_tags, "")

        # 4.1 メタデータ行から output_mode を判定し、その行を除いた本文を system message にする
        if system_prompt_file == FALLBACK_SYSTEM_PROMPT_LABEL:
            output_mode, system_prompt_text = None, ""
        else:
            output_mode, system_prompt_text = parse_system_prompt_file(
                system_prompt_file, CAPTION_OUTPUT_MODES, SYSTEM_PROMPTS_DIR
            )
        prompt_file_is_invalid = output_mode is None

        # image はバッチテンソル1個のリスト、または上流によってはテンソルのリストで届く
        images = list(iter_images(image))
        tags_per_image = resolve_tags_per_image(tags, len(images))
        # reference_tags も tags と同じ規則（1件なら全画像へブロードキャスト）で対応付ける
        reference_tags_per_image = resolve_tags_per_image(reference_tags, len(images))
        name_entries = split_image_name_entries(image_names)
        log_dir = ensure_log_dir()
        labels = resolve_image_labels(name_entries, len(images))

        # 7.4.1 デバッグ用の設定値サマリ。バッチ内で値は不変のため実行開始時に1回だけ出力する
        # （7.4 のコンソール出力簡略化を行う際もこの行は残すこと）
        summary = (f"開始: {len(images)}枚, model={model}, mode={output_mode or 'INVALID'}, "
                   f"prompt={system_prompt_file}, thinking={enable_thinking}, temp={temperature}, "
                   f"top_p={FIXED_TOP_P}, max_tokens={max_tokens}, timeout={timeout_sec}s, "
                   f"max_retries={max_retries}")
        print(f"[YoshiakiLLMCaptionGenerator] {summary}")
        print(f"[YoshiakiLLMCaptionGenerator] ログ出力先: {log_dir}")
        write_log(log_dir, f"RUN {summary}")

        # system message はバッチ内で不変のため実行開始時に1回だけ記録する
        if log_prompt:
            write_prompt_log(log_dir, f"==== RUN {summary} ====")
            write_prompt_log(
                log_dir,
                f"PROMPT system ({system_prompt_file}, {len(system_prompt_text)}文字):",
                system_prompt_text,
            )

        # 4.1 メタデータ行が無い／不正な場合は、この実行のすべての画像を失敗扱いにする
        if prompt_file_is_invalid:
            print(f"[YoshiakiLLMCaptionGenerator] INVALID_PROMPT_FILE: {system_prompt_file} "
                  f"({INVALID_PROMPT_FILE_REASON})")
            write_log(log_dir,
                      f"INVALID_PROMPT_FILE: {system_prompt_file} "
                      f"reason={INVALID_PROMPT_FILE_REASON}",
                      is_error=True)

        # 9章 タグと画像の件数が食い違うと対応がずれるため警告する（処理自体は継続）
        tag_count = len(tags) if isinstance(tags, list) else 1
        if tag_count > 1 and tag_count != len(images):
            warning = f"WARNING: タグ {tag_count}件 と 画像 {len(images)}枚 の件数が一致しません"
            print(f"[YoshiakiLLMCaptionGenerator] {warning}")
            write_log(log_dir, warning)

        # 13.6.1 上限クランプ用のコンテキスト長。バッチ内で不変なのでここで1回だけ解決する
        max_context_window = get_model_context_window(
            lemonade_host, lemonade_port, lemonade_api_key, model
        )

        results = []
        success_count = 0
        for index, image_tensor in enumerate(images, start=1):
            label = labels[index - 1]
            image_tags = tags_per_image[index - 1]
            image_reference_tags = reference_tags_per_image[index - 1]
            write_log(log_dir, f"START: {label}")

            # 4.1 事前チェック：プロンプトファイルが不正ならLLMを呼ばずに即スキップ
            if prompt_file_is_invalid:
                print(f"[YoshiakiLLMCaptionGenerator] SKIPPED: {label} ({REASON_INVALID_PROMPT_FILE})")
                write_log(log_dir,
                          f"SKIPPED: {label} reason={REASON_INVALID_PROMPT_FILE}", is_error=True)
                # 9章：スキップしても枚数・順序を崩さないよう空文字を入れる
                results.append("")
                continue

            # 7.2 事前チェック：tags が空文字ならLLMを呼ばずに即スキップ（リトライ対象外）
            if not image_tags.strip():
                print(f"[YoshiakiLLMCaptionGenerator] SKIPPED: {label} (empty_tags)")
                write_log(log_dir, f"SKIPPED: {label} reason=empty_tags", is_error=True)
                # 9章：スキップしても枚数・順序を崩さないよう空文字を入れる
                results.append("")
                continue

            pil_image = resize_if_needed(tensor_to_pil(image_tensor))
            image_base64 = encode_image_base64(pil_image)
            print(f"[YoshiakiLLMCaptionGenerator] {index}/{len(images)} 送信中 "
                  f"(size={pil_image.size[0]}x{pil_image.size[1]})")

            # 7.1 4分類（connection / timeout / parse_length / parse_format）を
            # 同一カウンタで最大 max_retries 回試行する（初回送信を含む総試行回数）
            caption = ""
            # 13.6.1 クランプに使うプロンプト側トークン数。応答の usage が取れたら実測値へ差し替える
            prompt_tokens = estimate_prompt_tokens(
                system_prompt_text,
                build_user_text(image_tags, trigger_word, reference_tags=image_reference_tags)
            )
            attempt_max_tokens, attempt_temperature, attempt_clamped = max_tokens, temperature, False
            # 7.1 直前の試行の失敗理由に応じて次の試行のパラメータを分岐させる
            previous_reason = None
            for attempt in range(1, max_retries + 1):
                # params_source / format_correction は previous_reason を上書きする前に決める
                params_source = describe_params_source(previous_reason, attempt)
                # 5.2 直前が parse_format のときだけ訂正指示を追記する。
                # 訂正文が "---" 区切り（PART1/PART2）についての内容なので both のみ対象とする。
                # timeout / connection / parse_length はフォーマットの問題ではないため追記しない。
                format_correction = (previous_reason == REASON_PARSE_FORMAT
                                     and output_mode == "both")
                attempt_max_tokens, attempt_temperature, attempt_clamped = next_attempt_params(
                    previous_reason, attempt, attempt_max_tokens, attempt_temperature,
                    max_tokens, temperature, max_context_window, prompt_tokens
                )
                messages = build_messages(system_prompt_text, image_tags, trigger_word,
                                          image_base64, format_correction,
                                          reference_tags=image_reference_tags)
                payload = build_chat_payload(model, messages, enable_thinking,
                                             attempt_temperature, attempt_max_tokens)

                if log_prompt:
                    # 7.3.1 その試行で実際に送った user message をそのまま記録する
                    write_prompt_log(
                        log_dir,
                        f"PROMPT user {label} ({index}/{len(images)}, "
                        f"attempt {attempt}/{max_retries}):",
                        f"{build_user_text(image_tags, trigger_word, format_correction, reference_tags=image_reference_tags)}\n"
                        f"{describe_image_part(pil_image, image_base64)}",
                    )
                # 13.1 リクエストごとに一意なIDを発行し、タイムアウト時のキャンセルに使う
                request_id = str(uuid.uuid4())
                try:
                    request_started = time.monotonic()
                    response_payload = request_chat_completion(
                        lemonade_host, lemonade_port, lemonade_api_key, payload, timeout_sec,
                        request_id=request_id
                    )
                    elapsed = time.monotonic() - request_started
                    # 13.6.1 実測のプロンプトトークン数が取れれば概算より優先する
                    actual_prompt_tokens = (response_payload.get("usage") or {}).get("prompt_tokens")
                    if isinstance(actual_prompt_tokens, int) and actual_prompt_tokens > 0:
                        prompt_tokens = actual_prompt_tokens
                    if log_prompt:
                        timing = format_response_timing(elapsed, response_payload)
                        write_prompt_log(
                            log_dir,
                            f"RESPONSE {label} (attempt {attempt}/{max_retries}, {timing}, "
                            f"max_tokens={attempt_max_tokens}, temp={attempt_temperature}):",
                            format_response_for_log(response_payload),
                        )
                    raw_response = extract_response_text(response_payload)
                    # 6.3 パース失敗時にどちらの分類として扱うかを finish_reason から決めておく
                    failure_category = classify_parse_failure(response_payload, attempt_max_tokens)
                    caption, parse_notes = parse_response(
                        raw_response, output_mode, trigger_word, failure_category
                    )
                    # 6.1.1 / 6.1.2 後処理で応答に手を入れた場合は内容を NOTE として残す
                    for note in parse_notes:
                        write_log(log_dir, f"NOTE: {note} image={label}")
                    write_log(log_dir, f"SUCCESS: {label} mode={output_mode} attempt={attempt}")
                    success_count += 1
                    break
                except RETRYABLE_EXCEPTIONS as e:
                    reason = classify_error(e)
                    previous_reason = reason
                    if reason == REASON_TIMEOUT:
                        # 13.5 HTTP接続の切断そのものがキャンセル手段として機能する。
                        # Lemonade Server v11.7.0 の PR #3133 により、prefill中（初トークン
                        # 生成前）の切断も上流リクエストへ伝わり生成が中断される。
                        # 接続は request_chat_completion() の finally で確実に閉じている。
                        write_log(log_dir,
                                  f"CONNECTION_ABORTED: {label} reason=timeout "
                                  f"note=prefill_cancel_supported_v11.7+")
                        # 13.5.1 その上で、正式なキャンセルAPIが設定されていれば保険として呼ぶ
                        cancel_request(log_dir, lemonade_host, lemonade_port,
                                       lemonade_api_key, request_id)
                    # 13.3 / 13.6.2 各試行で実際に使用したパラメータと分類を記録する。
                    # クランプ・訂正指示の追加が発生した試行には note= を付記する。
                    notes = []
                    if attempt_clamped:
                        notes.append(CLAMP_LOG_NOTE)
                    if format_correction:
                        notes.append(FORMAT_CORRECTION_LOG_NOTE)
                    note_text = ("".join(f" {note}" for note in notes))
                    write_log(log_dir,
                              f"RETRY: {label} attempt={attempt}/{max_retries} "
                              f"max_tokens={attempt_max_tokens} temperature={attempt_temperature} "
                              f"applied={params_source} reason={reason}{note_text} detail={e}")
                    if attempt == max_retries:
                        # 7.4 コンソールはファイル名＋簡易理由のみ。詳細はログファイル参照
                        print(f"[YoshiakiLLMCaptionGenerator] SKIPPED: {label} ({reason})")
                        write_log(log_dir,
                                  f"SKIPPED: {label} reason={reason} "
                                  f"({max_retries} attempts exhausted)",
                                  is_error=True)
                        # 9章：失敗時も空文字で枚数を揃える
                        caption = ""

            results.append(caption)

        skipped_count = len(images) - success_count
        print(f"[YoshiakiLLMCaptionGenerator] 完了: 成功 {success_count}件 / スキップ {skipped_count}件"
              + (f"（詳細は {os.path.join(log_dir, ERROR_LOG_FILENAME)} を参照）"
                 if skipped_count else ""))
        write_log(log_dir, f"RUN END: success={success_count} skipped={skipped_count} "
                           f"elapsed={format_duration(time.monotonic() - run_started)}")

        return (results,)


NODE_CLASS_MAPPINGS = {
    "YoshiakiLLMCaptionGenerator": YoshiakiLLMCaptionGenerator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YoshiakiLLMCaptionGenerator": "Yoshiaki-LLMCaptionGenerator",
}
