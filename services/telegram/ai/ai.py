"""
AI integration for the Telegram bot (Now using OpenAI only)
"""
import logging
import json
from typing import Optional, Dict, List
from config import Environ 
import os
import openai
import asyncio  
import re  
import random     
import base64  

from .ai_prompts import ANALYZE_IMAGE_SYSTEM_PROMPT_TEMPLATE, GET_ERROR_CODE_SUGGESTION_SYSTEM_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

# --- Константы для повторных запросов ---
MAX_API_RETRIES_PER_STAGE = 2 # Макс. попыток для каждого ОТДЕЛЬНОГО вызова API OpenAI
USER_REQUESTED_OVERALL_PASSES = 2 # Количество полных проходов анализа (будет использовано позже)
DEFAULT_RETRY_WAIT_SECONDS = 20
TIMEOUT_RETRY_WAIT_SECONDS = 5

async def _make_openai_api_call(client: openai.AsyncOpenAI, model_name: str, messages: List[Dict[str, any]],
                                response_format_type: Optional[str] = None, temperature: float = 0.0,
                                timeout: int = 60, call_description: str = "OpenAI API call") -> tuple[Optional[str], Optional[Dict[str, any]]]:
    """
    Вспомогательная функция для вызова OpenAI API с внутренними повторами при ошибках.
    Возвращает (content, error_dict). Если успешно, content - строка, error_dict - None.
    Если ошибка, content - None, error_dict содержит детали ошибки.
    """
    last_exception = None
    for attempt in range(MAX_API_RETRIES_PER_STAGE + 1):
        try:
            logger.info(f"{call_description}, Попытка {attempt + 1}/{MAX_API_RETRIES_PER_STAGE + 1}")
            common_params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "timeout": timeout
            }
            if response_format_type:
                common_params["response_format"] = {"type": response_format_type}

            response = await client.chat.completions.create(**common_params)

            if not response.choices or not response.choices[0].message or response.choices[0].message.content is None:
                error_message = f"Ответ {call_description} не содержит ожидаемого поля content или оно равно None."
                logger.error(error_message)
                if attempt < MAX_API_RETRIES_PER_STAGE:
                    last_exception = ValueError(error_message)
                    wait_time = TIMEOUT_RETRY_WAIT_SECONDS * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Отсутствует content в ответе {call_description}. Ожидание {wait_time:.2f} сек.")
                    await asyncio.sleep(wait_time)
                    continue
                else: # All retries for no content exhausted
                    return None, {"error": "NO_CONTENT_IN_RESPONSE", "description": error_message}
            
            return response.choices[0].message.content.strip(), None # content, no error_dict

        except openai.RateLimitError as e:
            last_exception = e
            logger.warning(f"OpenAI RateLimitError ({call_description}, Попытка {attempt + 1}): {e}")
            if attempt < MAX_API_RETRIES_PER_STAGE:
                wait_time_rl = DEFAULT_RETRY_WAIT_SECONDS
                try: # Try to extract wait time from error
                    match_s = re.search(r"Please try again in (\\\\d+\\\\.?\\\\d*)s", str(e)) # Pattern for seconds
                    match_ms = re.search(r"Please try again in (\\\\d+\\\\.?\\\\d*)ms", str(e)) # Pattern for milliseconds
                    
                    if match_s:
                        wait_time_rl = float(match_s.group(1)) + random.uniform(0, 1)
                    elif match_ms:
                        wait_time_rl = float(match_ms.group(1)) / 1000.0 + random.uniform(0, 1)
                    else: # Fallback for minutes if other patterns fail
                        match_min = re.search(r"Please try again in (\\\\d+\\\\.?\\\\d*)m", str(e)) # Pattern for minutes
                        if match_min:
                             wait_time_rl = float(match_min.group(1)) * 60 + random.uniform(0, 1)
                except Exception as parse_ex:
                    logger.error(f"Ошибка извлечения времени ожидания из RateLimitError: {parse_ex}")
                logger.info(f"RateLimitError ({call_description}). Ожидание {wait_time_rl:.2f} сек.")
                await asyncio.sleep(wait_time_rl)
            else: # All retries for RateLimitError exhausted
                logger.error(f"Превышено макс. попыток ({MAX_API_RETRIES_PER_STAGE + 1}) для RateLimitError ({call_description}).")
                return None, {"error": "RATE_LIMIT_EXHAUSTED", "description": str(e)}
        
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            last_exception = e
            error_type_name = type(e).__name__
            logger.warning(f"OpenAI {error_type_name} ({call_description}, Попытка {attempt + 1}): {e}")
            if attempt < MAX_API_RETRIES_PER_STAGE:
                wait_time_to = TIMEOUT_RETRY_WAIT_SECONDS * (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"{error_type_name} ({call_description}). Ожидание {wait_time_to:.2f} сек.")
                await asyncio.sleep(wait_time_to)
            else: # All retries for Timeout/ConnectionError exhausted
                logger.error(f"Превышено макс. попыток ({MAX_API_RETRIES_PER_STAGE + 1}) для {error_type_name} ({call_description}).")
                return None, {"error": "TIMEOUT_OR_CONNECTION_EXHAUSTED", "description": str(e)}

        except openai.APIStatusError as e:
            last_exception = e
            logger.error(f"OpenAI Ошибка статуса API ({call_description}, status={e.status_code}): {e.message}", exc_info=False)
            if 400 <= e.status_code < 500 and e.status_code != 429: # Non-retryable client errors
                return None, {"error": "API_CLIENT_ERROR", "status_code": e.status_code, "description": e.message}
            if attempt < MAX_API_RETRIES_PER_STAGE:
                wait_time_se = TIMEOUT_RETRY_WAIT_SECONDS * (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"APIStatusError ({call_description}). Ожидание {wait_time_se:.2f} сек.")
                await asyncio.sleep(wait_time_se)
            else: # All retries for this type of APIStatusError exhausted
                logger.error(f"Превышено макс. попыток ({MAX_API_RETRIES_PER_STAGE + 1}) для APIStatusError ({call_description}).")
                return None, {"error": "API_STATUS_ERROR_EXHAUSTED", "description": e.message}
        
        except Exception as e:
            last_exception = e
            logger.error(f"Непредвиденная ошибка при вызове OpenAI API ({call_description}, попытка {attempt + 1}): {e}", exc_info=True)
            if attempt == MAX_API_RETRIES_PER_STAGE:
                 return None, {"error": "UNEXPECTED_API_ERROR_LAST_ATTEMPT", "description": str(e)}
            await asyncio.sleep(TIMEOUT_RETRY_WAIT_SECONDS * (2**attempt) + random.uniform(0,1))

    final_error_msg = f"Не удалось получить успешный ответ от OpenAI ({call_description}) после {MAX_API_RETRIES_PER_STAGE + 1} попыток."
    logger.error(f"{final_error_msg} Последняя зафиксированная ошибка: {last_exception}")
    error_key_final = "ALL_API_ATTEMPTS_FAILED_IN_HELPER"
    if isinstance(last_exception, openai.RateLimitError): error_key_final = "RATE_LIMIT_EXHAUSTED"
    elif isinstance(last_exception, (openai.APITimeoutError, openai.APIConnectionError)): error_key_final = "TIMEOUT_OR_CONNECTION_EXHAUSTED"
    elif isinstance(last_exception, openai.APIStatusError): error_key_final = "API_STATUS_ERROR_EXHAUSTED"
    elif isinstance(last_exception, ValueError) and "не содержит ожидаемого поля content" in str(last_exception): error_key_final = "NO_CONTENT_IN_RESPONSE"
    
    return None, {"error": error_key_final, "description": final_error_msg, "last_exception_type": str(type(last_exception)), "last_exception_message": str(last_exception)}

async def _do_one_full_analysis_pass(client, base64_image, known_error_codes, system_prompt_image_json, user_content_image_json, pass_num: int):
    """Выполняет один полный проход анализа: Image-to-JSON, затем OCR fallback если нужно."""
    logger.info(f"Начало полного прохода анализа #{pass_num}")
    
    # Этап 1: Image-to-JSON
    ai_response_raw, error_dict = await _make_openai_api_call(
        client, "gpt-4o", 
        messages=[{"role": "system", "content": system_prompt_image_json}, {"role": "user", "content": user_content_image_json}],
        response_format_type="json_object", timeout=90,
        call_description=f"Image-to-JSON (Pass {pass_num})"
    )

    if error_dict:
        logger.error(f"Ошибка на этапе Image-to-JSON (Проход {pass_num}): {error_dict}")
        return None, error_dict # Возвращаем ошибку, чтобы внешний цикл мог решить, продолжать ли

    current_ai_result = None
    try:
        current_ai_result = json.loads(ai_response_raw)
        required_keys = {"product", "os_version", "timestamp", "error_code", "crash_reporter_key", "panic_string"}
        if not all(key in current_ai_result for key in required_keys):
            logger.error(f"Ответ OpenAI JSON (Проход {pass_num}) не содержит всех нужных ключей: {current_ai_result}")
            return None, {"error": "MISSING_JSON_KEYS", "description": "JSON from AI miss some keys"}
    except json.JSONDecodeError as e:
        logger.error(f"Не удалось распарсить JSON ответ от OpenAI (Проход {pass_num}): {e}. Ответ: {ai_response_raw}")
        return None, {"error": "JSON_DECODE_ERROR", "description": str(e)}

    logger.info(f"Image-to-JSON (Проход {pass_num}) успешно вернул JSON: {current_ai_result}")

    # Этап 2: OCR Fallback, если необходимо
    product_found = current_ai_result.get("product") is not None
    crash_key_found = current_ai_result.get("crash_reporter_key") is not None
    initial_error_code = current_ai_result.get("error_code")

    if product_found and crash_key_found and initial_error_code is None:
        logger.info(f"Image-to-JSON (Проход {pass_num}) не нашел error_code, запускаю OCR fallback.")
        
        # Обновленный, более нейтральный промпт для OCR, чтобы избежать отказов AI
        text_extraction_system_prompt = "Твоя задача — вытащить весь видимый текст из предоставленного изображения после panic_string до слово slide если видишь. Верни только текст без какого-либо анализа или комментариев."
        
        extracted_text_raw, text_error_dict = await _make_openai_api_call(
            client, "gpt-4o",
            messages=[{"role": "system", "content": text_extraction_system_prompt}, 
                      {"role": "user", "content": user_content_image_json}], 
            timeout=60,
            call_description=f"Text Extraction OCR (Pass {pass_num})"
        )

        if text_error_dict:
            logger.warning(f"Ошибка при извлечении текста OCR (Проход {pass_num}): {text_error_dict}. Продолжаем без OCR.")
        elif not extracted_text_raw or extracted_text_raw.lower().startswith(("i'm sorry", "i am sorry", "i cannot", "i can't assist", "as an ai", "sorry,")) or len(extracted_text_raw) < 25:
            logger.warning(f"OCR (Проход {pass_num}) вернул бесполезный текст: '{extracted_text_raw[:100]}...'. Пропускаем анализ этого текста.")
        else:
            logger.info(f"OCR (Проход {pass_num}) извлек текст (первые 500 симв): {extracted_text_raw[:500]}...")
            suggested_error_code_ocr = await get_ai_error_code_suggestion(client, extracted_text_raw, known_error_codes)
            if suggested_error_code_ocr:
                logger.info(f"OCR fallback (Проход {pass_num}) нашел error_code: {suggested_error_code_ocr}. Обновляем результат.")
                current_ai_result["error_code"] = suggested_error_code_ocr
                if current_ai_result.get("panic_string") != suggested_error_code_ocr:
                    current_ai_result["panic_string"] = suggested_error_code_ocr
            else:
                logger.info(f"OCR fallback (Проход {pass_num}) не смог определить error_code из извлеченного текста.")
    
    return current_ai_result, None # Результат этого прохода, нет ошибки

async def analyze_image_via_ai(
        image_path: str,
        known_error_codes: List[str]
) -> Optional[Dict[str, Optional[str]]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY не найден для analyze_image_via_ai.")
        return None

    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Ошибка чтения или кодирования изображения {image_path}: {e}", exc_info=True)
        return None

    codes_list_str = "\n".join([f"- `{code}`" for code in known_error_codes])
    system_prompt_image_json = ANALYZE_IMAGE_SYSTEM_PROMPT_TEMPLATE.format(known_error_codes_list_str=codes_list_str)
    user_content_image_json = [
        {"type": "text", "text": "Проанализируй текст на этом изображении лога сбоя iOS и верни ТОЛЬКО JSON с требуемой информацией, следуя СТРОГИМ правилам форматирования."},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
    ]
    client = openai.AsyncOpenAI(api_key=api_key)
    
    final_result_from_passes = None
    last_error_dict = None

    for pass_idx in range(USER_REQUESTED_OVERALL_PASSES):
        current_pass_result, error_dict_from_pass = await _do_one_full_analysis_pass(
            client, base64_image, known_error_codes, 
            system_prompt_image_json, user_content_image_json, 
            pass_num=pass_idx + 1
        )
        
        if error_dict_from_pass:
            last_error_dict = error_dict_from_pass
            if error_dict_from_pass.get("error") in ["RATE_LIMIT_EXHAUSTED", "TIMEOUT_OR_CONNECTION_EXHAUSTED", "API_CLIENT_ERROR"]:
                logger.error(f"Критическая ошибка API на проходе {pass_idx + 1}: {error_dict_from_pass}. Прерывание.")
                return {"error": error_dict_from_pass.get("error"), "description": error_dict_from_pass.get("description")}

        if current_pass_result:
            final_result_from_passes = current_pass_result
            if current_pass_result.get("error_code"):
                logger.info(f"Код ошибки '{current_pass_result['error_code']}' найден на проходе {pass_idx + 1}. Завершаем анализ.")
                break 
        
        if pass_idx < USER_REQUESTED_OVERALL_PASSES - 1 and not (current_pass_result and current_pass_result.get("error_code")):
            logger.info(f"Код ошибки не найден на проходе {pass_idx + 1}. Переход к следующему полному проходу.")
        elif not (current_pass_result and current_pass_result.get("error_code")):
             logger.warning(f"Код ошибки не найден после {USER_REQUESTED_OVERALL_PASSES} полных проходов.")

    if not final_result_from_passes:
        logger.error(f"Анализ изображения не дал результата после {USER_REQUESTED_OVERALL_PASSES} проходов. Последняя ошибка: {last_error_dict}")
        if last_error_dict:
            return {"error": last_error_dict.get("error", "UNKNOWN_FAILURE_ALL_PASSES"), "description": last_error_dict.get("description")}
        return None

    # Финальная обработка найденного результата
    current_ai_error_code = final_result_from_passes.get("error_code")
    if current_ai_error_code:
        found_known_code = False
        for known_code in known_error_codes:
            if isinstance(current_ai_error_code, str) and known_code.lower() == current_ai_error_code.lower():
                final_result_from_passes["error_code"] = known_code
                if final_result_from_passes.get("panic_string") != known_code:
                    final_result_from_passes["panic_string"] = known_code
                found_known_code = True
                break
        if not found_known_code:
            logger.warning(f"Код ошибки '{current_ai_error_code}' от AI (финальный) не найден в списке известных! Заменяется на null.")
            final_result_from_passes["error_code"] = None
            final_result_from_passes["panic_string"] = None
    else:  # error_code is None
        if final_result_from_passes.get("panic_string") is not None:
            logger.info("Финальный error_code is null, устанавливаем panic_string в null.")
            final_result_from_passes["panic_string"] = None
            
    return final_result_from_passes

async def get_ai_error_code_suggestion(
        client: openai.AsyncOpenAI,
        error_text: str,
        known_error_codes: List[str],
) -> Optional[str]:
    """
    Определяет наиболее подходящий error_code из списка known_error_codes
    на основе предоставленного error_text с помощью OpenAI (GPT-4o), используя _make_openai_api_call.
    """
    if not error_text or not known_error_codes:
        logger.warning("Пустой error_text или known_error_codes передан в get_ai_error_code_suggestion.")
        return None

    codes_list_str = "\n".join([f"- `{code}`" for code in known_error_codes])
    system_prompt = GET_ERROR_CODE_SUGGESTION_SYSTEM_PROMPT_TEMPLATE.format(known_error_codes_list_str=codes_list_str)
    user_prompt = f"{error_text}\n\nВыбери ОДИН код из списка выше или напиши null:"

    ai_response_raw, error_dict = await _make_openai_api_call(
        client, "gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        call_description="Error Code Suggestion from Text"
    )

    if error_dict:
        logger.error(f"Ошибка при запросе error_code suggestion: {error_dict}")
        return None
    
    if not ai_response_raw:
        logger.error("Получен пустой контент от _make_openai_api_call для error code suggestion (неожиданно).")
        return None

    logger.info(f"Ответ от OpenAI (raw text for error code suggestion): {ai_response_raw}")

    if ai_response_raw.lower() == "null":
        logger.info("AI вернул 'null', подходящий код ошибки не найден (text analysis).")
        return None
    
    for known_code in known_error_codes:
        if known_code == ai_response_raw:
            logger.info(f"AI выбрал подходящий код ошибки (точное совпадение): {known_code}")
            return known_code
        if known_code.lower() == ai_response_raw.lower():
            logger.info(f"AI выбрал код (без учета регистра): {known_code} (ответ AI: {ai_response_raw})")
            return known_code

    logger.warning(f"Ответ AI '{ai_response_raw}' (для кода ошибки из текста) не 'null' и не найден в списке известных. Совпадений нет.")
    return None
