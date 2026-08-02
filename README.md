# SmokingTrackerBot

A Telegram bot that records smoking events in SQLite. It uses long polling,
treats regular text messages as new records, and supports these commands:

- `/start` — check that the bot is available;
- `/summary` — show totals grouped by user and day;
- `/day` — show events recorded today.

A polling bot does not require an inbound port, domain, HTTP server, or TLS
certificate.

## Requirements

- CPython 3.14 with `venv`, `ssl`, and `sqlite3` support;
- a Telegram bot token issued by BotFather.

The dependency lock is generated for Linux with CPython 3.14. Verify the
runtime and its required standard-library modules before installing packages:

```bash
python3.14 --version
python3.14 -c \
  'import ssl, sqlite3, lzma, bz2, venv; print(ssl.OPENSSL_VERSION); print(sqlite3.sqlite_version)'
```

## Setup

Create an isolated environment and install the complete hashed lock:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
```

Create `.env` from `.env.example` and provide the two required variables:

```dotenv
TELEGRAM_TOKEN=<token from BotFather>
DATABASE_URL=db.db
```

`DATABASE_URL` accepts either a SQLite file path or a `sqlite:///` URL. A
relative path is resolved from the process working directory. Other database
schemes are rejected.

The token in `.env.example` is a non-working example. Both `.env` and `db.db`
are excluded from Git. Never place the token, a production environment file,
the user database, or a backup in Git, logs, or command-line arguments.

Initialize a new database, or bring an existing one to the current schema:

```bash
.venv/bin/python -m alembic upgrade head
```

For an existing persistent database, follow the backup and migration
requirements in [DEPLOYMENT.md](DEPLOYMENT.md) before applying migrations.

## Verification

Run the automated tests and application preflight check:

```bash
.venv/bin/python -m pip check
.venv/bin/python -W error::DeprecationWarning -m unittest discover -s tests -v
.venv/bin/python -m alembic current --check-heads
.venv/bin/python main.py --check
```

`main.py --check` validates the required environment variables, confirms that
the SQLite file exists, runs SQLite `quick_check`, verifies the `smoking` table
schema, and calls Telegram `getMe`. It does not start polling or call
`getUpdates`.

## Running the bot

Start the long-running polling process from the project root:

```bash
.venv/bin/python main.py
```

Never run this command with the production token while another instance is
polling. Use a separate test bot token for development, or stop and confirm the
exit of the existing process before starting its replacement.

## Updating dependencies

Update direct dependencies in `requirements.in`. Generate the lock file on
Linux with CPython 3.14 and the pinned `pip-tools` version:

```bash
.venv/bin/python -m pip install pip-tools==7.5.3
.venv/bin/python -m piptools compile \
  --upgrade --generate-hashes --strip-extras \
  --output-file=requirements.txt requirements.in
```

Commit `requirements.in` and the generated `requirements.txt` together. Do not
edit the lock file manually.

## Deployment

[DEPLOYMENT.md](DEPLOYMENT.md) is the canonical, environment-independent
contract for runtime, configuration, persistent data, migrations, release
checks, smoke testing, backup, and rollback.
