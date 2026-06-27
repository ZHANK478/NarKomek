import os
import logging
import httpx
import asyncio
from datetime import time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

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
- Ты НЕ ChatGPT и не GPT. Ты — консультант NarKomek, специалист по бизнесу в Казахстане
- Будь дружелюбным, как живой консультант"""

GRANT_SEARCH_PROMPT = """Напиши пост для Telegram-канала про актуальные гранты и программы поддержки бизнеса в Казахстане.

Формат поста (только текст, без звёздочек и решёток):

ГРАНТЫ ДЛЯ БИЗНЕСА КАЗАХСТАН

Напиши 2-3 актуальные программы. Для каждой:
- Название программы
- Что даёт (сумма, условия)
- Куда обращаться

В конце: Вопросы? Пишите @NarKomek_bot

Пиши простым текстом без markdown форматирования."""

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

async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("🔍 Ищу актуальные гранты, подожди...")
    
    logger.info(f"CHANNEL_ID value: '{CHANNEL_ID}'")
    
    try:
        post_text = await ask_openrouter(
            "Найди актуальные гранты для бизнеса в Казахстане и напиши пост.",
            [],
            GRANT_SEARCH_PROMPT
        )
        logger.info("Got text from OpenRouter, now posting...")
        
        if CHANNEL_ID:
            logger.info(f"Sending to channel: {CHANNEL_ID}")
            try:
                await context.bot.send_message(chat_id=CHANNEL_ID, text=post_text)
                logger.info("SUCCESS: Posted to channel!")
                await update.message.reply_text(f"✅ Пост опубликован в {CHANNEL_ID}!")
            except Exception as channel_error:
                logger.error(f"CHANNEL ERROR: {channel_error}")
                await update.message.reply_text(f"❌ Ошибка публикации в канал: {channel_error}\n\nВот пост:\n\n{post_text}")
        else:
            logger.warning("CHANNEL_ID is empty!")
            await update.message.reply_text(f"⚠️ CHANNEL_ID не настроен!\n\nВот пост:\n\n{post_text}")
            
    except Exception as e:
        logger.error(f"General error: {e}")
        await update.message.reply_text(f"❌ Общая ошибка: {e}")

async def daily_grant_job(context):
    if CHANNEL_ID:
        try:
            post_text = await ask_openrouter(
                "Найди актуальные гранты для бизнеса в Казахстане и напиши пост.",
                [],
                GRANT_SEARCH_PROMPT
            )
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post_text)
            logger.info("Daily grant post published!")
        except Exception as e:
            logger.error(f"Daily job error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text(WELCOME_MESSAGE, reply_markup=get_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    history = context.user_data.get("history", [])
    await asyncio.sleep(2)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await asyncio.sleep(2)
    try:
        reply = await ask_openrouter(user_message, history)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})
        context.user_data["history"] = history[-10:]
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("😔 Ошибка, попробуй ещё раз.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text("🔄 Начнём сначала!", reply_markup=get_keyboard())

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    job_queue = app.job_queue
    job_queue.run_daily(daily_grant_job, time=time(hour=4, minute=0))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("grant", grant_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info(f"Bot started! CHANNEL_ID={CHANNEL_ID}")
    app.run_polling()

if __name__ == "__main__":
    main()
