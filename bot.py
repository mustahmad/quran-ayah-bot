"""
Telegram-бот для поиска аятов Корана.
Принимает текст (арабский/транскрипция) или аудио/видео.
Использует Groq AI (Whisper + Llama) для умного поиска.
Все запросы сохраняются в PostgreSQL.
"""

import os
import tempfile
import logging
import subprocess

from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from quran_data import download_quran_data, search_ayah, SURAH_NAMES_RU
from ai_processor import transcribe_audio, smart_search_ayah
from database import init_db, save_user, save_search, get_user_history, get_stats, close_db

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

quran_data = []

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📋 История поиска"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("❓ Помощь")],
    ],
    resize_keyboard=True,
)


async def track_user(update: Update):
    """Сохраняет информацию о пользователе в БД."""
    user = update.effective_user
    if user:
        await save_user(
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name or "",
            last_name=user.last_name or "",
        )


def format_result(results: list, query: str, ai_analysis: dict = None) -> str:
    """Форматирует результаты поиска. Всегда показывает топ с процентами."""
    if not results:
        return "🔍 Не удалось выполнить поиск. Попробуйте ещё раз."

    lines = []
    best = results[0]
    score = round(best["score"])
    surah_num = best["surah"]
    surah_name_ru = SURAH_NAMES_RU.get(surah_num, best["surah_english"])

    if score >= 90:
        lines.append(f"✅ <b>Похож на {score}%</b>\n")
    elif score >= 70:
        lines.append(f"🔶 <b>Возможное совпадение ({score}%)</b>\n")
    else:
        lines.append(f"🔍 <b>Наиболее похожий результат ({score}%)</b>\n")

    lines.append(f"📖 <b>Сура:</b> {surah_num}. {surah_name_ru}")
    lines.append(f"   <i>{best['surah_name']}</i>")
    lines.append(f"📌 <b>Аят:</b> {best['ayah']}")
    lines.append(f"\n<b>Текст аята:</b>")
    lines.append(f"<blockquote>{best['text']}</blockquote>")

    translit = best.get("transliteration", "")
    if translit:
        lines.append(f"\n<b>Транскрипция:</b>")
        lines.append(f"<i>{translit}</i>")

    if len(results) > 1:
        lines.append("\n━━━━━━━━━━━━━━━━")
        lines.append("📋 <b>Другие варианты:</b>\n")
        for i, r in enumerate(results[1:], 2):
            s_num = r["surah"]
            s_name = SURAH_NAMES_RU.get(s_num, r["surah_english"])
            lines.append(
                f"  {i}. Сура {s_num} ({s_name}), Аят {r['ayah']} "
                f"— <b>{round(r['score'])}%</b>"
            )
            if i <= 3:
                lines.append(f"     <i>{r['text'][:80]}...</i>")

    return "\n".join(lines)


async def do_search(query: str, user_id: int, query_type: str):
    """Выполняет поиск: сначала нечёткий, потом ИИ для уточнения."""
    results = search_ayah(quran_data, query)

    # Если лучший результат < 85% — подключаем ИИ для уточнения
    ai_analysis = None
    best = results[0] if results else None
    if best and best["score"] < 85:
        try:
            ai_analysis = smart_search_ayah(query, results[:5])
            # Если ИИ нашёл лучший вариант — переставляем его на первое место
            if ai_analysis and ai_analysis.get("best_match"):
                idx = ai_analysis["best_match"] - 1
                if 0 <= idx < len(results):
                    confidence = ai_analysis.get("confidence", 0)
                    results[idx]["score"] = max(results[idx]["score"], confidence)
                    # Пересортируем
                    results.sort(key=lambda x: x["score"], reverse=True)
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")

    response = format_result(results, query, ai_analysis)

    # Сохраняем в БД
    best = results[0] if results else None
    await save_search(
        user_id=user_id,
        query_text=query,
        query_type=query_type,
        found_surah=best["surah"] if best else None,
        found_ayah=best["ayah"] if best else None,
        found_surah_name=SURAH_NAMES_RU.get(best["surah"], "") if best else None,
        match_score=best["score"] if best else None,
    )

    return response


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update)
    await update.message.reply_text(
        "🕌 <b>Ассаляму алейкум!</b>\n\n"
        "Я бот для поиска аятов Корана с ИИ. Я помогу найти аят "
        "и определить из какой он суры.\n\n"
        "<b>Что я умею:</b>\n"
        "📝 Напишите <b>текст аята</b> на арабском или транскрипцию\n"
        "🎤 Отправьте <b>голосовое сообщение</b> с чтением аята\n"
        "🎵 Отправьте <b>аудио файл</b> с чтением аята\n"
        "🎬 Отправьте <b>видео</b> с чтением аята\n\n"
        "🤖 Бот использует ИИ для умного поиска — даже если вы "
        "напишете приблизительно, он найдёт нужный аят!\n\n"
        "Просто отправьте мне текст или аудио! 👇",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )


async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📋 История поиска":
        await show_history(update, context)
    elif text == "📊 Статистика":
        await show_stats(update, context)
    elif text == "❓ Помощь":
        await show_help(update, context)
    else:
        await handle_text_search(update, context)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update)
    await update.message.reply_text(
        "📚 <b>Как пользоваться ботом:</b>\n\n"
        "<b>1. Поиск по тексту:</b>\n"
        "Напишите часть аята на арабском или транскрипцию "
        "(на русском или латинице). ИИ поможет найти нужный аят.\n\n"
        "Примеры:\n"
        "• <code>بسم الله الرحمن الرحيم</code>\n"
        "• <code>бисмилляхи ррахмани ррахим</code>\n"
        "• <code>bismillahi rrahmani rrahim</code>\n\n"
        "<b>2. Поиск по аудио/голосовому:</b>\n"
        "Запишите голосовое или отправьте аудио файл — "
        "ИИ распознает речь за 2-3 секунды.\n\n"
        "<b>3. Поиск по видео:</b>\n"
        "Отправьте видео — ИИ извлечёт звук и найдёт аят.\n\n"
        "💡 Чем больше текста, тем точнее результат!",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update)
    user_id = update.effective_user.id
    history = await get_user_history(user_id, limit=10)

    if not history:
        await update.message.reply_text(
            "📋 У вас пока нет истории поиска.\n\n"
            "Отправьте текст или аудио аята, чтобы начать!",
            parse_mode="HTML",
            reply_markup=MAIN_MENU,
        )
        return

    lines = ["📋 <b>Ваша история поиска:</b>\n"]
    for i, h in enumerate(history, 1):
        q_type = {"text": "📝", "voice": "🎤", "audio": "🎵", "video": "🎬"}.get(
            h.get("query_type", ""), "❓"
        )
        if h.get("found_surah"):
            surah_name = h.get("found_surah_name", "")
            lines.append(
                f"{i}. {q_type} → Сура {h['found_surah']} ({surah_name}), "
                f"Аят {h['found_ayah']} ({h.get('match_score', '?')}%)"
            )
        else:
            query = h.get("query_text", "")[:50]
            lines.append(f"{i}. {q_type} «{query}»")

    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=MAIN_MENU
    )


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update)
    stats = await get_stats()

    lines = [
        "📊 <b>Статистика бота:</b>\n",
        f"👥 Пользователей: {stats['total_users']}",
        f"🔍 Всего запросов: {stats['total_searches']}",
    ]

    if stats["top_surahs"]:
        lines.append("\n🏆 <b>Самые искомые суры:</b>")
        for surah_num, surah_name, cnt in stats["top_surahs"]:
            name_ru = SURAH_NAMES_RU.get(surah_num, surah_name or "")
            lines.append(f"  • Сура {surah_num} ({name_ru}) — {cnt} раз")

    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=MAIN_MENU
    )


async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update)
    query = update.message.text.strip()

    if len(query) < 2:
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте больше текста для поиска.",
            parse_mode="HTML",
            reply_markup=MAIN_MENU,
        )
        return

    msg = await update.message.reply_text("🔍 Ищу аят...", parse_mode="HTML")

    response = await do_search(query, update.effective_user.id, "text")
    await msg.edit_text(response, parse_mode="HTML")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update)
    msg = await update.message.reply_text(
        "🎤 Распознаю речь...", parse_mode="HTML",
    )

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

    try:
        text = transcribe_audio(tmp_path)
        if not text:
            await msg.edit_text(
                "❌ Не удалось распознать речь. Попробуйте ещё раз.",
                parse_mode="HTML",
            )
            return

        await msg.edit_text(
            f"📝 Распознано:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        response = await do_search(text, update.effective_user.id, "voice")
        await update.message.reply_text(response, parse_mode="HTML", reply_markup=MAIN_MENU)
    finally:
        os.unlink(tmp_path)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update)
    msg = await update.message.reply_text(
        "🎵 Обрабатываю аудио...", parse_mode="HTML",
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
            await msg.edit_text(
                "❌ Не удалось распознать речь. Попробуйте другой файл.",
                parse_mode="HTML",
            )
            return

        await msg.edit_text(
            f"📝 Распознано:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        response = await do_search(text, update.effective_user.id, "audio")
        await update.message.reply_text(response, parse_mode="HTML", reply_markup=MAIN_MENU)
    finally:
        os.unlink(tmp_path)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update)
    msg = await update.message.reply_text(
        "🎬 Обрабатываю видео...", parse_mode="HTML",
    )

    video = update.message.video or update.message.video_note
    file = await context.bot.get_file(video.file_id)

    # Конвертируем видео в аудио через ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_v:
        video_path = tmp_v.name
        await file.download_to_drive(video_path)

    audio_path = video_path + ".ogg"
    try:
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "libopus",
             "-ar", "16000", "-ac", "1", audio_path, "-y"],
            capture_output=True, check=True,
        )

        text = transcribe_audio(audio_path)
        if not text:
            await msg.edit_text(
                "❌ Не удалось распознать речь из видео.",
                parse_mode="HTML",
            )
            return

        await msg.edit_text(
            f"📝 Распознано:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        response = await do_search(text, update.effective_user.id, "video")
        await update.message.reply_text(response, parse_mode="HTML", reply_markup=MAIN_MENU)
    finally:
        os.unlink(video_path)
        if os.path.exists(audio_path):
            os.unlink(audio_path)


async def post_init(application: Application):
    global quran_data
    await init_db()
    quran_data = await download_quran_data()
    logger.info(f"Загружено {len(quran_data)} аятов Корана")


async def post_shutdown(application: Application):
    await close_db()


MENU_BUTTONS = {"📋 История поиска", "📊 Статистика", "❓ Помощь"}


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Ошибка: установите TELEGRAM_BOT_TOKEN в файле .env")
        return

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text(MENU_BUTTONS), handle_menu_buttons))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))

    print("🕌 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
