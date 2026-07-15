import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sqlite3
from typing import Mapping

from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from utils import dict_factory


LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
EXPECTED_COLUMNS = ('id', 'name', 'created_at')

logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    database_path: Path


def database_path_from_url(value: str) -> Path:
    if value.startswith('sqlite:///'):
        value = value.removeprefix('sqlite:///')
    elif '://' in value:
        raise ValueError('DATABASE_URL must be a SQLite file path or sqlite:/// URL')

    if not value:
        raise ValueError('DATABASE_URL must not be empty')

    return Path(value)


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    load_dotenv()
    values = os.environ if environ is None else environ
    token = values.get('TELEGRAM_TOKEN', '').strip()
    database_url = values.get('DATABASE_URL', '').strip()

    missing = []
    if not token:
        missing.append('TELEGRAM_TOKEN')
    if not database_url:
        missing.append('DATABASE_URL')
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return Settings(token, database_path_from_url(database_url))


def create_connection(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = dict_factory
    return connection


def validate_database(database_path: Path) -> None:
    if not database_path.is_file():
        raise ValueError(f'Database file does not exist: {database_path}')

    connection = sqlite3.connect(f'file:{database_path.resolve().as_posix()}?mode=ro', uri=True)
    try:
        quick_check = connection.execute('PRAGMA quick_check').fetchone()
        if quick_check is None or quick_check[0] != 'ok':
            raise ValueError('SQLite quick_check failed')

        columns = tuple(
            row[1] for row in connection.execute("PRAGMA table_info('smoking')").fetchall()
        )
        if columns != EXPECTED_COLUMNS:
            raise ValueError('Database table smoking has an unexpected schema')
    finally:
        connection.close()


def get_connection(context: ContextTypes.DEFAULT_TYPE) -> sqlite3.Connection:
    return context.application.bot_data['database']


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    connection = get_connection(context)
    connection.execute(
        'INSERT INTO smoking (name, created_at) VALUES (?, ?)',
        (user.username, datetime.now(timezone.utc).isoformat(sep=' ')),
    )
    connection.commit()

    await update.message.reply_text('ok!')


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    connection = get_connection(context)
    res = connection.execute(
        "SELECT name, DATE(DATETIME(created_at, '+03:00')) AS dt, COUNT(*) AS cnt "
        "FROM smoking "
        "GROUP BY 1,2 "
        "ORDER BY created_at "
    )

    smokes = res.fetchall()

    summary_by_person = {}
    for smoke in smokes:
        if smoke['name'] not in summary_by_person:
            summary_by_person[smoke['name']] = []

        summary_by_person[smoke['name']].append(smoke)

    summary_text = ''
    for name in summary_by_person:
        summary_text += f"@{name}:\n"
        for smoke in summary_by_person[name]:
            summary_text += f"{smoke['dt']}: {smoke['cnt']} times\n"

        summary_text += '\n'

    await context.bot.send_message(chat_id=update.effective_chat.id, text=summary_text)


async def day_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    connection = get_connection(context)
    res = connection.execute(
        "SELECT name, TIME(DATETIME(created_at, '+03:00')) AS dt "
        "FROM smoking "
        "WHERE DATE(DATETIME(created_at, '+03:00')) = DATE(DATETIME('now', '+03:00')) "
        "ORDER BY created_at"
    )

    smokes = res.fetchall()

    summary_by_person = {}
    for smoke in smokes:
        if smoke['name'] not in summary_by_person:
            summary_by_person[smoke['name']] = []

        summary_by_person[smoke['name']].append(smoke)

    summary_text = ''
    for name in summary_by_person:
        summary_text += f"@{name}:\n```\n"
        for smoke in summary_by_person[name]:
            summary_text += f"{smoke['dt']}\n"

        summary_text += '```\n'

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        parse_mode=ParseMode.MARKDOWN_V2,
        text=summary_text,
    )


def close_application_database(application: Application) -> None:
    connection = application.bot_data.pop('database', None)
    if connection is not None:
        connection.close()


async def post_shutdown(application: Application) -> None:
    close_application_database(application)


def create_application(settings: Settings) -> Application:
    application = (
        ApplicationBuilder()
        .token(settings.telegram_token)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data['database'] = create_connection(settings.database_path)

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(~filters.COMMAND, track))
    application.add_handler(CommandHandler('summary', summary))
    application.add_handler(CommandHandler('day', day_info))
    return application


async def check_telegram(token: str, bot_factory=Bot) -> None:
    bot = bot_factory(token=token)
    async with bot:
        await bot.get_me()


def run_check(settings: Settings) -> None:
    validate_database(settings.database_path)
    asyncio.run(check_telegram(settings.telegram_token))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='SmokingTrackerBot')
    parser.add_argument(
        '--check',
        action='store_true',
        help='validate configuration, SQLite, and Telegram credentials without polling',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = load_settings()
        validate_database(settings.database_path)

        if args.check:
            asyncio.run(check_telegram(settings.telegram_token))
            logger.info('Configuration, SQLite, and Telegram checks passed')
            return 0

        application = create_application(settings)
        try:
            application.run_polling()
        finally:
            close_application_database(application)
        return 0
    except (OSError, sqlite3.Error, ValueError) as exc:
        logger.error('Startup check failed: %s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
