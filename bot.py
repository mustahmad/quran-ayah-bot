"""
Telegram-бот для поиска аятов Корана.
Принимает текст (арабский/транскрипция) или аудио/видео,
находит аят и сообщает суру и номер аята.
"""

import os
import tempfile
import logging

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from quran_data import download_quran_data, search_ayah, SURAH_NAMES_RU
from audio_processor import transcribe_audio

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Глобальное хранилище данных Корана
quran_data = []


def format_result(results: list, query: str) -> str:
    """Форматирует результаты поиска в читаемое сообщение."""
    if not results:
        return (
            "❌ К сожалению, не удалось найти подходящий аят.\n\n"
            "Попробуйте:\n"
            "• Ввести больше текста аята\n"
            "• Проверить правильность написания\n"
            "• Отправить аудио с чтением аята"
        )

    lines = []
    best = results[0]

    if best["score"] >= 85:
        surah_num = best["surah"]
        surah_name_ru = SURAH_NAMES_RU.get(surah_num, best["surah_english"])

        lines.append("✅ <b>Аят найден!</b>\n")
        lines.append(f"📖 <b>Сура:</b> {surah_num}. {surah_name_ru}")
        lines.append(f"   <i>{best['surah_name']}</i>")
        lines.append(f"📌 <b>Аят:</b> {best['ayah']}")
        lines.append(f"\n<b>Текст аята:</b>")
        lines.append(f"<blockquote>{best['text']}</blockquote>")
        lines.append(f"\n🔗 <b>Ссылка:</b> Сура {surah_num}, Аят {best['ayah']}")

        if best["score"] < 100:
            lines.append(f"\n⚡ Совпадение: {best['score']}%")

        # Показываем альтернативы если есть
        if len(results) > 1 and results[1]["score"] >= 75:
            lines.append("\n\n━━━━━━━━━━━━━━━━")
            lines.append("📋 <b>Возможные варианты:</b>\n")
            for i, r in enumerate(results[1:], 2):
                if r["score"] >= 75:
                    s_num = r["surah"]
                    s_name = SURAH_NAMES_RU.get(s_num, r["surah_english"])
                    lines.append(
                        f"  {i}. Сура {s_num} ({s_name}), Аят {r['ayah']} "
                        f"— {r['score']}%"
                    )
    else:
        lines.append("🔍 <b>Точного совпадения не найдено.</b>\n")
        lines.append("Наиболее похожие аяты:\n")
        for i, r in enumerate(results, 1):
            s_num = r["surah"]
            s_name = SURAH_NAMES_RU.get(s_num, r["surah_english"])
            lines.append(f"  {i}. Сура {s_num} ({s_name}), Аят {r['ayah']}")
            lines.append(f"     <blockquote>{r['text'][:100]}...</blockquote>")
            lines.append(f"     Совпадение: {r['score']}%\n")

    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    await update.message.reply_text(
        "🕌 <b>Ассаляму алейкум!</b>\n\n"
        "Я бот для поиска аятов Корана. Я могу помочь вам найти аят "
        "и определить из какой он суры.\n\n"
        "<b>Что я умею:</b>\n"
        "📝 Отправьте мне <b>текст аята</b> на арабском — я найду его\n"
        "🎤 Отправьте <b>голосовое сообщение</b> с чтением аята\n"
        "🎵 Отправьте <b>аудио файл</b> с чтением аята\n"
        "🎬 Отправьте <b>видео</b> с чтением аята\n\n"
        "<b>Команды:</b>\n"
        "/start — Показать это сообщение\n"
        "/help — Помощь и советы\n\n"
        "Просто отправьте мне текст или аудио! 👇",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    await update.message.reply_text(
        "📚 <b>Как пользоваться ботом:</b>\n\n"
        "<b>1. Поиск по тексту:</b>\n"
        "Отправьте часть аята на арабском языке. Чем больше текста "
        "вы отправите, тем точнее будет результат.\n\n"
        "Пример: <code>بسم الله الرحمن الرحيم</code>\n\n"
        "<b>2. Поиск по аудио:</b>\n"
        "Запишите голосовое сообщение или отправьте аудио файл "
        "с чтением аята. Бот распознает речь и найдёт аят.\n\n"
        "<b>3. Поиск по видео:</b>\n"
        "Отправьте видео с чтением аята — бот извлечёт аудио "
        "и распознает его.\n\n"
        "💡 <b>Советы:</b>\n"
        "• Старайтесь отправлять хотя бы несколько слов аята\n"
        "• Для аудио — читайте чётко и без фонового шума\n"
        "• Арабский текст даёт наиболее точные результаты",
        parse_mode="HTML",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений."""
    query = update.message.text.strip()

    if len(query) < 2:
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте больше текста для поиска.",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text("🔍 Ищу аят...", parse_mode="HTML")

    results = search_ayah(quran_data, query)
    response = format_result(results, query)
    await update.message.reply_text(response, parse_mode="HTML")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик голосовых сообщений."""
    await update.message.reply_text(
        "🎤 Распознаю речь... Это может занять некоторое время.",
        parse_mode="HTML",
    )

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

    try:
        text = transcribe_audio(tmp_path)
        if not text:
            await update.message.reply_text(
                "❌ Не удалось распознать речь. Попробуйте ещё раз.",
                parse_mode="HTML",
            )
            return

        await update.message.reply_text(
            f"📝 Распознанный текст:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        results = search_ayah(quran_data, text)
        response = format_result(results, text)
        await update.message.reply_text(response, parse_mode="HTML")
    finally:
        os.unlink(tmp_path)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик аудио файлов."""
    await update.message.reply_text(
        "🎵 Обрабатываю аудио... Это может занять некоторое время.",
        parse_mode="HTML",
    )

    audio = update.message.audio or update.message.document
    file = await context.bot.get_file(audio.file_id)

    ext = ".ogg"
    if audio.file_name:
        _, ext = os.path.splitext(audio.file_name)
        if not ext:
            ext = ".ogg"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

    try:
        text = transcribe_audio(tmp_path)
        if not text:
            await update.message.reply_text(
                "❌ Не удалось распознать речь. Попробуйте другой файл.",
                parse_mode="HTML",
            )
            return

        await update.message.reply_text(
            f"📝 Распознанный текст:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        results = search_ayah(quran_data, text)
        response = format_result(results, text)
        await update.message.reply_text(response, parse_mode="HTML")
    finally:
        os.unlink(tmp_path)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик видео файлов."""
    await update.message.reply_text(
        "🎬 Обрабатываю видео... Это может занять некоторое время.",
        parse_mode="HTML",
    )

    video = update.message.video or update.message.video_note
    file = await context.bot.get_file(video.file_id)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

    try:
        text = transcribe_audio(tmp_path)
        if not text:
            await update.message.reply_text(
                "❌ Не удалось распознать речь из видео. Попробуйте другой файл.",
                parse_mode="HTML",
            )
            return

        await update.message.reply_text(
            f"📝 Распознанный текст:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        results = search_ayah(quran_data, text)
        response = format_result(results, text)
        await update.message.reply_text(response, parse_mode="HTML")
    finally:
        os.unlink(tmp_path)


async def post_init(application: Application):
    """Загружает данные Корана при запуске бота."""
    global quran_data
    quran_data = await download_quran_data()
    logger.info(f"Загружено {len(quran_data)} аятов Корана")


def main():
    """Запуск бота."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Ошибка: установите TELEGRAM_BOT_TOKEN в файле .env")
        print("1. Создайте бота через @BotFather в Telegram")
        print("2. Скопируйте токен")
        print("3. Создайте файл .env и добавьте: TELEGRAM_BOT_TOKEN=ваш_токен")
        return

    app = Application.builder().token(token).post_init(post_init).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Голосовые сообщения
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Аудио файлы
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))

    # Видео
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.VIDEO_NOTE,
        handle_video,
    ))

    print("🕌 Бот запущен! Нажмите Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
