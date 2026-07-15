import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import main


TOKEN = '123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / 'db.db'
        connection = sqlite3.connect(self.database_path)
        connection.execute(
            'CREATE TABLE smoking ('
            'id INTEGER PRIMARY KEY, '
            'name VARCHAR(50) NOT NULL, '
            'created_at DATETIME NOT NULL)'
        )
        connection.commit()
        connection.close()
        self.settings = main.Settings(TOKEN, self.database_path)

    def tearDown(self):
        self.temporary_directory.cleanup()


class SettingsTests(unittest.TestCase):
    def test_http_client_does_not_log_token_bearing_urls_at_info(self):
        self.assertGreater(logging.getLogger('httpx').getEffectiveLevel(), logging.INFO)
        self.assertGreater(logging.getLogger('httpcore').getEffectiveLevel(), logging.INFO)

    def test_missing_required_environment_variables(self):
        with self.assertRaisesRegex(ValueError, 'TELEGRAM_TOKEN, DATABASE_URL'):
            main.load_settings({})

    def test_plain_database_path_is_supported(self):
        settings = main.load_settings(
            {'TELEGRAM_TOKEN': TOKEN, 'DATABASE_URL': 'db.db'}
        )
        self.assertEqual(settings.database_path, Path('db.db'))

    def test_sqlite_url_is_supported(self):
        self.assertEqual(main.database_path_from_url('sqlite:///db.db'), Path('db.db'))

    def test_other_database_schemes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SQLite'):
            main.database_path_from_url('postgresql://localhost/database')


class DatabaseValidationTests(DatabaseTestCase):
    def test_valid_database_passes(self):
        main.validate_database(self.database_path)

    def test_missing_database_is_not_created(self):
        missing = Path(self.temporary_directory.name) / 'missing.db'
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            main.validate_database(missing)
        self.assertFalse(missing.exists())

    def test_unexpected_schema_is_rejected(self):
        connection = sqlite3.connect(self.database_path)
        connection.execute('ALTER TABLE smoking ADD COLUMN unexpected TEXT')
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, 'unexpected schema'):
            main.validate_database(self.database_path)


class ApplicationTests(DatabaseTestCase):
    def test_application_contains_all_handlers(self):
        application = main.create_application(self.settings)
        try:
            callbacks = [handler.callback for handler in application.handlers[0]]
            self.assertEqual(
                callbacks,
                [main.start, main.track, main.summary, main.day_info],
            )
        finally:
            main.close_application_database(application)

    def test_application_database_is_closed(self):
        application = main.create_application(self.settings)
        connection = application.bot_data['database']
        asyncio.run(main.post_shutdown(application))
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')


class HandlerTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.connection = main.create_connection(self.database_path)
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.context = SimpleNamespace(
            application=SimpleNamespace(bot_data={'database': self.connection}),
            bot=self.bot,
        )

    def tearDown(self):
        self.connection.close()
        super().tearDown()

    def test_track_inserts_a_row_and_replies(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(username='alice'),
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(message=message)

        asyncio.run(main.track(update, self.context))

        row = self.connection.execute('SELECT name, created_at FROM smoking').fetchone()
        self.assertEqual(row['name'], 'alice')
        self.assertIsNotNone(row['created_at'])
        message.reply_text.assert_awaited_once_with('ok!')

    def test_summary_preserves_existing_output_format(self):
        self.connection.executemany(
            'INSERT INTO smoking (name, created_at) VALUES (?, ?)',
            [
                ('alice', '2026-07-15 01:00:00+00:00'),
                ('alice', '2026-07-15 02:00:00+00:00'),
            ],
        )
        self.connection.commit()
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=42))

        asyncio.run(main.summary(update, self.context))

        self.bot.send_message.assert_awaited_once_with(
            chat_id=42,
            text='@alice:\n2026-07-15: 2 times\n\n',
        )

    def test_day_preserves_existing_output_format(self):
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        self.connection.execute(
            'INSERT INTO smoking (name, created_at) VALUES (?, ?)',
            ('alice', now),
        )
        self.connection.commit()
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=42))

        asyncio.run(main.day_info(update, self.context))

        call = self.bot.send_message.await_args.kwargs
        self.assertEqual(call['chat_id'], 42)
        self.assertTrue(call['text'].startswith('@alice:\n```\n'))
        self.assertTrue(call['text'].endswith('```\n'))
        self.assertEqual(call['parse_mode'], main.ParseMode.MARKDOWN_V2)


class FakeBot:
    def __init__(self, token):
        self.token = token
        self.get_me = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


class CheckModeTests(unittest.TestCase):
    def test_check_telegram_only_calls_get_me(self):
        created = []

        def factory(*, token):
            bot = FakeBot(token)
            created.append(bot)
            return bot

        asyncio.run(main.check_telegram(TOKEN, bot_factory=factory))

        self.assertEqual(created[0].token, TOKEN)
        created[0].get_me.assert_awaited_once_with()


if __name__ == '__main__':
    unittest.main()
