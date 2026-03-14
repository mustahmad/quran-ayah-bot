"""
Telegram-бот для поиска аятов Корана.
Принимает текст (арабский/транскрипция) или аудио/видео,
находит аят и сообщает суру и номер аята.
Все запросы сохраняются в PostgreSQL.
Интерфейс на кнопках.
"""

import os
import tempfile
import logging

from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from quran_data import download_quran_data, search_ayah, SURAH_NAMES_RU
from audio_processor import transcribe_audio
from database import init_db, save_user, save_search, get_user_history, get_stats, close_db

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

quran_data = []

# Главное меню — reply-кнопки
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


def format_result(results: list, query: str) -> str:
    """Форматирует результаты поиска."""
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
    """Обработчик команды /start и приветствие."""
    await track_user(update)
    await update.message.reply_text(
        "🕌 <b>Ассаляму алейкум!</b>\n\n"
        "Я бот для поиска аятов Корана. Я помогу вам найти аят "
        "и определить из какой он суры.\n\n"
        "<b>Что я умею:</b>\n"
        "📝 Отправьте <b>текст аята</b> на арабском — я найду его\n"
        "🎤 Отправьте <b>голосовое сообщение</b> с чтением аята\n"
        "🎵 Отправьте <b>аудио файл</b> с чтением аята\n"
        "🎬 Отправьте <b>видео</b> с чтением аята\n\n"
        "Просто отправьте мне текст или аудио! 👇",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )


async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки меню."""
    text = update.message.text

    if text == "📋 История поиска":
        await show_history(update, context)
    elif text == "📊 Статистика":
        await show_stats(update, context)
    elif text == "❓ Помощь":
        await show_help(update, context)
    else:
        # Это обычный текстовый запрос — ищем аят
        await handle_text_search(update, context)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает помощь."""
    await track_user(update)
    await update.message.reply_text(
        "📚 <b>Как пользоваться ботом:</b>\n\n"
        "<b>1. Поиск по тексту:</b>\n"
        "Просто напишите часть аята на арабском языке. "
        "Чем больше текста, тем точнее результат.\n\n"
        "Пример: <code>بسم الله الرحمن الرحيم</code>\n\n"
        "<b>2. Поиск по аудио:</b>\n"
        "Запишите голосовое сообщение или отправьте аудио файл "
        "с чтением аята.\n\n"
        "<b>3. Поиск по видео:</b>\n"
        "Отправьте видео с чтением аята — бот извлечёт аудио "
        "и распознает его.\n\n"
        "💡 <b>Советы:</b>\n"
        "• Отправляйте хотя бы несколько слов аята\n"
        "• Для аудио — читайте чётко и без шума\n"
        "• Арабский текст даёт самые точные результаты",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает историю поиска."""
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
        query = h.get("query_text", "")[:50]
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
            lines.append(f"{i}. {q_type} «{query}» — не найдено")

    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=MAIN_MENU
    )


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику бота."""
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
    """Поиск аята по тексту."""
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

    results = search_ayah(quran_data, query)
    response = format_result(results, query)

    best = results[0] if results else None
    await save_search(
        user_id=update.effective_user.id,
        query_text=query,
        query_type="text",
        found_surah=best["surah"] if best else None,
        found_ayah=best["ayah"] if best else None,
        found_surah_name=SURAH_NAMES_RU.get(best["surah"], "") if best else None,
        match_score=best["score"] if best else None,
    )

    await msg.edit_text(response, parse_mode="HTML")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик голосовых сообщений."""
    await track_user(update)
    msg = await update.message.reply_text(
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
            await msg.edit_text(
                "❌ Не удалось распознать речь. Попробуйте ещё раз.",
                parse_mode="HTML",
            )
            return

        await msg.edit_text(
            f"📝 Распознанный текст:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        results = search_ayah(quran_data, text)
        response = format_result(results, text)

        best = results[0] if results else None
        await save_search(
            user_id=update.effective_user.id,
            query_text=text,
            query_type="voice",
            found_surah=best["surah"] if best else None,
            found_ayah=best["ayah"] if best else None,
            found_surah_name=SURAH_NAMES_RU.get(best["surah"], "") if best else None,
            match_score=best["score"] if best else None,
        )

        await update.message.reply_text(response, parse_mode="HTML", reply_markup=MAIN_MENU)
    finally:
        os.unlink(tmp_path)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик аудио файлов."""
    await track_user(update)
    msg = await update.message.reply_text(
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
            await msg.edit_text(
                "❌ Не удалось распознать речь. Попробуйте другой файл.",
                parse_mode="HTML",
            )
            return

        await msg.edit_text(
            f"📝 Распознанный текст:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        results = search_ayah(quran_data, text)
        response = format_result(results, text)

        best = results[0] if results else None
        await save_search(
            user_id=update.effective_user.id,
            query_text=text,
            query_type="audio",
            found_surah=best["surah"] if best else None,
            found_ayah=best["ayah"] if best else None,
            found_surah_name=SURAH_NAMES_RU.get(best["surah"], "") if best else None,
            match_score=best["score"] if best else None,
        )

        await update.message.reply_text(response, parse_mode="HTML", reply_markup=MAIN_MENU)
    finally:
        os.unlink(tmp_path)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик видео файлов."""
    await track_user(update)
    msg = await update.message.reply_text(
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
            await msg.edit_text(
                "❌ Не удалось распознать речь из видео. Попробуйте другой файл.",
                parse_mode="HTML",
            )
            return

        await msg.edit_text(
            f"📝 Распознанный текст:\n<blockquote>{text}</blockquote>\n\n🔍 Ищу аят...",
            parse_mode="HTML",
        )

        results = search_ayah(quran_data, text)
        response = format_result(results, text)

        best = results[0] if results else None
        await save_search(
            user_id=update.effective_user.id,
            query_text=text,
            query_type="video",
            found_surah=best["surah"] if best else None,
            found_ayah=best["ayah"] if best else None,
            found_surah_name=SURAH_NAMES_RU.get(best["surah"], "") if best else None,
            match_score=best["score"] if best else None,
        )

        await update.message.reply_text(response, parse_mode="HTML", reply_markup=MAIN_MENU)
    finally:
        os.unlink(tmp_path)


async def post_init(application: Application):
    """Загружает данные Корана и инициализирует БД при запуске."""
    global quran_data
    await init_db()
    quran_data = await download_quran_data()
    logger.info(f"Загружено {len(quran_data)} аятов Корана")


async def post_shutdown(application: Application):
    """Закрывает соединения при остановке."""
    await close_db()


# Тексты кнопок для фильтрации
MENU_BUTTONS = {"📋 История поиска", "📊 Статистика", "❓ Помощь"}


def main():
    """Запуск бота."""
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

    # /start
    app.add_handler(CommandHandler("start", start))

    # Кнопки меню (фильтруем по тексту кнопок)
    app.add_handler(MessageHandler(
        filters.Text(MENU_BUTTONS),
        handle_menu_buttons,
    ))

    # Голосовые
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Аудио
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))

    # Видео
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))

    # Обычный текст — поиск аята (должен быть последним)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))

    print("🕌 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
