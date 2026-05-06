import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TG_TOKEN = os.getenv("TG_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

conversations = {}

SYSTEM_PROMPT = """Ти корисний AI-асистент на базі Claude.
Відповідай українською мовою, якщо користувач не просить інакше.
Будь доброзичливим, корисним і точним."""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text(
        "Привіт! Я AI-асистент на базі Claude. 🤖\n\n"
        "Напишіть мені будь-що — я відповім.\n"
        "/reset — почати нову розмову"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text("Розмову скинуто. Починаємо спочатку! ✅")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in conversations:
        conversations[user_id] = []

    conversations[user_id].append({"role": "user", "content": user_text})

    if len(conversations[user_id]) > 20:
        conversations[user_id] = conversations[user_id][-20:]

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=conversations[user_id],
        )

        assistant_text = response.content[0].text
        conversations[user_id].append({"role": "assistant", "content": assistant_text})

        await update.message.reply_text(assistant_text)

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Виникла помилка. Спробуйте ще раз або /reset.")


def main():
    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
