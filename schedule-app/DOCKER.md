# Docker

## Быстрый старт

```bash
# 1. Создать файл .env с паролем (или скопировать .env.example)
cp .env.example .env
# Отредактировать .env — указать SCHEDULE_PASSWORD

# 2. Собрать и запустить
docker compose up --build -d

# 3. Открыть в браузере
#    http://localhost:5000
```

## Остановка

```bash
docker compose down
```

## Перезапуск с очисткой БД

```bash
docker compose down
rm -rf data/
docker compose up --build -d
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SCHEDULE_PASSWORD` | — | **Обязательно.** Пароль администратора |
| `SCHEDULE_SECRET_KEY` | генерируется | Секретный ключ Flask |
| `FLASK_HOST` | `0.0.0.0` | Адрес (в Docker — обязательно 0.0.0.0) |
| `FLASK_PORT` | `5000` | Порт |
| `FLASK_DEBUG` | `0` | Режим отладки (1/true) |
| `SCHEDULE_DATA_DIR` | `/app/data` | Директория для БД |
| `SCHEDULE_BACKUPS_DIR` | `/app/backups` | Директория для бэкапов |

## Тома

- `./data:/app/data` — SQLite БД (persistent)
- `./backups:/app/backups` — бэкапы БД
