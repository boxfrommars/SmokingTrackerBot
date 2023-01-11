from datetime import datetime, timezone
import logging
import os
import sqlite3
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from utils import dict_factory

load_dotenv()

telegram_token = os.getenv('TELEGRAM_TOKEN')
db_url = os.getenv('DATABASE_URL')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

conn = sqlite3.connect(db_url, check_same_thread=False)
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

    summary = {}

    for smoke in smokes:
        if smoke['name'] not in summary:
            summary[smoke['name']] = []

        summary[smoke['name']].append(smoke)

    summary_text = ''
    for name in summary:
        summary_text += f"@{name}:\n"
        for s in summary[name]:
            summary_text += f"{s['dt']}: {s['cnt']} times\n"

        summary_text += '\n'

    await context.bot.send_message(chat_id=update.effective_chat.id, text=summary_text)

if __name__ == '__main__':
    application = ApplicationBuilder().token('5951868120:AAH4KS69D2YHtbFjQJKPMOLxYg985ewvCQQ').build()

    start_handler = CommandHandler('start', start)
    track_handler = MessageHandler(~filters.COMMAND, track)
    summary_handler = CommandHandler('summary', summary)

    application.add_handler(start_handler)
    application.add_handler(track_handler)
    application.add_handler(summary_handler)

    application.run_polling()
