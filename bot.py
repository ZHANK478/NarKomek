import os
import logging
import httpx
import asyncio
from datetime import time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.ext import JobQueue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
CHANNEL_ID = "@grants_kz_bot"

SYSTEM_PROMPT = """Ты — профессиональный бизнес-консультант в Казахстане. 
Ты помогаешь ТОЛЬКО по следующим темам:
1. Регистрация ИП (индивидуальный предприниматель) в Казахстане
2. Гранты для бизнеса в Казахстане (Даму, Бастау, государственные программы)
3. Составление бизнес-планов по шаблонам

Правила общения:
- Отвечай КОРОТКО — максимум 3-4 предложения за раз
- Веди диалог ПОШАГОВО — задай один вопрос и жди ответа
- Не вываливай всю информацию сразу
- Если вопрос НЕ по этим темам — вежливо объясни специализацию
- Отвечай на русском или казахском языке
- Будь дружелюбным, как живой консультант

Стиль: живой, тёплый, не роботизированный."""

GRANT_SEARCH_PROMPT = """Найди актуальные гранты и программы поддержки бизнеса в Казахстане на сегодня.

Напиши пост для Telegram-канала в таком формате:

🇰🇿 ГРАНТЫ ДЛЯ БИЗНЕСА — [сегодняшняя дата]

Найди 2-3 актуальные программы и для каждой напиши:
💰 Название программы
📋 Кратко что даёт (сумма, условия)
🔗 Куда обращаться (сайт или телефон)

В конце добавь:
💬 Есть вопросы? Пишите нашему консультанту @NarKomek_bot

Пост должен быть живым, полезным, не длиннее 30 строк."""

WELCOME_MESSAGE = """👋 Привет! Я консультант по бизнесу в Казахстане.

Помогу с:
📋 Регистрацией ИП через eGov
💰 Грантами — Даму, Бастау и другие
📊 Бизнес-планом для гранта

Напиши с чего начнём? 👇"""

def get_keyboard():
    buttons = [
        [KeyboardButton("📋 Как открыть ИП?")],
        [KeyboardButton("💰 Какие есть гранты?")],
        [KeyboardButton("📊 Помоги с бизнес-планом")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def ask_openrouter(user_message: str, history: list, system: str = SYSTEM_PROMPT) -> str:
    messages = history + [{"role": "user", "content": user_message}]
    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemini-3.1-flash-lite",
                "messages": [{"role": "system", "content": system}] + messages,
                "max_tokens": 1000,
            }
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]

async def search_and_post_grants(bot):
    """Ищет гранты и публикует в канал"""
    logger.info("Searching for grants...")
    try:
        post_text = await ask_openrouter(
            "Найди актуальные гранты для бизнеса в Казахстане сегодня и напиши пост.",
            [],
            GRANT_SEARCH_PROMPT
        )
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=post_text,
            parse_mode="Markdown"
        )
        logger.info("Grant post published!")
        return post_text
    except Exception as e:
        logger.error(f"Error posting grants: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=get_keyboard()
    )

async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /grant — вручную запустить публикацию"""
    msg = await update.message.reply_text("🔍 Ищу актуальные гранты, подожди минуту...")
    post = await search_and_post_grants(context.bot)
    if post:
        await msg.edit_text(f"✅ Пост опубликован в канале @grants_kz_bot!")
    else:
        await msg.edit_text("😔 Ошибка при публикации, попробуй ещё раз.")

async def daily_grant_job(context):
    """Автоматическая публикация каждое утро"""
    await search_and_post_grants(context.bot)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    history = context.user_data.get("history", [])

    # Пауза для живости
    await asyncio.sleep(2)
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    await asyncio.sleep(2)

    try:
        reply = await ask_openrouter(user_message, history)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})
        context.user_data["history"] = history[-10:]
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("😔 Ошибка, попробуй ещё раз.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text("🔄 Начнём сначала!", reply_markup=get_keyboard())

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Расписание — каждое утро в 9:00 по Астане (UTC+5)
    job_queue = app.job_queue
    job_queue.run_daily(
        daily_grant_job,
        time=time(hour=4, minute=0),  # 4:00 UTC = 9:00 Астана
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("grant", grant_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started with grant agent!")
    app.run_polling()

if __name__ == "__main__":
    main()
