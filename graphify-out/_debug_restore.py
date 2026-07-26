import sys, os
sys.path.insert(0, 'schedule-app')
os.environ['SCHEDULE_PASSWORD'] = 'TestPass123!'
os.environ['SCHEDULE_SECRET_KEY'] = 'test-secret'

import config
import db as db_module
import tempfile, json, sqlite3

tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
tmp.close()
config.DB_PATH = tmp.name
config.BACKUPS_DIR = tempfile.mkdtemp()
db_module.run_alembic_upgrade()

conn = db_module.get_db()
conn.execute("INSERT INTO schedule_days (id, day_name, date, sort_order, group_name) VALUES (1, 'Mon', '2026-09-07', 0, 'G1')")
conn.execute("INSERT INTO schedule_days (id, day_name, date, sort_order, group_name) VALUES (2, 'Tue', '2026-09-08', 1, 'G1')")
conn.execute("INSERT INTO schedule_days (id, day_name, date, sort_order, group_name) VALUES (3, 'Mon', '2026-09-14', 2, 'G1')")
conn.execute("INSERT INTO teachers (id, name) VALUES (1, 'T1')")
conn.execute("INSERT INTO teachers (id, name) VALUES (2, 'T2')")
conn.execute("INSERT INTO subjects (id, name) VALUES (1, 'Math')")
conn.execute("INSERT INTO subjects (id, name) VALUES (2, 'Phys')")
conn.execute("INSERT INTO classrooms_list (id, name) VALUES (1, '101')")
conn.execute("INSERT INTO classrooms_list (id, name) VALUES (2, '202')")
conn.execute("INSERT INTO groups_list (id, name, course, is_distance) VALUES (1, 'G1', 1, 0)")
conn.execute("INSERT INTO groups_list (id, name, course, is_distance) VALUES (2, 'G2', 1, 0)")
conn.execute("INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id) VALUES (1, 1, 1, 1, 1, 1, 1)")
conn.execute("INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id) VALUES (2, 1, 2, 2, 2, 2, 1)")
conn.commit()

# Create new day 4 + lesson (conflicting)
conn.execute("INSERT INTO schedule_days (id, day_name, date, sort_order, group_name) VALUES (4, 'Mon', '2026-09-07', 3, 'G2')")
conn.execute("INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id) VALUES (3, 4, 2, 1, 2, 1, 2)")
conn.commit()

# Delete day 1
conn.execute("UPDATE schedule_days SET deleted_at = datetime('now') WHERE id = 1")
conn.execute("UPDATE lessons SET deleted_at = datetime('now') WHERE day_id = 1")
conn.commit()

# Debug: check deleted lessons
day = conn.execute("SELECT id, day_name, date, group_name FROM schedule_days WHERE id = 1").fetchone()
print('Deleted day:', dict(day))

lessons = conn.execute("SELECT id, day_id, period, teacher_id, classroom_id FROM lessons WHERE day_id = 1 AND deleted_at IS NOT NULL").fetchall()
print(f'Lessons to restore: {len(lessons)}')

# Check for conflicts manually
for l in lessons:
    print(f'  Lesson {l["id"]}: period={l["period"]}, teacher={l["teacher_id"]}, classroom={l["classroom_id"]}')
    if l['teacher_id']:
        existing = conn.execute("""
            SELECT l.id, sd.day_name, sd.group_name FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.teacher_id = ? AND l.period = ? AND sd.date = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        """, (l['teacher_id'], l['period'], day['date'])).fetchall()
        print(f'    Teacher conflicts: {len(existing)}')
        for e in existing:
            print(f'      -> id={e["id"]}, day={e["day_name"]}, group={e["group_name"]}')
    if l['classroom_id']:
        existing = conn.execute("""
            SELECT l.id, sd.day_name, sd.group_name FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.classroom_id = ? AND l.period = ? AND sd.date = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        """, (l['classroom_id'], l['period'], day['date'])).fetchall()
        print(f'    Classroom conflicts: {len(existing)}')

# Also check: what active lessons exist for date 2026-09-07?
all_active = conn.execute("""
    SELECT l.id, l.period, l.teacher_id, l.classroom_id, sd.day_name, sd.group_name FROM lessons l
    JOIN schedule_days sd ON l.day_id = sd.id
    WHERE sd.date = '2026-09-07' AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
""").fetchall()
print(f'Active lessons on 2026-09-07: {len(all_active)}')
for a in all_active:
    print(f'  id={a["id"]}, period={a["period"]}, teacher={a["teacher_id"]}, classroom={a["classroom_id"]}, group={a["group_name"]}')

conn.close()
os.unlink(tmp.name)
print("\nDebug complete")
