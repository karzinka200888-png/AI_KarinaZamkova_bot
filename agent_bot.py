import os
import json
import math
import logging
import base64
import httpx
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TG_TOKEN = os.getenv("TG_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

NOTES_DIR = Path("notes")
NOTES_DIR.mkdir(exist_ok=True)

conversations: dict = {}

SYSTEM_PROMPT = """Ти — AI бізнес-асистент для підприємців.

Твої сильні сторони:
• Стратегічне мислення — аналіз ідей
• Управління — пріоритети, делегування
• Комунікація — листи, презентації
• Фінанси — unit-економіка, ROI

Будь конкретним, давай цифри та плани.
Відповідай українською мовою, якщо користувач не просить інакше.
Використовуй інструменти коли потрібно.
Поточний user_id буде вказано в повідомленні системи."""

TOOLS = [
    {
        "name": "calculate",
        "description": "Виконує математичні розрахунки. Підтримує +,-,*,/,**, sqrt, sin, cos, log, pi, e тощо.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Математичний вираз, наприклад: '2 ** 10' або 'sqrt(144)'",
                }
            },
            "required": ["expression"],
        },
    },
    {
        "name": "save_note",
        "description": "Зберігає нотатку для користувача",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "ID користувача Telegram"},
                "title": {"type": "string", "description": "Заголовок нотатки"},
                "content": {"type": "string", "description": "Текст нотатки"},
            },
            "required": ["user_id", "title", "content"],
        },
    },
    {
        "name": "list_notes",
        "description": "Повертає список нотаток користувача",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "ID користувача Telegram"}
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "delete_note",
        "description": "Видаляє нотатку користувача за заголовком",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "ID користувача Telegram"},
                "title": {"type": "string", "description": "Заголовок нотатки для видалення"},
            },
            "required": ["user_id", "title"],
        },
    },
    {
        "name": "get_datetime",
        "description": "Повертає поточну дату та час українською мовою",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_url",
        "description": "Читає текстовий вміст веб-сторінки за URL. Використовуй для отримання інформації з інтернету.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL сторінки"}
            },
            "required": ["url"],
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_calculate(expression: str) -> str:
    try:
        safe_env = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
        safe_env["abs"] = abs
        safe_env["round"] = round
        result = eval(expression, {"__builtins__": {}}, safe_env)  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Помилка обчислення: {e}"


def tool_save_note(user_id: int, title: str, content: str) -> str:
    user_dir = NOTES_DIR / str(user_id)
    user_dir.mkdir(exist_ok=True)
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
    note_file = user_dir / f"{safe_title}.json"
    note = {"title": title, "content": content, "created": datetime.now().isoformat()}
    note_file.write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"✅ Нотатку «{title}» збережено"


def tool_list_notes(user_id: int) -> str:
    user_dir = NOTES_DIR / str(user_id)
    if not user_dir.exists():
        return "Нотаток немає"
    notes = sorted(user_dir.glob("*.json"))
    if not notes:
        return "Нотаток немає"
    lines = []
    for i, note_file in enumerate(notes, 1):
        data = json.loads(note_file.read_text(encoding="utf-8"))
        preview = data["content"][:60].replace("\n", " ")
        lines.append(f"{i}. 📝 *{data['title']}*\n   {preview}…")
    return "\n".join(lines)


def tool_delete_note(user_id: int, title: str) -> str:
    user_dir = NOTES_DIR / str(user_id)
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
    note_file = user_dir / f"{safe_title}.json"
    if note_file.exists():
        note_file.unlink()
        return f"🗑 Нотатку «{title}» видалено"
    return f"Нотатку «{title}» не знайдено"


def tool_get_datetime() -> str:
    MONTHS = {
        1: "січня", 2: "лютого", 3: "березня", 4: "квітня",
        5: "травня", 6: "червня", 7: "липня", 8: "серпня",
        9: "вересня", 10: "жовтня", 11: "листопада", 12: "грудня",
    }
    DAYS = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя"]
    now = datetime.now()
    return f"{DAYS[now.weekday()]}, {now.day} {MONTHS[now.month]} {now.year} р., {now.strftime('%H:%M')}"


def tool_read_url(url: str) -> str:
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as http:
            r = http.get(url, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.splitlines() if len(l.strip()) > 25]
        return "\n".join(lines[:120])
    except Exception as e:
        return f"Помилка читання URL: {e}"


def execute_tool(name: str, inputs: dict) -> str:
    if name == "calculate":
        return tool_calculate(inputs["expression"])
    if name == "save_note":
        return tool_save_note(inputs["user_id"], inputs["title"], inputs["content"])
    if name == "list_notes":
        return tool_list_notes(inputs["user_id"])
    if name == "delete_note":
        return tool_delete_note(inputs["user_id"], inputs["title"])
    if name == "get_datetime":
        return tool_get_datetime()
    if name == "read_url":
        return tool_read_url(inputs["url"])
    return f"Невідомий інструмент: {name}"


# ── Agentic loop ──────────────────────────────────────────────────────────────

async def run_agent(user_id: int, messages: list) -> str:
    system = f"{SYSTEM_PROMPT}\nПоточний user_id: {user_id}"
    current_messages = list(messages)

    for _ in range(8):  # max 8 tool rounds
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=current_messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "Відповідь не отримана"

        if response.stop_reason == "tool_use":
            current_messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"Tool call: {block.name}({block.input})")
                    result = execute_tool(block.name, block.input)
                    logger.info(f"Tool result: {result[:80]}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            current_messages.append({"role": "user", "content": tool_results})
            continue

        break

    return "Не вдалося отримати відповідь після кількох спроб"


# ── Telegram handlers ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text(
        "Привіт! Я бізнес-асистент на базі Claude AI 🤖\n\n"
        "Я вмію:\n"
        "• Відповідати на питання\n"
        "• 🔢 Рахувати математику\n"
        "• 📝 Зберігати нотатки (/notes)\n"
        "• 🌐 Читати веб-сторінки\n"
        "• 📅 Повідомляти дату/час\n"
        "• 📷 Аналізувати фото\n\n"
        "/reset — почати нову розмову\n"
        "/notes — мої нотатки"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text("✅ Розмову скинуто. Починаємо спочатку!")


async def notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = tool_list_notes(user_id)
    await update.message.reply_text(result, parse_mode="Markdown")


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
        reply = await run_agent(user_id, conversations[user_id])
        conversations[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"handle_message error: {e}")
        await update.message.reply_text("Виникла помилка. Спробуйте ще раз або /reset.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = update.message.caption or "Опиши що зображено на фото"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        photo_b64 = base64.standard_b64encode(bytes(photo_bytes)).decode()

        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1024,
            system=SYSTEM_PROMPT + f"\nПоточний user_id: {user_id}",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": photo_b64}},
                    {"type": "text", "text": caption},
                ],
            }],
        )
        reply = response.content[0].text
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"handle_photo error: {e}")
        await update.message.reply_text("Не вдалося обробити фото. Спробуйте ще раз.")


def main():
    logger.info("Agent bot started with tools")
    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("notes", notes_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
