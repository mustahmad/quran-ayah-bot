"""
Модуль для обработки аудио и видео файлов.
Использует Whisper для распознавания арабской речи.
"""

import os
import tempfile
import subprocess
import whisper

_model = None


def get_model():
    """Загружает модель Whisper (lazy loading)."""
    global _model
    if _model is None:
        print("Загрузка модели Whisper...")
        _model = whisper.load_model("base")
        print("Модель Whisper загружена")
    return _model


def extract_audio_from_video(video_path: str) -> str:
    """Извлекает аудио из видео файла с помощью ffmpeg."""
    audio_path = video_path + ".wav"
    subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            audio_path, "-y"
        ],
        capture_output=True,
        check=True,
    )
    return audio_path


def transcribe_audio(file_path: str) -> str:
    """
    Транскрибирует аудио файл в текст на арабском.
    Поддерживает: ogg, mp3, wav, m4a, mp4, avi и др.
    """
    model = get_model()

    # Если это видео — извлекаем аудио
    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.webm'}
    ext = os.path.splitext(file_path)[1].lower()

    audio_path = file_path
    if ext in video_extensions:
        audio_path = extract_audio_from_video(file_path)

    try:
        result = model.transcribe(
            audio_path,
            language="ar",
            task="transcribe",
        )
        return result["text"].strip()
    finally:
        # Очищаем временный аудио файл если извлекали из видео
        if audio_path != file_path and os.path.exists(audio_path):
            os.remove(audio_path)
