# SmokingTrackerBot

A Telegram bot that records smoking events in SQLite. It uses long polling,
treats regular text messages as new records, and supports these commands:

- `/start` — check that the bot is available;
- `/summary` — show totals grouped by user and day;
- `/day` — show events recorded today.

The production setup uses CPython 3.14, a dedicated virtual environment, and
systemd. A polling bot does not require an inbound port, domain, Nginx virtual
host, or TLS certificate.

## Requirements

- Linux server with CPython 3.14 installed separately from the system Python;
- Git and SSH access to the repository;
- Telegram bot token issued by BotFather;
- systemd;
- project path `/home/xu/Workspace/SmokingTrackerBot` and user `xu`, or
  corresponding changes to the provided unit file.

Verify that the required Python modules are available before deployment:

```bash
/opt/python/3.14.6/bin/python3.14 --version
/opt/python/3.14.6/bin/python3.14 -c \
  'import ssl, sqlite3, lzma, bz2, venv; print(ssl.OPENSSL_VERSION); print(sqlite3.sqlite_version)'
```

## Configuration

The application reads two variables from `.env`:

```dotenv
TELEGRAM_TOKEN=<token from BotFather>
DATABASE_URL=db.db
```

The token in `.env.example` is an example, not a working secret. Both `.env`
and `db.db` are excluded from Git and should have mode `600` in production.
Never place the token in Git, logs, or command-line arguments.

## Deploying a new instance

The commands below match the paths and user configured in
`deploy/smoking-tracker-bot.service`.

Clone the repository and create the virtual environment:

```bash
mkdir -p /home/xu/Workspace
git clone git@github.com:boxfrommars/SmokingTrackerBot.git \
  /home/xu/Workspace/SmokingTrackerBot
cd /home/xu/Workspace/SmokingTrackerBot
git switch master

/opt/python/3.14.6/bin/python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -W error::DeprecationWarning -m unittest discover -s tests -v
```

Create the configuration and initialize a new database:

```bash
cp .env.example .env
chmod 600 .env
nano .env

.venv/bin/alembic upgrade head
.venv/bin/python main.py --check
```

`main.py --check` validates the required environment variables, runs SQLite
`quick_check`, verifies the database schema, and calls Telegram `getMe`. It does
not start polling or call `getUpdates`.

Install and start the systemd unit only after all checks pass:

```bash
sudo install -o root -g root -m 0644 \
  deploy/smoking-tracker-bot.service \
  /etc/systemd/system/smoking-tracker-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now smoking-tracker-bot.service

systemctl is-active smoking-tracker-bot.service
systemctl is-enabled smoking-tracker-bot.service
systemctl status smoking-tracker-bot.service --no-pager
```

The unit starts after the network is online, starts automatically after a
server reboot, and restarts the bot five seconds after an abnormal exit. A
manual `systemctl stop` does not trigger an automatic restart.

If the deployment user or path differs, update `User`, `Group`,
`WorkingDirectory`, `EnvironmentFile`, and `ExecStart` in the unit file before
installing it.

## Migrating an existing SQLite database

Never run two polling processes with the same Telegram token. Prepare the new
server while its unit is stopped, and copy the final database only after the
old bot has stopped completely.

1. On the new server, prepare the repository, virtual environment,
   dependencies, `.env`, and systemd unit. Keep the unit stopped and disabled.
2. Test the application with a temporary database:

   ```bash
   DATABASE_URL=/tmp/smoking-preflight.db .venv/bin/alembic upgrade head
   DATABASE_URL=/tmp/smoking-preflight.db .venv/bin/python main.py --check
   rm -f /tmp/smoking-preflight.db
   ```

3. Confirm that the new service is stopped. Gracefully stop the old polling
   process and wait until it has exited.
4. Create a rollback copy and checksum on the old server:

   ```bash
   cp --preserve=timestamps,mode db.db db.db.rollback-YYYYMMDD
   chmod 600 db.db.rollback-YYYYMMDD
   sha256sum db.db
   ```

5. Transfer `.env` and `db.db` over SSH/SCP without printing their contents.
   Compare the SHA-256 checksum on the new server and set ownership and modes:

   ```bash
   chown xu:xu .env db.db
   chmod 600 .env db.db
   .venv/bin/python main.py --check
   sudo systemctl enable --now smoking-tracker-bot.service
   ```

6. Test `/start`, `/summary`, `/day`, and one regular message. Confirm that
   exactly one process is polling and that the restart counter is stable:

   ```bash
   systemctl show smoking-tracker-bot.service -p NRestarts -p ExecMainPID
   journalctl -u smoking-tracker-bot.service --since '10 minutes ago' --no-pager
   ```

Keep the stopped old deployment and its rollback database for a short rollback
window. Do not leave the old process running.

## Updating a deployed instance

```bash
cd /home/xu/Workspace/SmokingTrackerBot
git switch master
git pull --ff-only
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -W error::DeprecationWarning -m unittest discover -s tests -v
sudo systemctl restart smoking-tracker-bot.service
systemctl is-active smoking-tracker-bot.service
```

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

1. Stop the new instance completely:

   ```bash
   sudo systemctl disable --now smoking-tracker-bot.service
   ```

2. Confirm that its polling process has exited.
3. If the new instance accepted records after cutover, copy its current `db.db`
   back to the old server while preserving the previous database separately.
4. Start the old bot only after confirming that the new process is stopped.

At every stage, no more than one polling process may use the Telegram token.
