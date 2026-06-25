# ИП Консультант KZ — Telegram Bot

Бот-консультант по регистрации ИП, грантам и бизнес-планам в Казахстане.

## Переменные окружения (Environment Variables)

Нужно добавить в Railway или любой другой хостинг:

- `TELEGRAM_TOKEN` — токен от @BotFather
- `OPENROUTER_API_KEY` — ключ от openrouter.ai

## Запуск локально

```bash
pip install -r requirements.txt
export TELEGRAM_TOKEN=your_token
export OPENROUTER_API_KEY=your_key
python bot.py
```
