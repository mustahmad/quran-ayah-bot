"""
Модуль для работы с Groq AI.
- Whisper large-v3 для распознавания аудио (быстро и бесплатно)
- Llama 3 для умного поиска аятов по смыслу
"""

import os
import json
from groq import Groq

_client = None


def get_client() -> Groq:
    """Получает клиент Groq (lazy init)."""
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY не установлен")
        _client = Groq(api_key=api_key)
    return _client


def transcribe_audio(file_path: str) -> str:
    """
    Транскрибирует аудио/видео через Groq Whisper API.
    Очень быстро — 2-3 секунды вместо минуты.
    """
    client = get_client()

    with open(file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(file_path), audio_file),
            model="whisper-large-v3",
            language="ar",
            response_format="text",
        )

    return transcription.strip() if transcription else ""


def smart_search_ayah(query: str, top_candidates: list) -> dict | None:
    """
    Использует Llama для умного анализа — какой из кандидатов
    лучше всего соответствует запросу пользователя.
    """
    client = get_client()

    candidates_text = ""
    for i, c in enumerate(top_candidates[:5]):
        candidates_text += (
            f"{i+1}. Сура {c['surah']} ({c.get('surah_english', '')}), "
            f"Аят {c['ayah']}: {c['text']}\n"
            f"   Транскрипция: {c.get('transliteration', 'нет')}\n\n"
        )

    prompt = f"""Ты — эксперт по Корану. Пользователь ищет аят по тексту или транскрипции.

Запрос пользователя: "{query}"

Вот кандидаты из базы данных (найдены нечётким поиском):

{candidates_text}

Проанализируй запрос пользователя и кандидатов. Определи:
1. Какой кандидат лучше всего соответствует запросу?
2. Насколько ты уверен (0-100%)?
3. Может быть, запрос соответствует другому аяту, которого нет в списке? Если да — укажи суру и аят.

Ответь СТРОГО в JSON формате:
{{
  "best_match": номер_кандидата_или_0_если_никакой,
  "confidence": число_от_0_до_100,
  "reasoning": "краткое объяснение на русском",
  "alternative_surah": номер_суры_или_null,
  "alternative_ayah": номер_аята_или_null,
  "alternative_text": "текст_аята_или_null"
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты эксперт по Корану. Отвечай ТОЛЬКО валидным JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        result_text = response.choices[0].message.content
        return json.loads(result_text)
    except Exception as e:
        print(f"Ошибка Groq AI: {e}")
        return None
