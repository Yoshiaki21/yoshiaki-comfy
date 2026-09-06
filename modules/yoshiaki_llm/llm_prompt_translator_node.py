import time
import uuid

from .llm_common import (
    CaptionParseError,
    DEFAULT_LEMONADE_HOST, DEFAULT_LEMONADE_PORT, FALLBACK_MODEL_LABEL,
    TRANSLATION_SYSTEM_PROMPTS_DIR, FALLBACK_SYSTEM_PROMPT_LABEL, TRANSLATION_OUTPUT_MODES,
    INVALID_PROMPT_FILE_REASON,
    DEFAULT_MAX_RETRIES, MIN_VALID_RESPONSE_CHARS,
    REASON_PARSE_FORMAT, REASON_TIMEOUT,
    fetch_lemonade_models, get_model_context_window, list_system_prompt_files,
    parse_system_prompt_file, build_chat_payload, request_chat_completion,
    extract_response_text, strip_thinking, classify_parse_failure, classify_error,
    resolve_max_retries, ensure_log_dir_at, write_log, write_prompt_log,
    format_duration, format_response_timing, format_response_for_log,
    estimate_prompt_tokens, next_attempt_params, cancel_request, RETRYABLE_EXCEPTIONS,
)

# 翻訳専用のログ出力先。キャプションノードの logs/ と混在させない
LOG_DIR_NAME = "logs_translate"

# 6.1 訂正指示。both モードの PART1/PART2 のような構造要件が無いため、
# 「余計な前置き・説明・引用符を付けずに翻訳結果だけを返す」ことだけを念押しする。
FORMAT_CORRECTION_NOTE = (
    "Note: Your previous response did not look like a clean translation. "
    "Output ONLY the translated prompt text itself — no preamble, no explanation, "
    "no quotation marks, no markdown."
)


def build_translation_messages(system_prompt_text, japanese_prompt, format_correction=False):
    # 5.2相当：画像パートが無いため text のみの user message。
    # fixed_tags はLLMに渡さない（翻訳対象ではないため）＝トークン節約にもなる。
    user_text = japanese_prompt
    if format_correction:
        user_text = f"{user_text}\n{FORMAT_CORRECTION_NOTE}"
    return [
        {"role": "system", "content": system_prompt_text},
        {"role": "user", "content": user_text},
    ]


def parse_translation_response(raw_response, failure_category=REASON_PARSE_FORMAT):
    # PART1/PART2分割・trigger_word処理が不要なぶん、キャプションノードよりパースは単純。
    # thinking除去 → trim → 最短文字数チェックのみ。
    try:
        body = strip_thinking(raw_response).strip()
        if len(body) < MIN_VALID_RESPONSE_CHARS:
            raise CaptionParseError(f"応答が短すぎます ({len(body)}文字): {body!r}")
        return body, []
    except CaptionParseError as e:
        e.category = failure_category
        raise


def combine_final_prompt(fixed_tags, translated):
    # fixed_tags（品質タグ・score系・人数タグ等）を先頭、翻訳結果を後ろに置いて結合する。
    parts = []
    fixed = (fixed_tags or "").strip().rstrip(",").strip()
    if fixed:
        parts.append(fixed)
    translated = (translated or "").strip().rstrip(",").strip()
    if translated:
        parts.append(translated)
    return ", ".join(parts)


class YoshiakiPromptTranslator:
    @classmethod
    def INPUT_TYPES(cls):
        model_list = fetch_lemonade_models(DEFAULT_LEMONADE_HOST, DEFAULT_LEMONADE_PORT)
        if not model_list:
            model_list = [FALLBACK_MODEL_LABEL]

        system_prompt_files = list_system_prompt_files(TRANSLATION_SYSTEM_PROMPTS_DIR)
        if not system_prompt_files:
            system_prompt_files = [FALLBACK_SYSTEM_PROMPT_LABEL]

        return {
            "required": {
                # UI表示順は dict の定義順に対応する。fixed_tags を japanese_prompt より上に置く。
                "fixed_tags": ("STRING", {"multiline": True, "default": "",
                    "tooltip": "翻訳不要の固定タグ(品質タグ・score_1〜3・1girl/solo等)。"
                               "そのまま最終出力の先頭に使われます。"}),
                "japanese_prompt": ("STRING", {"multiline": True, "default": "",
                    "tooltip": "翻訳が必要な日本語本文。"}),
                "system_prompt_file": (system_prompt_files,),
                "lemonade_host": ("STRING", {"default": DEFAULT_LEMONADE_HOST}),
                "lemonade_port": ("INT", {"default": DEFAULT_LEMONADE_PORT, "min": 1, "max": 65535}),
                "lemonade_api_key": ("STRING", {"default": ""}),
                "model": (model_list,),
                "enable_thinking": ("BOOLEAN", {"default": True}),
                "temperature": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 2.0, "step": 0.05}),
                "max_tokens": ("INT", {"default": 2048, "min": 1, "max": 32768}),
                "timeout_sec": ("INT", {"default": 120, "min": 1, "max": 3600}),
                "always_regenerate": ("BOOLEAN", {"default": False}),
                "log_prompt": ("BOOLEAN", {"default": False}),
                "max_retries": ("INT", {
                    "default": DEFAULT_MAX_RETRIES, "min": 1, "max": 10,
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("combined_prompt", "translated_prompt")
    FUNCTION = "translate"
    CATEGORY = "yoshiaki-comfy/LLM"

    @classmethod
    def IS_CHANGED(cls, fixed_tags, japanese_prompt, system_prompt_file, lemonade_host,
                   lemonade_port, lemonade_api_key, model, enable_thinking, temperature,
                   max_tokens, timeout_sec, always_regenerate, log_prompt,
                   max_retries=DEFAULT_MAX_RETRIES):
        if always_regenerate:
            return float("nan")
        return False

    def translate(self, fixed_tags, japanese_prompt, system_prompt_file, lemonade_host,
                  lemonade_port, lemonade_api_key, model, enable_thinking, temperature,
                  max_tokens, timeout_sec, always_regenerate=False, log_prompt=False,
                  max_retries=DEFAULT_MAX_RETRIES):
        run_started = time.monotonic()
        max_retries = resolve_max_retries(max_retries)
        log_dir = ensure_log_dir_at(LOG_DIR_NAME)

        if system_prompt_file == FALLBACK_SYSTEM_PROMPT_LABEL:
            output_mode, system_prompt_text = None, ""
        else:
            output_mode, system_prompt_text = parse_system_prompt_file(
                system_prompt_file, TRANSLATION_OUTPUT_MODES, TRANSLATION_SYSTEM_PROMPTS_DIR
            )

        if output_mode is None:
            print(f"[YoshiakiPromptTranslator] INVALID_PROMPT_FILE: {system_prompt_file}")
            write_log(log_dir,
                      f"INVALID_PROMPT_FILE: {system_prompt_file} reason={INVALID_PROMPT_FILE_REASON}",
                      is_error=True)
            # 4.2：不正なプロンプトファイルのときは fixed_tags があっても両方空文字にする
            return ("", "")

        if not (japanese_prompt or "").strip():
            write_log(log_dir, "SKIPPED: reason=empty_japanese_prompt")
            # 4.2：翻訳対象が無いだけなら fixed_tags のパススルーとして扱う（エラー扱いしない）
            return (combine_final_prompt(fixed_tags, ""), "")

        max_context_window = get_model_context_window(
            lemonade_host, lemonade_port, lemonade_api_key, model
        )

        write_log(log_dir, f"RUN model={model} mode={output_mode} prompt={system_prompt_file}")
        if log_prompt:
            write_prompt_log(log_dir, f"PROMPT system ({system_prompt_file}):", system_prompt_text)

        prompt_tokens = estimate_prompt_tokens(system_prompt_text, japanese_prompt, has_image=False)
        attempt_max_tokens, attempt_temperature = max_tokens, temperature
        previous_reason = None
        translated = ""

        for attempt in range(1, max_retries + 1):
            format_correction = previous_reason == REASON_PARSE_FORMAT
            attempt_max_tokens, attempt_temperature, _clamped = next_attempt_params(
                previous_reason, attempt, attempt_max_tokens, attempt_temperature,
                max_tokens, temperature, max_context_window, prompt_tokens
            )
            messages = build_translation_messages(system_prompt_text, japanese_prompt, format_correction)
            payload = build_chat_payload(model, messages, enable_thinking,
                                         attempt_temperature, attempt_max_tokens)

            if log_prompt:
                write_prompt_log(
                    log_dir,
                    f"PROMPT user (attempt {attempt}/{max_retries}):",
                    build_translation_messages(system_prompt_text, japanese_prompt,
                                               format_correction)[1]["content"],
                )

            request_id = str(uuid.uuid4())
            try:
                request_started = time.monotonic()
                response_payload = request_chat_completion(
                    lemonade_host, lemonade_port, lemonade_api_key, payload, timeout_sec,
                    request_id=request_id
                )
                elapsed = time.monotonic() - request_started
                if log_prompt:
                    timing = format_response_timing(elapsed, response_payload)
                    write_prompt_log(
                        log_dir, f"RESPONSE (attempt {attempt}/{max_retries}, {timing}):",
                        format_response_for_log(response_payload),
                    )
                raw_response = extract_response_text(response_payload)
                failure_category = classify_parse_failure(response_payload, attempt_max_tokens)
                translated, _notes = parse_translation_response(raw_response, failure_category)
                write_log(log_dir, f"SUCCESS attempt={attempt}")
                break
            except RETRYABLE_EXCEPTIONS as e:
                reason = classify_error(e)
                previous_reason = reason
                write_log(log_dir,
                          f"RETRY attempt={attempt}/{max_retries} reason={reason} detail={e}")
                if reason == REASON_TIMEOUT:
                    cancel_request(log_dir, lemonade_host, lemonade_port, lemonade_api_key, request_id)
                if attempt == max_retries:
                    print(f"[YoshiakiPromptTranslator] FAILED: {reason}")
                    write_log(log_dir, f"FAILED reason={reason} ({max_retries} attempts exhausted)",
                              is_error=True)
                    translated = ""

        write_log(log_dir, f"RUN END elapsed={format_duration(time.monotonic() - run_started)}")
        combined = combine_final_prompt(fixed_tags, translated)
        return (combined, translated)


NODE_CLASS_MAPPINGS = {
    "YoshiakiPromptTranslator": YoshiakiPromptTranslator,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "YoshiakiPromptTranslator": "Yoshiaki-PromptTranslator",
}
