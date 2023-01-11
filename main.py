from datetime import datetime, timezone
import logging
import os
import sqlite3
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

load_dotenv()

telegram_token = os.getenv('TELEGRAM_TOKEN')
db_url = os.getenv('DATABASE_URL')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

conn = sqlite3.connect('db.db', check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    cursor.execute('INSERT INTO smoking (name, created_at) VALUES (?, ?)', (user.username, datetime.now(timezone.utc)))
    conn.commit()

    await context.bot.send_message(chat_id=update.effective_chat.id, text='ok!')


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user = update.message.from_user

    res = cursor.execute('SELECT * FROM smoking')
    smokes = res.fetchall()

    summary_lines = [f'@{s.name} has smoked at {s.created_at}' for s in smokes]
    summary_text = '\n'.join(summary_lines)

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
