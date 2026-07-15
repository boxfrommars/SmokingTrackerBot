# SmokingTrackerBot

Telegram-бот для учёта событий курения в SQLite. Бот работает через long polling,
принимает обычные сообщения как новые записи и поддерживает команды:

- `/start` — проверка доступности бота;
- `/summary` — сводка по дням и пользователям;
- `/day` — записи за текущий день.

Production-развёртывание рассчитано на Ubuntu 24.04, CPython 3.14.6, отдельный
virtual environment и systemd. Входящий порт, Nginx, домен и TLS-сертификат для
polling-бота не нужны.

## Конфигурация

Приложение читает две переменные из `.env`:

```dotenv
TELEGRAM_TOKEN=<token from BotFather>
DATABASE_URL=db.db
```

Значение токена в `.env.example` является примером, а не рабочим секретом.
Файлы `.env` и `db.db` игнорируются Git и должны иметь права `600` на сервере.
Не передавайте токен через Git, логи или командную строку.

## Установка CPython 3.14.6 на Ubuntu 24.04

Системный Python Ubuntu заменять нельзя. CPython устанавливается параллельно в
`/opt/python/3.14.6`.

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential curl ca-certificates xz-utils \
  libssl-dev zlib1g-dev libncurses-dev libreadline-dev \
  libsqlite3-dev libgdbm-dev libdb5.3-dev libbz2-dev \
  libexpat1-dev liblzma-dev tk-dev libffi-dev uuid-dev

cd /tmp
curl -fSLO https://www.python.org/ftp/python/3.14.6/Python-3.14.6.tar.xz
echo '143b1dddefaec3bd2e21e3b839b34a2b7fb9842272883c576420d605e9f30c63  Python-3.14.6.tar.xz' \
  | sha256sum -c -
tar -xf Python-3.14.6.tar.xz
cd Python-3.14.6
./configure \
  --prefix=/opt/python/3.14.6 \
  --enable-optimizations \
  --with-lto \
  --with-ensurepip=install
make -j1
sudo make altinstall
```

Однопоточная PGO/LTO-сборка безопаснее для небольшого дроплета без swap, но
может выполняться десятки минут. После установки проверьте runtime и основные
extension-модули:

```bash
/opt/python/3.14.6/bin/python3.14 --version
/opt/python/3.14.6/bin/python3.14 -c \
  'import ssl, sqlite3, lzma, bz2, venv; print(ssl.OPENSSL_VERSION); print(sqlite3.sqlite_version)'
python3 --version  # системная версия должна остаться неизменной
```

## Развёртывание проекта

Команды ниже предполагают пользователя `xu` и каталог
`/home/xu/Workspace/SmokingTrackerBot`, совпадающие с systemd unit в
`deploy/smoking-tracker-bot.service`.

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

Для нового экземпляра создайте конфигурацию и пустую базу:

```bash
cp .env.example .env
chmod 600 .env
nano .env

.venv/bin/alembic upgrade head
.venv/bin/python main.py --check
```

`main.py --check` проверяет обязательные переменные, SQLite `quick_check`, схему
таблицы и Telegram `getMe`. Polling и `getUpdates` в этом режиме не запускаются.

Установите сервис только после успешных проверок:

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

Unit запускается после готовности сети, автоматически стартует после reboot и
перезапускает процесс через пять секунд при аварийном завершении. Ручной
`systemctl stop` не вызывает автоматический restart.

Если пользователь или путь отличаются, сначала исправьте `User`, `Group`,
`WorkingDirectory`, `EnvironmentFile` и `ExecStart` в unit-файле.

## Перенос существующей SQLite-базы

Нельзя одновременно запускать два polling-процесса с одним Telegram-токеном.
Новый сервер полностью подготавливается при остановленном unit, а финальная база
копируется только после остановки старого бота.

1. На новом сервере установите Python, проект, зависимости, `.env` и systemd
   unit, но оставьте unit остановленным и disabled.
2. Проверьте код на временной базе:

   ```bash
   DATABASE_URL=/tmp/smoking-preflight.db .venv/bin/alembic upgrade head
   DATABASE_URL=/tmp/smoking-preflight.db .venv/bin/python main.py --check
   rm -f /tmp/smoking-preflight.db
   ```

3. Убедитесь, что новый сервис не работает, затем штатно остановите старый
   polling-процесс и дождитесь его полного завершения.
4. На старом сервере создайте rollback-копию и checksum:

   ```bash
   cp --preserve=timestamps,mode db.db db.db.rollback-YYYYMMDD
   chmod 600 db.db.rollback-YYYYMMDD
   sha256sum db.db
   ```

5. Передайте `.env` и `db.db` по SSH/SCP без вывода содержимого. На новом
   сервере сравните SHA-256, затем установите права:

   ```bash
   chown xu:xu .env db.db
   chmod 600 .env db.db
   .venv/bin/python main.py --check
   sudo systemctl enable --now smoking-tracker-bot.service
   ```

6. Проверьте `/start`, `/summary`, `/day` и одно обычное сообщение. Убедитесь,
   что работает ровно один процесс и `NRestarts` не растёт:

   ```bash
   systemctl show smoking-tracker-bot.service -p NRestarts -p ExecMainPID
   journalctl -u smoking-tracker-bot.service --since '10 minutes ago' --no-pager
   ```

## Обновление развёрнутого экземпляра

```bash
cd /home/xu/Workspace/SmokingTrackerBot
git switch master
git pull --ff-only
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python -W error::DeprecationWarning -m unittest discover -s tests -v
sudo systemctl restart smoking-tracker-bot.service
systemctl is-active smoking-tracker-bot.service
```

Перед изменением прямых зависимостей обновите `requirements.in`, а lock-файл
генерируйте на Linux с CPython 3.14 и фиксированной версией `pip-tools`:

```bash
.venv/bin/python -m pip install pip-tools==7.5.3
.venv/bin/python -m piptools compile \
  --upgrade --generate-hashes --strip-extras \
  --output-file=requirements.txt requirements.in
```

## Rollback

1. Полностью остановите новый экземпляр:

   ```bash
   sudo systemctl disable --now smoking-tracker-bot.service
   ```

2. Убедитесь, что новый polling-процесс завершён.
3. Если после переключения появились новые записи, скопируйте актуальную
   `db.db` обратно на старый сервер и сохраните там предыдущую базу отдельно.
4. Только после этого запустите старый экземпляр в прежнем окружении.

В любой момент с одним Telegram-токеном должен работать не более чем один
polling-процесс.
