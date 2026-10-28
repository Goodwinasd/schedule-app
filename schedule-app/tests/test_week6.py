"""Неделя 6: несколько преподавателей у курсовой, консультация как разовое
событие, своё место у мероприятия вне сетки."""

from utils import LESSON_SELECT


def _h(csrf):
    return {'X-CSRF-Token': csrf}


def _insert_subject(db, name):
    conn = db.get_db()
    subject_id = conn.execute("INSERT INTO subjects (name) VALUES (?)", (name,)).lastrowid
    conn.commit()
    conn.close()
    return subject_id


def _room_id(db):
    conn = db.get_db()
    room = conn.execute('SELECT id FROM classrooms_list LIMIT 1').fetchone()['id']
    conn.close()
    return room


def _lesson_from_table(client, lesson_id):
    data = client.get('/api/schedule-table',
                      query_string={'group': 'Группа-1', 'monday': '2026-09-07'}).get_json()
    for period in data['periods']:
        for lessons in period['lessons'].values():
            for lesson in lessons:
                if lesson['id'] == lesson_id:
                    return lesson
    return None


def test_coursework_has_multiple_teachers(client, seed_lessons, db, admin_csrf):
    """Курсовая: основной преподаватель + дополнительные (текстом) в API;
    без дополнительных — предупреждение, но сохранение не блокируется."""
    h = _h(admin_csrf)
    subject_id = _insert_subject(db, 'Специальная техника')
    resp = client.post('/api/days/1/lessons', json={
        'period': 6, 'subject_id': subject_id, 'teacher_id': 1, 'classroom_id': _room_id(db),
        'group_id': 1, 'is_special_event': True, 'event_type': 'coursework',
        'additional_teachers': 'Петров П.П., Сидоров С.С.',
    }, headers=h)
    assert resp.status_code == 201, resp.get_json()
    lesson_id = resp.get_json()['id']
    assert resp.get_json()['warnings'] == []

    lesson = _lesson_from_table(client, lesson_id)
    assert lesson is not None
    assert lesson['additional_teachers'] == 'Петров П.П., Сидоров С.С.'

    # Частичный PUT, очищающий доп. преподавателей → warning (не блокер, код 200).
    resp = client.put(f'/api/lessons/{lesson_id}', json={'additional_teachers': ''}, headers=h)
    assert resp.status_code == 200, resp.get_json()
    assert any('Курсовая' in w for w in resp.get_json()['warnings'])
    assert _lesson_from_table(client, lesson_id)['additional_teachers'] is None


def test_consultation_is_special_event(client, seed_days, db, admin_csrf):
    """Консультация без чекбокса «Разовое» автоматически is_special_event=1
    и переживает очистку недели (генератор/удаление такие уроки не трогают)."""
    h = _h(admin_csrf)
    subject_id = _insert_subject(db, 'Консультация по праву')
    resp = client.post('/api/days/1/lessons', json={
        'period': 7, 'subject_id': subject_id, 'teacher_id': 1, 'classroom_id': _room_id(db),
        'group_id': 1, 'event_type': 'consultation',
    }, headers=h)
    assert resp.status_code == 201, resp.get_json()
    lesson_id = resp.get_json()['id']

    conn = db.get_db()
    row = conn.execute('SELECT is_special_event, event_type FROM lessons WHERE id = ?',
                       (lesson_id,)).fetchone()
    assert row['is_special_event'] == 1
    assert row['event_type'] == 'consultation'

    resp = client.delete('/api/week', query_string={
        'monday': '2026-09-07', 'target_type': 'group', 'target_id': 'Группа-1',
    }, headers=h)
    assert resp.status_code == 200, resp.get_json()
    row = conn.execute('SELECT deleted_at FROM lessons WHERE id = ?', (lesson_id,)).fetchone()
    conn.close()
    assert row['deleted_at'] is None


def test_week6_constraints(client, seed_days, db, admin_csrf):
    """Неделя 6: колонки миграции; мероприятие вне сетки хранит своё место,
    а экспорт печатает место вместо аудитории и время вне сетки."""
    h = _h(admin_csrf)
    conn = db.get_db()
    cols = {row[1] for row in conn.execute('PRAGMA table_info(lessons)')}
    assert {'additional_teachers', 'custom_room_name'} <= cols

    subject_id = _insert_subject(db, 'Музей МВД')
    resp = client.post('/api/days/1/lessons', json={
        'period': 3, 'subject_id': subject_id, 'teacher_id': 2, 'classroom_id': _room_id(db),
        'group_id': 1, 'is_special_event': True, 'event_type': 'event',
        'custom_start_time': '11:00', 'custom_end_time': '12:30',
        'custom_room_name': 'Музей МВД',
    }, headers=h)
    assert resp.status_code == 201, resp.get_json()
    lesson_id = resp.get_json()['id']
    assert _lesson_from_table(client, lesson_id)['custom_room_name'] == 'Музей МВД'

    row = conn.execute(LESSON_SELECT + ' WHERE l.id = ?', (lesson_id,)).fetchone()
    conn.close()
    from routes import _export_lesson_text
    text = _export_lesson_text(row)
    assert '11:00–12:30' in text
    assert 'Музей МВД' in text
    assert '101' not in text  # аудитория заменена местом
