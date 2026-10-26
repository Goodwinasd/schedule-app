#!/bin/sh
# Инициализация перед стартом WSGI: миграции, справочники, аудит сирот.
# Планировщик бэкапов в контейнере живёт отдельным сервисом (см. docker-compose.yml).
set -e

python - <<'PY'
import logging
logging.basicConfig(level=logging.INFO)
from db import (
    run_alembic_upgrade, ensure_curriculum_table, seed_specialties,
    cleanup_orphan_schedule_records,
)
run_alembic_upgrade()
ensure_curriculum_table()
seed_specialties()
cleanup_orphan_schedule_records()
print("init: migrations and seed completed")
PY

exec "$@"
