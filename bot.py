import os
import logging
import httpx
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]

SYSTEM_PROMPT = """Ты — профессиональный бизнес-консультант в Казахстане. 
Ты помогаешь ТОЛЬКО по следующим темам:
1. Регистрация ИП (индивидуальный предприниматель) в Казахстане
2. Гранты для бизнеса в Казахстане (Даму, Бастау, государственные программы)
3. Составление бизнес-планов по шаблонам

Правила:
- Если вопрос НЕ по этим темам — вежливо объясни, что ты специализируешься только на ИП, грантах и бизнес-планах
- Отвечай на русском языке (или казахском, если пишут на казахском)
- Давай конкретные, практичные советы
- Ссылайся на актуальные казахстанские программы и порталы (egov.kz, damu.kz)
- Будь дружелюбным и поддерживающим

Примеры тем которые ты знаешь:
- Как открыть ИП через eGov
- Какие налоги платит ИП (упрощёнка, патент)
- Программа "Бастау Бизнес"
- Гранты Даму до 3 млн тенге
- Как написать бизнес-план для гранта
- Структура бизнес-плана"""

WELCOME_MESSAGE = """👋 Привет! Я твой консультант по бизнесу в Казахстане.

Я помогу тебе с:
📋 *Регистрацией ИП* — пошагово через eGov
💰 *Грантами* — Даму, Бастау и другие программы  
📊 *Бизнес-планами* — по шаблонам для грантов

Просто напиши свой вопрос или выбери тему ниже 👇"""

def get_keyboard():
    buttons = [
        [KeyboardButton("📋 Как открыть ИП?")],
        [KeyboardButton("💰 Какие есть гранты?")],
        [KeyboardButton("📊 Помоги с бизнес-планом")],
        [KeyboardButton("❓ Задать свой вопрос")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def ask_openrouter(user_message: str, history: list) -> str:
    messages = history + [{"role": "user", "content": user_message}]
    
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemini-3.1-flash-lite",
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                "max_tokens": 1000,
            }
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    history = context.user_data.get("history", [])
    
    # Показываем что бот думает
    thinking = await update.message.reply_text("⏳ Думаю...")
    
    try:
        reply = await ask_openrouter(user_message, history)
        
        # Сохраняем историю (последние 10 сообщений)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})
        context.user_data["history"] = history[-10:]
        
        await thinking.edit_text(reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        await thinking.edit_text("😔 Произошла ошибка. Попробуй ещё раз.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text("🔄 История очищена. Начнём сначала!", reply_markup=get_keyboard())

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
