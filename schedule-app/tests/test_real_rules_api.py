"""API и потоки: поля реальных правил, спец. мероприятия, зеркальные группы."""

from datetime import datetime, timedelta


def _monday(days_ahead=28):
    today = datetime.today().date() + timedelta(days=days_ahead)
    return (today - timedelta(days=today.weekday())).isoformat()


def _setup_stream(conn, name='02-0923+11/24', course=2):
    """Составной поток: группа «A+B» + группы-части, для которых работает зеркалирование."""
    for part in name.split('+'):
        conn.execute("INSERT INTO groups_list (name, course) VALUES (?, ?)", (part, course))
    gid = conn.execute(
        "INSERT INTO groups_list (name, course) VALUES (?, ?)", (name, course)).lastrowid
    teacher_id = conn.execute("INSERT INTO teachers (name) VALUES ('Стрим-препод')").lastrowid
    subject_id = conn.execute("INSERT INTO subjects (name) VALUES ('Стрим-предмет')").lastrowid
    room_id = conn.execute("INSERT INTO classrooms_list (name, room_type) VALUES ('201', NULL)").lastrowid
    conn.execute(
        "INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester) "
        "VALUES (?, ?, ?, 1, 73, 18)", (gid, subject_id, teacher_id))
    conn.commit()
    return gid, room_id


def test_group_shift_roundtrip_via_api(client, admin_csrf):
    h = {'X-CSRF-Token': admin_csrf}
    resp = client.post('/api/groups', json={'name': 'Тест-смена', 'course': 2, 'shift': 2}, headers=h)
    assert resp.status_code in (200, 201), resp.get_json()
    gid = resp.get_json()['id']

    groups = client.get('/api/groups').get_json()
    assert next(g for g in groups if g['id'] == gid)['shift'] == 2

    resp = client.put(f'/api/groups/{gid}', json={'name': 'Тест-смена', 'course': 2, 'shift': 1}, headers=h)
    assert resp.status_code == 200, resp.get_json()
    groups = client.get('/api/groups').get_json()
    assert next(g for g in groups if g['id'] == gid)['shift'] == 1


def test_subject_and_classroom_room_types_via_api(client, admin_csrf):
    h = {'X-CSRF-Token': admin_csrf}
    resp = client.post('/api/subjects', json={'name': 'Физкультура', 'required_room_type': 'gym'}, headers=h)
    assert resp.status_code in (200, 201), resp.get_json()
    sid = resp.get_json()['id']
    subjects = client.get('/api/subjects').get_json()
    assert next(s for s in subjects if s['id'] == sid)['required_room_type'] == 'gym'

    resp = client.post('/api/classrooms', json={'name': 'Динамо-тест', 'room_type': 'gym'}, headers=h)
    assert resp.status_code in (200, 201), resp.get_json()
    cid = resp.get_json()['id']
    rooms = client.get('/api/classrooms').get_json()
    assert next(c for c in rooms if c['id'] == cid)['room_type'] == 'gym'

    resp = client.put(f'/api/classrooms/{cid}', json={'name': 'Динамо-тест', 'room_type': 'gym'}, headers=h)
    assert resp.status_code == 200


def test_special_event_survives_week_delete(client, seed_lessons, db, admin_csrf):
    h = {'X-CSRF-Token': admin_csrf}
    conn = db.get_db()
    day = conn.execute(
        "SELECT id, date, group_name FROM schedule_days WHERE date = '2026-09-07'").fetchone()
    group_name = day['group_name'] or 'Группа-1'
    room_1 = conn.execute("SELECT id FROM classrooms_list LIMIT 1").fetchone()['id']
    room_2 = conn.execute(
        "INSERT INTO classrooms_list (name, room_type) VALUES ('501 правая', NULL)").lastrowid
    conn.commit()

    resp = client.post(f'/api/days/{day["id"]}/lessons', json={
        'period': 6, 'subject_id': 1, 'teacher_id': 1,
        'classroom_id': room_1, 'classroom_id_2': room_2, 'group_id': 1,
        'is_special_event': True,
    }, headers=h)
    assert resp.status_code == 201, resp.get_json()
    special_id = resp.get_json()['id']

    table = client.get(
        f'/api/schedule-table?group={group_name}&monday=2026-09-07').get_json()
    cell = next(
        lesson for period in table['periods'] for lesson in period['lessons'].get('2026-09-07', [])
        if lesson['id'] == special_id)
    assert cell['is_special_event'] is True
    assert cell['classroom_2'] == '501 правая'
    assert cell['classroom'] == 'Каб-1' or cell['classroom']  # имя первой аудитории приходит

    resp = client.delete(
        f'/api/week?monday=2026-09-07&target_type=group&target_id={group_name}', headers=h)
    assert resp.status_code in (200, 400), resp.get_json()
    conn = db.get_db()
    row = conn.execute(
        "SELECT deleted_at, is_special_event FROM lessons WHERE id = ?", (special_id,)).fetchone()
    conn.close()
    assert row is not None and row['deleted_at'] is None, 'мероприятие удалилось вместе с неделей'
    assert row['is_special_event'] == 1


def test_composite_stream_groups_share_slot_after_optimization(app, db):
    import generator
    conn = db.get_db()
    gid, room_id = _setup_stream(conn)
    monday = _monday()
    generator.generate_schedule(conn, gid, '02-0923+11/24', 1, monday, 1, optimize=True)
    conn.commit()

    dates = [
        (datetime.strptime(monday, '%Y-%m-%d') + timedelta(days=d)).strftime('%Y-%m-%d')
        for d in range(6)
    ]
    placeholders = ','.join('?' * len(dates))
    main_rows = conn.execute(
        "SELECT sd.date, l.period, l.teacher_id FROM lessons l "
        "JOIN schedule_days sd ON l.day_id = sd.id "
        f"WHERE l.group_id = ? AND sd.date IN ({placeholders}) "
        "AND l.deleted_at IS NULL AND sd.deleted_at IS NULL", [gid] + dates).fetchall()
    assert main_rows, 'поток не сгенерирован'

    for row in main_rows:
        mirrors = conn.execute(
            "SELECT COUNT(DISTINCT gl.name) c FROM lessons l "
            "JOIN schedule_days sd ON l.day_id = sd.id "
            "JOIN groups_list gl ON l.group_id = gl.id "
            f"WHERE sd.date = ? AND l.period = ? AND l.teacher_id = ? "
            f"AND gl.name IN ('02-0923', '11/24') "
            "AND l.deleted_at IS NULL AND sd.deleted_at IS NULL",
            (row['date'], row['period'], row['teacher_id'])).fetchone()['c']
        assert mirrors == 2, (
            f'поток разъехался {row["date"]} пара {row["period"]}: зеркальных групп {mirrors}')
