# SmokingTrackerBot

A Telegram bot that records smoking events in SQLite. It uses long polling,
treats regular text messages as new records, and supports these commands:

- `/start` — check that the bot is available;
- `/summary` — show totals grouped by user and day;
- `/day` — show events recorded today.

A polling bot does not require an inbound port, domain, Nginx virtual host, or
TLS certificate.

## Requirements

- Linux server with CPython 3.14;
- Git and SSH access to the repository;
- Telegram bot token issued by BotFather;
- systemd for production process management.

Verify that Python and the required standard-library modules are available:

```bash
python3.14 --version
python3.14 -c \
  'import ssl, sqlite3, lzma, bz2, venv; print(ssl.OPENSSL_VERSION); print(sqlite3.sqlite_version)'
```

## Configuration

The application reads two variables from `.env`:

```dotenv
TELEGRAM_TOKEN=<token from BotFather>
DATABASE_URL=db.db
```

The token in `.env.example` is an example, not a working secret. Both `.env`
and `db.db` are excluded from Git and should only be accessible to the service
account in production. Never place the token in Git, logs, or command-line
arguments.

## Deployment

1. Clone the repository and switch to `master`.
2. Create a virtual environment with CPython 3.14.
3. Install the locked dependencies.
4. Create `.env` based on `.env.example` and add the real Telegram token.
5. Initialize a new database with Alembic, or transfer the existing `.env` and
   SQLite database from the previous deployment.
6. Run the tests and the application preflight check.
7. Adapt the provided systemd unit to the deployment user and project path,
   install it, and enable the service.

Typical project setup commands:

```bash
git clone <repository-url>
cd SmokingTrackerBot
git switch master

python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -W error::DeprecationWarning -m unittest discover -s tests -v
```

For a new database:

```bash
.venv/bin/alembic upgrade head
```

Before starting the service, run:

```bash
.venv/bin/python main.py --check
```

`main.py --check` validates the required environment variables, runs SQLite
`quick_check`, verifies the database schema, and calls Telegram `getMe`. It does
not start polling or call `getUpdates`.

The example unit is located at `deploy/smoking-tracker-bot.service`. Update its
user, group, working directory, environment file, and executable paths for the
target environment before installing it.

The unit is configured to:

- start after the network is online;
- start automatically after a server reboot;
- restart the bot five seconds after an abnormal exit;
- leave the bot stopped after a manual service stop.

## Migrating an existing deployment

Never run two polling processes with the same Telegram token.

Prepare and validate the new deployment while its service is stopped. When it
is ready, stop the old bot completely, transfer the current `.env` and SQLite
database to the new deployment using a secure method, verify that the files are
intact and accessible only to the service account, and start the new service.

After cutover, test `/start`, `/summary`, `/day`, and one regular message.
Confirm that exactly one process is polling, the service remains active, and
its restart counter is stable.

Keep the stopped old deployment and a database backup for a short rollback
window. Do not leave the old process running.

## Updating a deployed instance

Stop or restart the service only after the updated code and dependencies have
passed their checks:

```bash
git switch master
git pull --ff-only
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -W error::DeprecationWarning -m unittest discover -s tests -v
.venv/bin/python main.py --check
```

Then restart the systemd service and confirm that it is active without a
growing restart count.

Update direct dependencies in `requirements.in`. Generate the lock file on
Linux with CPython 3.14 and the pinned `pip-tools` version:

```bash
.venv/bin/python -m pip install pip-tools==7.5.3
.venv/bin/python -m piptools compile \
  --upgrade --generate-hashes --strip-extras \
  --output-file=requirements.txt requirements.in
```

Commit both `requirements.in` and the generated `requirements.txt`.

## Rollback

Stop the new service and confirm that its polling process has exited. If the
new deployment accepted records after cutover, transfer its current database
back to the old deployment while retaining a backup. Start the old bot only
after confirming that the new process is stopped.

At every stage, no more than one polling process may use the Telegram token.
