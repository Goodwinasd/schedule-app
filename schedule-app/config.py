# Изменение №1 (бэкенд-рефакторинг): выделен config.py

import os
import os.path
import secrets
import re
import logging
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)


def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

# ---- Secrets ----

class ConfigError(RuntimeError):
    """Ошибка конфигурации: приложение не может стартовать. Явно, а не молча."""


# Ключ из старого .env.example: он засвечен в репозитории, подписывать им сессии нельзя.
_LEAKED_SECRET_KEYS = {'0384e0d154b345d12a37d51db9a846b11647ace477f27991'}


def _require_strong_password(password):
    """Проверить пароль администратора; бросить ConfigError с понятным текстом."""
    if not password:
        raise ConfigError(
            "SCHEDULE_PASSWORD не задан. Скопируйте .env.example в .env и укажите пароль "
            "администратора (минимум 8 символов, цифра и спецсимвол)."
        )
    if len(password) < 8 or not re.search(r'\d', password) or not re.search(r'[!@#$%^&*()_+\-=]', password):
        raise ConfigError(
            "SCHEDULE_PASSWORD слишком простой: нужно минимум 8 символов, цифра и спецсимвол "
            "из набора !@#$%^&*()_+-="
        )


def _is_weak_secret(key):
    """Похож ли ключ подписи сессий на дефолтный или засвеченный в репозитории."""
    if not key:
        return False
    return key in _LEAKED_SECRET_KEYS or key.strip().lower().startswith('change-me')


PASSWORD = os.environ.get('SCHEDULE_PASSWORD')
_require_strong_password(PASSWORD)

SECRET_KEY = os.environ.get('SCHEDULE_SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    with open(env_path, 'a', encoding='utf-8') as f:
        f.write(f"\nSCHEDULE_SECRET_KEY={SECRET_KEY}\n")
    logger.warning(
        "SCHEDULE_SECRET_KEY не задан — сгенерирован новый и записан в .env. "
        "Ключ подписи сессий общий для всех копий приложения: не коммитьте .env."
    )
elif _is_weak_secret(SECRET_KEY):
    logger.warning(
        "SCHEDULE_SECRET_KEY похож на дефолтный или засвеченный: подпись сессий можно "
        "подделать. Смените ключ в .env — это разлогинит всех пользователей."
    )

ADMIN_PASSWORD_HASH = generate_password_hash(PASSWORD)

# ---- Database ----

DB_DIR = os.path.dirname(__file__)
DB_NAME = 'schedule.db'
DATA_DIR = os.environ.get('SCHEDULE_DATA_DIR', os.path.join(DB_DIR, 'data'))
DB_PATH = os.path.join(DATA_DIR, DB_NAME)
BACKUPS_DIR = os.environ.get('SCHEDULE_BACKUPS_DIR', os.path.join(DB_DIR, 'backups'))

# ---- App settings ----

# ---- Dynamic settings (single source of truth) ----

SESSION_LIFETIME_MIN = 60
SESSION_LIFETIME_DEFAULT = 3600
SETTINGS = {
    'session_lifetime': SESSION_LIFETIME_DEFAULT,
    'login_rate_limit': 5,
    'login_rate_window': 300,
    'backup_retention_days': 30,
}

# Чтение из БД с fallback на хардкод (если миграция не применена или таблица пуста)
def _load_settings_from_db():
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute('SELECT key, value FROM settings').fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def sync_settings_from_db():
    """Refresh the in-memory SETTINGS dict from the DB (single source of truth)."""
    global SETTINGS
    db = _load_settings_from_db()
    for key in SETTINGS.keys():
        if key in db:
            try:
                SETTINGS[key] = int(db[key])
            except (TypeError, ValueError):
                pass
    if SETTINGS['session_lifetime'] < SESSION_LIFETIME_MIN:
        SETTINGS['session_lifetime'] = SESSION_LIFETIME_DEFAULT


def apply_setting(key, value):
    """Validate, persist to DB and update the in-memory dict atomically.
    Returns the normalized string value or raises ValueError."""
    if key not in SETTINGS:
        raise ValueError("Unknown setting")
    num = int(value)
    if num < 1:
        raise ValueError("Значение должно быть положительным целым числом")
    if key == 'session_lifetime' and num < SESSION_LIFETIME_MIN:
        num = SESSION_LIFETIME_DEFAULT
    SETTINGS[key] = num
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                 (key, str(num)))
    conn.commit()
    conn.close()
    return str(num)


sync_settings_from_db()

PERMANENT_SESSION_LIFETIME = SETTINGS['session_lifetime']
LOGIN_RATE_LIMIT = SETTINGS['login_rate_limit']
LOGIN_RATE_WINDOW = SETTINGS['login_rate_window']
BACKUP_RETENTION_DAYS = SETTINGS['backup_retention_days']
TRASH_RETENTION_DAYS = 30

DEBUG = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
HOST = os.environ.get('FLASK_HOST', '127.0.0.1')
PORT = int(os.environ.get('FLASK_PORT', 5000))

# ---- Bell schedule ----

BELL_SCHEDULE = [
    {"period": 1, "start": "8:30", "end": "9:55", "shift": 1},
    {"period": 2, "start": "10:00", "end": "11:25", "shift": 1},
    {"period": 3, "start": "12:00", "end": "13:25", "shift": 1},
    {"period": 4, "start": "13:30", "end": "14:55", "shift": 2},
    {"period": 5, "start": "15:00", "end": "16:25", "shift": 2},
    {"period": 6, "start": "16:55", "end": "18:20", "shift": 2},
    {"period": 7, "start": "18:25", "end": "19:50", "shift": 3},
    {"period": 8, "start": "19:55", "end": "21:20", "shift": 3},
]

SHIFT_LABELS = {1: '1 смена', 2: '2 смена', 3: '3 смена'}

# ---- Bell schedule presets ----

BELL_SCHEDULE_PRESETS = {
    'standard': {
        'name': 'Стандартный день',
        'description': 'Пары по 85 мин, перерывы 5-15 мин',
        'schedule': BELL_SCHEDULE,
    },
    'short': {
        'name': 'Сокращенный день (30 мин урок)',
        'description': 'Пары по 60 мин',
        'schedule': [
            {"period": 1, "start": "08:30", "end": "09:30", "shift": 1},
            {"period": 2, "start": "09:40", "end": "10:40", "shift": 1},
            {"period": 3, "start": "10:50", "end": "11:50", "shift": 1},
            {"period": 4, "start": "12:20", "end": "13:20", "shift": 2},
            {"period": 5, "start": "13:30", "end": "14:30", "shift": 2},
            {"period": 6, "start": "14:40", "end": "15:40", "shift": 2},
            {"period": 7, "start": "15:50", "end": "16:50", "shift": 3},
            {"period": 8, "start": "17:00", "end": "18:00", "shift": 3},
        ],
    },
    'saturday': {
        'name': 'Суббота',
        'description': '6 пар по 45 мин',
        'schedule': [
            {"period": 1, "start": "08:30", "end": "09:15", "shift": 1},
            {"period": 2, "start": "09:25", "end": "10:10", "shift": 1},
            {"period": 3, "start": "10:20", "end": "11:05", "shift": 1},
            {"period": 4, "start": "11:15", "end": "12:00", "shift": 1},
            {"period": 5, "start": "12:10", "end": "12:55", "shift": 1},
            {"period": 6, "start": "13:05", "end": "13:50", "shift": 1},
        ],
    },
}


def get_bell_schedule():
    """Актуальная схема звонков: из settings (ключ bell_schedule) или базовый BELL_SCHEDULE."""
    import json as _json
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT value FROM settings WHERE key = 'bell_schedule'").fetchone()
        conn.close()
        if row and row[0]:
            parsed = _json.loads(row[0])
            if (isinstance(parsed, list) and parsed
                    and all(isinstance(s, dict) and 'period' in s and 'start' in s and 'end' in s for s in parsed)):
                return parsed
    except Exception:
        pass
    return list(BELL_SCHEDULE)


def save_bell_schedule(slots):
    """Валидирует и сохраняет схему звонков в settings (ключ bell_schedule).
    Нормализует время к формату HH:MM, сортирует по номеру пары.
    Возвращает нормализованный список или бросает ValueError."""
    import json as _json
    import re as _re
    import sqlite3
    if not isinstance(slots, list) or not slots:
        raise ValueError("Схема звонков не может быть пустой")
    norm = []
    seen = set()
    for s in slots:
        if not isinstance(s, dict):
            raise ValueError("Каждый слот должен быть объектом с полями period, start, end")
        try:
            period = int(s.get('period'))
            shift = int(s.get('shift', 1))
        except (TypeError, ValueError):
            raise ValueError("Номер пары и смена должны быть целыми числами")
        start = str(s.get('start', '')).strip()
        end = str(s.get('end', '')).strip()
        if period < 1 or period > 8:
            raise ValueError("Номер пары должен быть от 1 до 8")
        if shift < 1:
            raise ValueError("Смена должна быть положительным числом")
        if not _re.fullmatch(r'(\d{1,2}):([0-5]\d)', start):
            raise ValueError(f"Неверное время начала пары {period}: {start!r} (ожидается HH:MM)")
        if not _re.fullmatch(r'(\d{1,2}):([0-5]\d)', end):
            raise ValueError(f"Неверное время окончания пары {period}: {end!r} (ожидается HH:MM)")
        sh, sm = map(int, start.split(':'))
        eh, em = map(int, end.split(':'))
        if sh > 23 or eh > 23:
            raise ValueError(f"Часы должны быть от 0 до 23 (пара {period})")
        if period in seen:
            raise ValueError(f"Пара {period} указана дважды")
        seen.add(period)
        norm.append({
            'period': period,
            'start': f'{sh:02d}:{sm:02d}',
            'end': f'{eh:02d}:{em:02d}',
            'shift': shift,
        })
    norm.sort(key=lambda s: s['period'])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('bell_schedule', ?, CURRENT_TIMESTAMP) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                 (_json.dumps(norm, ensure_ascii=False),))
    conn.commit()
    conn.close()
    return norm

# ---- Rate limiting ----

LOGIN_CLEANUP_INTERVAL = 300
