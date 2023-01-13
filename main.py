from datetime import datetime, timezone
import logging
import os
import sqlite3
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from utils import dict_factory

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
DB_URL = os.getenv('DATABASE_URL')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

conn = sqlite3.connect(DB_URL, check_same_thread=False)
conn.row_factory = dict_factory
cursor = conn.cursor()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    cursor.execute('INSERT INTO smoking (name, created_at) VALUES (?, ?)', (user.username, datetime.now(timezone.utc)))
    conn.commit()

    await update.message.reply_text('ok!')


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = cursor.execute("SELECT name, DATE(DATETIME(created_at, '+03:00')) AS dt, COUNT(*) AS cnt "
                         "FROM smoking "
                         "GROUP BY 1,2 "
                         "ORDER BY created_at ")

    smokes = res.fetchall()

    summary_by_person = {}
    for smoke in smokes:
        if smoke['name'] not in summary_by_person:
            summary_by_person[smoke['name']] = []

        summary_by_person[smoke['name']].append(smoke)

    summary_text = ''
    for name in summary_by_person:
        summary_text += f"@{name}:\n"
        for s in summary_by_person[name]:
            summary_text += f"{s['dt']}: {s['cnt']} times\n"

        summary_text += '\n'

    await context.bot.send_message(chat_id=update.effective_chat.id, text=summary_text)


async def day_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = cursor.execute("SELECT name, TIME(DATETIME(created_at, '+03:00')) AS dt "
                         "FROM smoking "
                         "WHERE DATE(DATETIME(created_at, '+03:00')) = DATE(DATETIME('now', '+03:00')) "
                         "ORDER BY created_at")

    smokes = res.fetchall()

    summary_by_person = {}
    for smoke in smokes:
        if smoke['name'] not in summary_by_person:
            summary_by_person[smoke['name']] = []

        summary_by_person[smoke['name']].append(smoke)

    summary_text = ''
    for name in summary_by_person:
        summary_text += f"@{name}:\n```\n"
        for s in summary_by_person[name]:
            summary_text += f"{s['dt']}\n"

        summary_text += '```\n'

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        parse_mode=ParseMode.MARKDOWN_V2,
        text=summary_text)


if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    start_handler = CommandHandler('start', start)
    track_handler = MessageHandler(~filters.COMMAND, track)
    summary_handler = CommandHandler('summary', summary)
    day_info_handler = CommandHandler('day', day_info)

    application.add_handler(start_handler)
    application.add_handler(track_handler)
    application.add_handler(summary_handler)
    application.add_handler(day_info_handler)

    application.run_polling()
