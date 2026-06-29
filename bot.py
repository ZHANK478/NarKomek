import os
import logging
import httpx
import xml.etree.ElementTree as ET
from datetime import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@armykz_news")

FACTS = [
    "Срочная служба в Казахстане длится 12 месяцев. Альтернативная гражданская служба — 18 месяцев.",
    "Призывной возраст в РК: от 18 до 27 лет. Если вам уже 27 — вы зачисляетесь в запас.",
    "Весенний призыв в Казахстане проходит с апреля по июнь, осенний — с октября по декабрь.",
    "Категория А — годен без ограничений. Категория Д — полностью освобождён от службы.",
    "Студенты очной формы обучения имеют право на отсрочку от призыва. Нужна справка из вуза.",
    "Категория Г означает временную негодность. Даётся отсрочка на 6-12 месяцев для лечения.",
    "Единственный кормилец семьи имеет право на отсрочку от призыва при наличии документов.",
    "Проверить статус повестки можно на портале eGov.kz в разделе воинского учёта.",
    "Категория В — ограниченно годен. В мирное время не призывается, зачисляется в запас.",
    "Альтернативная служба доступна по убеждениям или вероисповеданию. Срок — 18 месяцев.",
]

fact_index = 0

SYSTEM_PROMPT = """Ты — армейский ИИ-помощник для граждан Казахстана.
Помогаешь призывникам и их родителям разобраться в вопросах воинской службы.

Темы:
1. Категории годности (А, Б, В, Г, Д)
2. Документы для призыва и медкомиссии
3. Сроки службы и отсрочки
4. Куда обращаться
5. Альтернативная служба

Правила:
- Отвечай на русском языке
- Ты ИИ — если спросят, честно скажи об этом
- НЕ указывай mil.gov.kz — сайт не работает. Направляй на egov.kz
- В конце каждого ответа пиши: "⚠️ Информация справочная. Уточняйте на egov.kz или в местном Управлении по делам обороны"
- Не давай юридических гарантий
- Отвечай коротко и по делу

Категории годности:
- А — годен (без ограничений)
- Б — годен с незначительными ограничениями
- В — ограниченно годен (запас, не призывается в мирное время)
- Г — временно не годен (отсрочка 6-12 месяцев)
- Д — не годен (освобождение)

Сроки: срочная — 12 мес, альтернативная — 18 мес, возраст 18-27 лет.
Призывы: весна (апрель-июнь), осень (октябрь-декабрь).
Отсрочки: студенты очной формы, единственный кормилец, категория Г, уход за больным родственником."""


async def ask_gemini(user_message: str) -> str:
    async with httpx.AsyncClient(timeout=40) as client:
        try:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "google/gemini-3.1-flash-lite",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 1000,
                }
            )
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return "Извините, произошла техническая ошибка. Попробуйте позже или обратитесь на egov.kz"


async def fetch_army_news() -> tuple:
    """Берём свежую новость об армии РК из RSS"""
    rss_urls = [
        "https://www.inform.kz/rss/",
        "https://www.zakon.kz/rss/",
    ]
    keywords = ["армия", "призыв", "минобороны", "военн", "срочник", "отсрочк"]

    async with httpx.AsyncClient(timeout=15) as client:
        for rss_url in rss_urls:
            try:
                r = await client.get(rss_url)
                root = ET.fromstring(r.content)
                for item in root.findall(".//item"):
                    title = item.findtext("title", "").lower()
                    desc = item.findtext("description", "").lower()
                    link = item.findtext("link", "")
                    orig_title = item.findtext("title", "")
                    if any(kw in title or kw in desc for kw in keywords):
                        return orig_title, link
            except Exception as e:
                logger.error(f"RSS error {rss_url}: {e}")
                continue

    return None, None


# ───────────────────────────────────────────
# АВТОПОСТИНГ
# ───────────────────────────────────────────

async def morning_post(context):
    """10:00 Астана (05:00 UTC) — новость дня"""
    global fact_index
    title, link = await fetch_army_news()

    if title and link:
        prompt = f"Напиши краткий пост (2-3 предложения) для Telegram канала об армии Казахстана на основе заголовка: '{title}'. Нейтральный тон, без хэштегов."
        summary = await ask_gemini(prompt)
        text = f"📰 *Новость дня*\n\n{summary}\n\n🔗 [Читать полностью]({link})\n\n👉 Вопросы? @armyKZZ\\_bot"
    else:
        fact = FACTS[fact_index % len(FACTS)]
        fact_index += 1
        text = f"💡 *Факт дня*\n\n{fact}\n\n👉 Вопросы? @armyKZZ\\_bot"

    # Публикуем в канал
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
        logger.info("Утренний пост опубликован!")
    except Exception as e:
        logger.error(f"Ошибка публикации в канал: {e}")

    # Уведомляем админа
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"✅ Утренний пост опубликован\n\n{text[:300]}")
        except Exception as e:
            logger.error(f"Ошибка уведомления админа: {e}")


async def evening_post(context):
    """19:00 Астана (14:00 UTC) — факт дня"""
    global fact_index
    fact = FACTS[fact_index % len(FACTS)]
    fact_index += 1
    text = f"💡 *Факт дня*\n\n{fact}\n\n👉 Остались вопросы? @armyKZZ\\_bot"

    # Публикуем в канал
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
        logger.info("Вечерний пост опубликован!")
    except Exception as e:
        logger.error(f"Ошибка публикации в канал: {e}")

    # Уведомляем админа
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"✅ Вечерний пост опубликован\n\n{text[:300]}")
        except Exception as e:
            logger.error(f"Ошибка уведомления админа: {e}")


# ───────────────────────────────────────────
# КОМАНДЫ
# ───────────────────────────────────────────

async def manual_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /post — только для админа"""
    if str(update.message.from_user.id) != ADMIN_CHAT_ID:
        return

    await update.message.reply_text("📤 Публикую пост...")
    await morning_post(context)
    await update.message.reply_text("✅ Готово! Проверь канал @armykz_news")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я — армейский ИИ-помощник для граждан Казахстана.\n\n"
        "Помогу разобраться с:\n"
        "• Категориями годности (А, Б, В, Г, Д)\n"
        "• Документами для призыва\n"
        "• Сроками и отсрочками\n"
        "• Куда обращаться\n\n"
        "Я *искусственный интеллект* и отвечаю на основе открытых данных. "
        "Для официальных решений обращайтесь в Управление по делам обороны.\n\n"
        "Просто напишите свой вопрос! 💬"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.message.from_user.id

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Логируем вопрос админу
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"❓ Вопрос от пользователя {user_id}:\n\n{user_message}"
            )
        except Exception as e:
            logger.error(f"Лог ошибка: {e}")

    try:
        reply = await ask_gemini(user_message)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"handle_message error: {e}")
        await update.message.reply_text("😔 Ошибка, попробуйте ещё раз.")


# ───────────────────────────────────────────
# ЗАПУСК
# ───────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Расписание постов (UTC время)
    job_queue = app.job_queue
    job_queue.run_daily(morning_post, time=time(hour=5, minute=0))   # 10:00 Астана
    job_queue.run_daily(evening_post, time=time(hour=14, minute=0))  # 19:00 Астана

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("post", manual_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"Бот запущен! CHANNEL_ID={CHANNEL_ID}")
    app.run_polling()


if __name__ == "__main__":
    main()
