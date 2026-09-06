import datetime
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_LEMONADE_HOST = "192.168.85.57"
DEFAULT_LEMONADE_PORT = 13305
MODELS_FETCH_TIMEOUT_SEC = 3
FALLBACK_MODEL_LABEL = "(Lemonade Server unavailable - check host/port)"

# system_prompts系フォルダはノードごとに分離する。
# キャプションノード用（既存のパスをそのまま維持）と翻訳ノード用（新規）の2つ。
SYSTEM_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system_prompts")
TRANSLATION_SYSTEM_PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "system_prompts_translate"
)
FALLBACK_SYSTEM_PROMPT_LABEL = "(no .txt files found in system_prompts/)"

# 4.1 output_mode はウィジェットではなく、プロンプトファイル1行目のメタデータ行から判定する
#     例: <!-- output_mode: both -->
OUTPUT_MODE_HEADER_PATTERN = re.compile(r"^\s*<!--\s*output_mode\s*:\s*([A-Za-z_]+)\s*-->\s*$")
# ノードごとに許可する output_mode が異なるため、呼び出し側が valid_modes を指定する
# （parse_system_prompt_file 参照）。
CAPTION_OUTPUT_MODES = ("tags_only", "caption_only", "both")
TRANSLATION_OUTPUT_MODES = ("prompt_translation",)
# 4.1 メタデータ行が無い／値が不正なファイルを選択したときのログ・スキップ理由
INVALID_PROMPT_FILE_REASON = "missing_or_invalid_output_mode_header"
REASON_INVALID_PROMPT_FILE = "invalid_prompt_file"

# 5.3 top_p は内部固定値
FIXED_TOP_P = 1.0

# 13.5 リクエストはストリーミングで送る。
# Lemonade Server は「クライアントへ書き込む際に接続をポーリングする」実装（v11.7.0 PR #3133）
# のため、非ストリーミングだと生成フェーズでの切断がサーバーへ伝わらず、打ち切ったはずの生成が
# 最後まで走り続ける（実機で 4/4 再現。stream=True では 4/4 即解放）。
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
SSE_DATA_PREFIX = "data:"
SSE_DONE_MARKER = "[DONE]"
# HTTPエラー時に読み取る本文の上限
MAX_ERROR_BODY_BYTES = 2048

# 6章 出力パース
# 実機の Lemonade Server は thinking を message.reasoning_content に分離して返し、
# content にはインラインの <think> を含めない（2026-08-23 実機再確認）。
# ただし <think> をインラインで返すサーバー／モデルもあるため、保険として除去処理は残す。
THINK_CLOSE_TAG = "</think>"
# 6.2 これより短い応答は「応答不正」とみなす（タグ1個の最短ケースを潰さない範囲で設定）
MIN_VALID_RESPONSE_CHARS = 4

# 7章 エラーハンドリング・リトライ・ログ
# 7.1 接続失敗／タイムアウト／パース失敗を同一カウンタで最大 max_retries 回試行する。
# 回数は 2.1 の max_retries ウィジェットで指定する（初回送信を含む総試行回数）。
# 下限1はリトライなし（初回失敗で即スキップ）、上限は暴走時の待ち時間が膨らむのを防ぐため10。
DEFAULT_MAX_RETRIES = 3
MIN_MAX_RETRIES = 1
MAX_MAX_RETRIES = 10
ERROR_LOG_FILENAME = "error.log"
FULL_LOG_FILENAME = "log.log"
# log_prompt が ON のときだけ書き出す、LLMへの送信内容と生応答の記録
PROMPT_LOG_FILENAME = "prompt.log"
# prompt.log の多行本文につけるインデント（行指向のログと混ざらないようにする）
PROMPT_LOG_INDENT = "    "
# 7.3 ログのタイムスタンプ書式
LOG_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# 13章 Thinkモード暴走対策
# 13.1 タイムアウト時にサーバー側の生成を明示的に中断させるキャンセルAPIのパス。
# 【2026-08-23 実サーバー調査結果】Lemonade Server 11.5.0 にはキャンセル用エンドポイントが
# 存在しない（/openapi.json /docs は404。/api/v1 配下の halt / stop / cancel / abort /
# interrupt / terminate / kill / requests / generate-stop、および OpenAI Responses API 形式の
# /responses/{id}/cancel、DELETE /chat/completions/{id} をすべて確認し全て404）。
# 唯一 POST /api/v1/unload が200を返すが、これはモデル自体をアンロードするため
# 他の処理・他の利用者にも影響し、キャンセル用途には使えない。
# → 空文字の間はキャンセル呼び出しをスキップする。将来サーバーが対応したらここにパスを設定するだけでよい
#    （例: "/api/v1/cancel"）。リクエストのボディは {"request_id": ...} で送る。
LEMONADE_CANCEL_PATH = ""
CANCEL_TIMEOUT_SEC = 5

# 7.1 / 6.3 リトライ対象の失敗分類
REASON_CONNECTION = "connection"
REASON_TIMEOUT = "timeout"
REASON_PARSE_LENGTH = "parse_length"
REASON_PARSE_FORMAT = "parse_format"
# 13.2 の縮小方向の調整を適用する分類（それ以外はパラメータを据え置く）
SHRINK_REASONS = (REASON_TIMEOUT, REASON_PARSE_FORMAT)

# 13.2 リトライ時のパラメータ調整。ウィジェットには公開しない。
# 2回目は max_tokens 半分・temperature +0.2、3回目は 1/4・+0.4。下限/上限でクリップする。
#
# 【max_retries 対応：案B（計算式への一般化）を採用】
# 旧実装は3行固定のテーブル（scale 1.0/0.5/0.25、delta 0.0/0.2/0.4）だったが、
# max_retries が3を超えると4回目以降の行が無い。案A（3回目の調整幅を据え置いて繰り返す）
# ではなく案B（計算式）を採用した。理由は、テーブルの値がもともと「半分ずつ縮小・+0.2ずつ上昇」
# という規則そのものであり、式にすれば試行回数が何回になっても同じ規則で延長できるため。
#   max_tokens  = ウィジェット設定値 * RETRY_MAX_TOKENS_SHRINK_RATIO ** (試行回数-1)
#   temperature = min(上限, ウィジェット設定値 + RETRY_TEMPERATURE_STEP * (試行回数-1))
# 試行1〜3の結果は旧テーブルと完全に一致する（1.0 / 0.5 / 0.25、+0.0 / +0.2 / +0.4）。
# 下限（RETRY_MAX_TOKENS_FLOOR）と上限（RETRY_TEMPERATURE_CEILING）は既存の定数のまま据え置き、
# 4回目以降は下限テーブル末尾の値（256）と temperature 上限（1.0）でクリップされ続ける。
RETRY_MAX_TOKENS_SHRINK_RATIO = 0.5
RETRY_MAX_TOKENS_FLOOR = (0, 512, 256)
RETRY_TEMPERATURE_STEP = 0.2
RETRY_TEMPERATURE_CEILING = 1.0

# 13.6 parse_length（finish_reason=="length"）時は max_tokens を直前の2倍にして再試行する
RETRY_MAX_TOKENS_GROWTH = 2
# 13.6.1 クランプ後もこれを下回らせない
MIN_MAX_TOKENS = 256
# 13.6.1 プロンプト側トークン数の概算。usage.prompt_tokens が取れる場合はそちらを優先する
CHARS_PER_TOKEN_ESTIMATE = 4
IMAGE_PROMPT_TOKENS_ESTIMATE = 1024
# 13.6.1 max_context_window ぎりぎりを避けるための余裕
CONTEXT_SAFETY_MARGIN_TOKENS = 256
CLAMP_LOG_NOTE = "note=clamped_by_max_context_window"

# 3章のモデル一覧取得時に拾う max_context_window のキャッシュ（13.6.1のクランプに使う）
MODEL_CONTEXT_WINDOWS = {}


class CaptionParseError(Exception):
    """6.2 応答不正。7.1 のリトライ対象。

    category には 6.3 の分類（parse_length / parse_format）を持たせ、
    13.2（縮小）と 13.6（増量）のどちらへ分岐するかの判断に使う。
    クラス名は CaptionParseError のままだが、画像専用ではなく
    LLM呼び出し全般（キャプション・翻訳の両ノード）の応答パース例外として使う。
    """

    def __init__(self, message, category=REASON_PARSE_FORMAT):
        super().__init__(message)
        self.category = category


def build_lemonade_base_url(host, port):
    host = (host or DEFAULT_LEMONADE_HOST).strip()
    return f"http://{host}:{port}/v1"


def fetch_lemonade_models(host=DEFAULT_LEMONADE_HOST, port=DEFAULT_LEMONADE_PORT, api_key=""):
    # ComfyUI の INPUT_TYPES 評価タイミング（起動時／ブラウザF5）でのみ呼ばれる。
    # ここで例外を外に投げると ComfyUI 自体の起動が止まるため、失敗時は必ず空リストを返す。
    url = f"{build_lemonade_base_url(host, port)}/models"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=MODELS_FETCH_TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"[YoshiakiLLMCaptionGenerator] Lemonade Server のモデル一覧取得に失敗しました ({url}): {e}")
        return []

    entries = payload.get("data", []) if isinstance(payload, dict) else []
    model_ids = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        model_ids.append(entry["id"])
        # 13.6.1 の上限クランプで使うためコンテキスト長も保持しておく
        window = entry.get("max_context_window")
        if isinstance(window, int) and window > 0:
            MODEL_CONTEXT_WINDOWS[entry["id"]] = window
    return model_ids


def get_model_context_window(host, port, api_key, model):
    # 13.6.1 クランプ用の max_context_window。3章のモデル一覧取得時のキャッシュを使い、
    # 未取得なら一度だけ取りに行く。取得できなければ None を返し、その場合クランプは行わない。
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]

    fetch_lemonade_models(host, port, api_key)
    # 取得できなかった場合も None をキャッシュし、画像ごとに再取得しにいかないようにする
    MODEL_CONTEXT_WINDOWS.setdefault(model, None)
    return MODEL_CONTEXT_WINDOWS[model]


def list_system_prompt_files(directory):
    # system_prompts系フォルダが存在しない、または .txt が1つもない場合は空リストを返す。
    # INPUT_TYPES から呼ばれるため、例外で ComfyUI 起動を止めないこと。
    try:
        filenames = [f for f in os.listdir(directory) if f.lower().endswith(".txt")]
    except OSError as e:
        print(f"[yoshiaki-comfy LLM] system_prompts フォルダの読み取りに失敗しました ({directory}): {e}")
        return []
    return sorted(filenames)


def read_system_prompt_file(filename, directory):
    path = os.path.join(directory, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_system_prompt_file(filename, valid_modes, directory):
    """1行目のメタデータ行から output_mode を判定し、その行を除いた本文を返す。

    戻り値は (output_mode, system_message)。メタデータ行が無い・valid_modes に
    含まれない値・ファイルが読めない場合は output_mode を None にして返す
    （呼び出し側で失敗扱いにする）。ComfyUI自体を止めないため例外は送出しない。
    """
    try:
        text = read_system_prompt_file(filename, directory)
    except OSError as e:
        print(f"[yoshiaki-comfy LLM] system prompt の読み込みに失敗しました ({filename}): {e}")
        return None, ""

    lines = text.splitlines()
    match = OUTPUT_MODE_HEADER_PATTERN.match(lines[0]) if lines else None
    if not match:
        return None, text

    output_mode = match.group(1).strip()
    if output_mode not in valid_modes:
        return None, text

    # メタデータ行はLLMに見せない。除去後に先頭へ残る空行も落とす
    return output_mode, "\n".join(lines[1:]).lstrip("\n")


def build_chat_payload(model, messages, enable_thinking, temperature, max_tokens):
    # 5.3 enable_thinking は chat template 側のフラグとして渡す（llama.cpp / vLLM 系の
    # OpenAI互換サーバー共通の指定方法）。サーバー側が未対応の場合は無視されるだけで害はない。
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": FIXED_TOP_P,
        "chat_template_kwargs": {"enable_thinking": bool(enable_thinking)},
        # 13.5 切断をサーバーに伝えるためストリーミングで受け取る（上のコメント参照）。
        # include_usage を付けると最終チャンクに usage が入り、6.3 の分類・13.6 のクランプ・
        # tok/s の算出にそのまま使える（実機で取得できることを確認済み）。
        "stream": True,
        "stream_options": {"include_usage": True},
    }


def read_sse_completion(conn, response, deadline):
    """13.5 SSE を読み、非ストリーミング応答と同じ形の dict に集約して返す。

    deadline（`time.monotonic()` 基準の絶対時刻）を超えたら TimeoutError を送出する。
    ストリーミングではソケットの timeout は「チャンク間隔」にしか効かないため、
    総経過時間の管理は自前で行い、読み取りごとに残り時間をソケットへ設定する。
    """
    content_parts = []
    reasoning_parts = []
    finish_reason = None
    usage = None

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # 呼び出し元の finally で接続を閉じ、切断をサーバーへ伝える
            raise TimeoutError("timed out")
        if conn.sock is not None:
            conn.sock.settimeout(remaining)

        raw_line = response.readline()
        if not raw_line:
            break

        line = raw_line.decode("utf-8", "replace").strip()
        if not line.startswith(SSE_DATA_PREFIX):
            continue
        data = line[len(SSE_DATA_PREFIX):].strip()
        if data == SSE_DONE_MARKER:
            break

        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            # 壊れた行は読み飛ばす（全体を失敗させない）
            continue

        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])

    # 6.3 の分類・13.6 のクランプ・各種ログ処理を変更せずに使えるよう、
    # 非ストリーミング応答と同じ構造に組み立てて返す
    return {
        "choices": [{
            "finish_reason": finish_reason,
            "message": {
                "content": "".join(content_parts),
                "reasoning_content": "".join(reasoning_parts),
            },
        }],
        "usage": usage or {},
    }


def request_chat_completion(host, port, api_key, payload, timeout_sec, request_id=None):
    """ストリーミングでリクエストし、SSE を集約した応答 dict を返す。

    例外はそのまま呼び出し元（7.1 のリトライ処理）へ送出する。
    `timeout_sec` は「総経過時間」の上限として扱う（read_sse_completion 参照）。
    """
    host = (host or DEFAULT_LEMONADE_HOST).strip()
    url = f"http://{host}:{port}{CHAT_COMPLETIONS_PATH}"
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # 13.1 タイムアウト時にサーバー側の生成を特定・中断できるよう一意なIDを付与する
    if request_id:
        headers["X-Request-Id"] = request_id

    body = json.dumps(payload).encode("utf-8")
    deadline = time.monotonic() + timeout_sec

    # 13.5.1 ストリーミングでは接続の明示クローズが必須。urllib ではなく http.client を
    # 直接使うことで、読み取りごとの残り時間設定と finally での確実な close を保証する。
    conn = http.client.HTTPConnection(host, port, timeout=timeout_sec)
    try:
        conn.request("POST", CHAT_COMPLETIONS_PATH, body=body, headers=headers)
        response = conn.getresponse()
        if response.status >= 400:
            detail = response.read(MAX_ERROR_BODY_BYTES).decode("utf-8", "replace")
            # classify_error が http_{code} を返せるよう urllib の例外型に合わせる
            raise urllib.error.HTTPError(url, response.status, detail, response.headers, None)
        return read_sse_completion(conn, response, deadline)
    finally:
        # 13.5 タイムアウト・例外時に確実にTCP接続を閉じ、切断をサーバーへ伝える。
        # 生成フェーズの切断がサーバーへ届くのはストリーミングだからで、
        # 非ストリーミングだと打ち切った生成が最後まで走り続ける（実機確認済み）。
        conn.close()


def extract_response_text(response_payload):
    # HTTP応答から生のテキストを取り出すだけ（パースは呼び出し側で行う）
    choice = response_payload["choices"][0]
    message = choice["message"]
    content = (message.get("content") or "").strip()
    if content:
        return content

    # 実機のサーバーは thinking を reasoning_content に分離するため、
    # content が空 = 本文が1文字も生成されていない状態。ここで理由を確定させておかないと
    # 6章のパースで「応答が短すぎます (0文字)」という原因不明のエラーになる。
    finish_reason = choice.get("finish_reason")
    thinking_chars = len((message.get("reasoning_content") or "").strip())
    if finish_reason == "length":
        # 6.3 parse_length。13.6 の max_tokens 増量で回復を狙う
        raise CaptionParseError(
            f"max_tokens に達したため本文が生成されませんでした"
            f"（thinking で {thinking_chars} 文字を消費）",
            REASON_PARSE_LENGTH,
        )
    raise CaptionParseError(
        f"モデルが本文を返しませんでした (finish_reason={finish_reason}, "
        f"thinking {thinking_chars} 文字)",
        REASON_PARSE_FORMAT,
    )


def strip_thinking(text):
    # </think> 以降のみを抽出する。<think> が無い場合は全体を対象とする。
    # 複数回出現した場合は最後の </think> 以降を採用する。
    # 実機のサーバーは thinking を分離して返すためここは通常ノーオペだが、
    # インラインで <think> を返す構成向けの保険として残している。
    text = text or ""
    _, separator, after = text.rpartition(THINK_CLOSE_TAG)
    return after if separator else text


def classify_parse_failure(response_payload, requested_max_tokens):
    # 6.3 パース失敗の理由を finish_reason で分類する（"---" の有無だけで判定しない）。
    choices = response_payload.get("choices") or [{}]
    choice = choices[0] if isinstance(choices[0], dict) else {}
    if choice.get("finish_reason") == "length":
        return REASON_PARSE_LENGTH

    # usage が取れる場合は補強材料として使う（completion_tokens が max_tokens に張り付いていれば
    # finish_reason が "stop" でも打ち切りとみなす）。usage 未対応サーバーでは finish_reason のみ。
    usage = response_payload.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    if (requested_max_tokens and isinstance(completion_tokens, (int, float))
            and completion_tokens >= requested_max_tokens):
        return REASON_PARSE_LENGTH
    return REASON_PARSE_FORMAT


def first_value(value, default=None):
    # INPUT_IS_LIST = True のため全入力がリストで届く。ウィジェット値は要素1個のリストになる。
    # 未接続の optional 入力は素の値（関数定義のデフォルト）で来る場合もあるため両方許容する。
    if isinstance(value, list):
        return value[0] if value else default
    return default if value is None else value


def resolve_max_retries(value):
    """2.1 / 7.1 max_retries ウィジェット値を安全な試行回数（整数）に丸める。

    max_retries ウィジェットが存在しなかった頃のワークフローJSONを読み込むと、値が
    届かない（None）／型が違うことがある。その場合でもエラーにせず既定の3回を使う。
    範囲外の値は 1〜10 にクリップする（下限1＝リトライなし、上限は暴走防止）。
    """
    try:
        retries = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_RETRIES
    return max(MIN_MAX_RETRIES, min(MAX_MAX_RETRIES, retries))


def ensure_log_dir_at(subdir_name):
    # 7.3 ログ出力先を用意する汎用版（ensure_log_dir の subdir_name 指定版）。
    # 作成に失敗してもログ書き込み側で握りつぶすため、ここでは警告を出すだけで本処理は止めない。
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), subdir_name)
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        print(f"[yoshiaki-comfy LLM] ログ出力先の作成に失敗しました ({log_dir}): {e}")
    return log_dir


def append_log_line(log_dir, filename, line):
    # 7.3 追記型。書き込みのたびに open/close する（長時間バッチの途中でも内容が確定し、
    # ComfyUIが落ちてもログが失われない）。ログ書き込みの失敗で本処理を止めないこと。
    path = os.path.join(log_dir, filename)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"[YoshiakiLLMCaptionGenerator] ログ書き込みに失敗しました ({path}): {e}")


def log_timestamp():
    return datetime.datetime.now().strftime(LOG_TIMESTAMP_FORMAT)


def write_log(log_dir, message, is_error=False):
    # log.log は全処理ログ、error.log は失敗のみ（error.log の内容は log.log にも含まれる）
    line = f"[{log_timestamp()}] {message}"
    append_log_line(log_dir, FULL_LOG_FILENAME, line)
    if is_error:
        append_log_line(log_dir, ERROR_LOG_FILENAME, line)


def write_prompt_log(log_dir, header, body=""):
    # log_prompt が ON のときだけ呼ばれる。多行の本文はインデントして1ブロックとして追記する。
    block = f"[{log_timestamp()}] {header}"
    if body:
        indented = "\n".join(PROMPT_LOG_INDENT + line for line in body.splitlines())
        block = f"{block}\n{indented}"
    append_log_line(log_dir, PROMPT_LOG_FILENAME, block)


def format_duration(seconds):
    # 実行全体の所要時間表示用
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}秒"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}時間{minutes}分{secs}秒"
    return f"{minutes}分{secs}秒"


def format_response_timing(elapsed_sec, response_payload):
    # RESPONSE の見出し用。usage を返さないサーバーもあるため tok/s は取れるときだけ付ける。
    parts = [f"{elapsed_sec:.1f}秒"]
    usage = response_payload.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    if isinstance(completion_tokens, (int, float)) and elapsed_sec > 0:
        parts.append(f"{completion_tokens / elapsed_sec:.1f} tok/s")
    return ", ".join(parts)


def format_response_for_log(response_payload):
    # 生応答の記録用。thinking は content と分離して返るサーバーがあるため両方を残す。
    # ここで例外を出すとリトライ判定に紛れ込むため、すべて defensive に取り出す。
    choices = response_payload.get("choices") or [{}]
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or ""

    blocks = [f"finish_reason={choice.get('finish_reason')} usage={response_payload.get('usage')}"]
    if reasoning:
        blocks.append(f"--- reasoning_content ({len(reasoning)}文字) ---\n{reasoning}")
    blocks.append(f"--- content ({len(content)}文字) ---\n{content}")
    return "\n".join(blocks)


def classify_error(error):
    # 7.1 の4分類（connection / timeout / parse_length / parse_format）を返す。
    # 4分類に当てはまらないもの（HTTPエラー・不正JSON等）は独自の名前を返し、
    # パラメータ調整の対象外（据え置き）として扱う。
    if isinstance(error, CaptionParseError):
        return getattr(error, "category", REASON_PARSE_FORMAT)
    if isinstance(error, urllib.error.HTTPError):
        return f"http_{error.code}"
    # 読み取りタイムアウトは TimeoutError、接続タイムアウトは URLError(reason=TimeoutError) で来る
    if isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError):
        return REASON_TIMEOUT
    if isinstance(error, urllib.error.URLError):
        return REASON_CONNECTION
    if isinstance(error, (json.JSONDecodeError, KeyError, IndexError)):
        return "invalid_response"
    return type(error).__name__


def estimate_prompt_tokens(system_prompt_text, user_text, has_image=True):
    # 13.6.1 プロンプト側トークン数の概算。厳密なトークナイザ計算は不要で、
    # 「明らかに超過する組み合わせを避ける」ことが目的。
    # 実応答の usage.prompt_tokens が取れる場合はそちらを優先する（呼び出し側で差し替える）。
    chars = len(system_prompt_text or "") + len(user_text or "")
    estimate = chars // CHARS_PER_TOKEN_ESTIMATE
    if has_image:
        # 画像はbase64の文字数ではなく画像トークンとして数えられるため固定値で見積もる
        estimate += IMAGE_PROMPT_TOKENS_ESTIMATE
    return estimate


def clamp_max_tokens(desired_max_tokens, prompt_tokens, max_context_window):
    # 13.6.1 「プロンプト側の推定トークン数 + max_tokens」が max_context_window を
    # 超えないようクランプする。戻り値は (max_tokens, クランプしたか)。
    if not max_context_window:
        return desired_max_tokens, False

    allowed = max_context_window - prompt_tokens - CONTEXT_SAFETY_MARGIN_TOKENS
    allowed = max(MIN_MAX_TOKENS, allowed)
    if desired_max_tokens > allowed:
        return allowed, True
    return desired_max_tokens, False


def shrink_retry_params(attempt, base_max_tokens, base_temperature):
    # 13.2 暴走の再発防止。調整幅は「試行回数」から計算する（基準はウィジェット設定値）。
    # 案Bを採用しているため max_retries が4以上でも同じ規則で縮小・上昇を続けられる。
    steps = attempt - 1
    scaled = int(base_max_tokens * (RETRY_MAX_TOKENS_SHRINK_RATIO ** steps))
    # 下限は既存の定数のまま。テーブルを超える試行回数では末尾の値（256）を使い続ける。
    floor = RETRY_MAX_TOKENS_FLOOR[min(steps, len(RETRY_MAX_TOKENS_FLOOR) - 1)]
    # 下限でクリップしたうえで、元の設定値を超えないようにする
    # （ユーザーが下限より小さい max_tokens を設定している場合に増えてしまうのを防ぐ）
    max_tokens = min(base_max_tokens, max(floor, scaled))
    # 浮動小数の誤差がログに出ないよう丸める（0.3 + 0.4 = 0.7000000000000001 対策）
    temperature = round(min(RETRY_TEMPERATURE_CEILING,
                            base_temperature + RETRY_TEMPERATURE_STEP * steps), 2)
    return max_tokens, temperature


def describe_params_source(previous_reason, attempt):
    """13.3 ログ可読性のための補助。

    `RETRY` 行の `reason=` は「その試行が失敗した理由」であって
    「そのパラメータを選んだ理由」ではない。両者を取り違えた誤読が実運用で発生したため、
    パラメータがどの分岐で決まったのかを `applied=` として併記する。
    """
    if attempt <= 1:
        return "initial"
    if previous_reason == REASON_PARSE_LENGTH:
        return f"13.6_grow(prev={previous_reason})"
    if previous_reason in SHRINK_REASONS:
        return f"13.2_shrink(prev={previous_reason})"
    return f"keep(prev={previous_reason})"


def next_attempt_params(previous_reason, attempt, current_max_tokens, current_temperature,
                        base_max_tokens, base_temperature, max_context_window, prompt_tokens):
    """7.1 直前の試行の失敗理由で次の試行のパラメータを決める（固定の試行回数テーブルではない）。

    戻り値は (max_tokens, temperature, クランプしたか)。
    - parse_length            : 13.6 直前に使用した値の2倍（max_context_window でクランプ）
    - timeout / parse_format  : 13.2 の縮小テーブル（試行回数で索く。基準はウィジェット設定値）
    - connection / その他     : 調整なし（直前に使用した値のまま再試行）
    """
    if attempt <= 1:
        return base_max_tokens, base_temperature, False

    if previous_reason == REASON_PARSE_LENGTH:
        desired = current_max_tokens * RETRY_MAX_TOKENS_GROWTH
        max_tokens, clamped = clamp_max_tokens(desired, prompt_tokens, max_context_window)
        # 13.6 は max_tokens のみを調整し temperature は据え置く
        return max_tokens, current_temperature, clamped

    if previous_reason in SHRINK_REASONS:
        max_tokens, temperature = shrink_retry_params(attempt, base_max_tokens, base_temperature)
        return max_tokens, temperature, False

    return current_max_tokens, current_temperature, False


def cancel_request(log_dir, host, port, api_key, request_id):
    # 13.1 タイムアウト時にサーバー側の生成を明示的に中断させる。
    # ベストエフォートであり、失敗しても 7.1 のリトライ処理は継続する（成功は必須条件にしない）。
    if not LEMONADE_CANCEL_PATH:
        write_log(log_dir,
                  f"CANCEL_SKIPPED request_id={request_id} reason=no_endpoint_configured")
        return False

    host = (host or DEFAULT_LEMONADE_HOST).strip()
    url = f"http://{host}:{port}{LEMONADE_CANCEL_PATH}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = json.dumps({"request_id": request_id}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=CANCEL_TIMEOUT_SEC):
            pass
    except (OSError, ValueError) as e:
        write_log(log_dir, f"CANCEL_FAILED request_id={request_id} reason={e}")
        return False

    write_log(log_dir, f"CANCEL_REQUEST_SENT request_id={request_id}")
    return True


# 7.1 リトライ対象の例外。
# urllib.error.URLError / HTTPError / TimeoutError はいずれも OSError のサブクラスなので
# 接続失敗・タイムアウトは OSError で捕捉できる。JSON/キー欠落は応答異常、
# CaptionParseError は 6.2 の応答不正。
RETRYABLE_EXCEPTIONS = (OSError, json.JSONDecodeError, KeyError, IndexError, CaptionParseError)
