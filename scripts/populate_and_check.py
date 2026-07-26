#!/usr/bin/env python3
import requests, json, sys

BASE = 'http://127.0.0.1:5000'
s = requests.Session()

print('=== 1. Логин ===')
r = s.post(f'{BASE}/api/auth/login', json={'password': 'admin123!'})
if r.status_code != 200:
    print('Login failed:', r.text)
    sys.exit(1)
csrf = r.json().get('csrf_token', '')
s.headers.update({'X-CSRF-Token': csrf})
print(f'OK, csrf token obtained')

print('\n=== 2. Справочники ===')

def create_or_get(table, name, extra=None):
    r = s.get(f'{BASE}/api/{table}')
    if r.status_code == 200:
        items = r.json()
        if isinstance(items, list):
            for item in items:
                if item.get('name') == name:
                    print(f'  {table} "{name}": aktif id={item["id"]}')
                    return item['id']
    payload = {'name': name}
    if extra:
        payload.update(extra)
    r = s.post(f'{BASE}/api/{table}', json=payload)
    if r.status_code in (200, 201):
        rid = r.json().get('id')
        print(f'  {table} "{name}": created id={rid}')
        return rid
    if r.status_code == 409:
        # already exists but maybe soft-deleted - try to find by listing
        r = s.get(f'{BASE}/api/{table}')
        if r.status_code == 200:
            items = r.json()
            if isinstance(items, list):
                for item in items:
                    if item.get('name') == name:
                        print(f'  {table} "{name}": aktif (after 409) id={item["id"]}')
                        return item['id']
    print(f'  {table} "{name}": error {r.status_code}')
    return None

from datetime import datetime
ts = datetime.now().strftime('%H%M%S')

teachers = {}
for name in ['Иванов', 'Петров', 'Сидорова']:
    tid = create_or_get('teachers', f'{name}_{ts}')
    if tid:
        teachers[name] = tid

subjects = {}
for name in [f'Математика_{ts}', f'Физика_{ts}', f'Информатика_{ts}']:
    sid = create_or_get('subjects', name)
    if sid:
        subjects[name] = sid
# map short names for lesson creation
subj_short = {}
for full, short in zip(subjects.keys(), ['Математика', 'Физика', 'Информатика']):
    subj_short[short] = subjects[full]
teach_short = {}
for full, short in zip(teachers.keys(), ['Иванов', 'Петров', 'Сидорова']):
    teach_short[short] = teachers[full]
classrooms = {}
for name in [f'101_{ts}', f'202_{ts}', f'303_{ts}']:
    cid = create_or_get('classrooms', name)
    if cid:
        classrooms[name] = cid
class_short = {}
for full, short in zip(classrooms.keys(), ['101', '202', '303']):
    class_short[short] = classrooms[full]

group_ids = {}
for name in ['Группа 1', 'Группа 2']:
    gid = create_or_get('groups', name, {'course': 1})
    if gid:
        group_ids[name] = gid

print('\n=== 3. Неделя ===')
monday = '2026-08-03'
r = s.post(f'{BASE}/api/days/batch', json={'days': [
    {'day_name': 'Понедельник', 'date': monday, 'group_name': 'Группа 1'},
    {'day_name': 'Вторник', 'date': '2026-08-04', 'group_name': 'Группа 1'},
]})
if r.status_code == 201:
    day_ids = r.json().get('ids', [])
    print(f'Days created: {day_ids}')
    mon_id = day_ids[0] if day_ids else None
else:
    print(f'Batch failed ({r.status_code}), trying single day...')
    r = s.post(f'{BASE}/api/days', json={'day_name': 'Понедельник', 'date': monday, 'group_name': 'Группа 1'})
    if r.status_code == 201:
        mon_id = r.json().get('id')
        print(f'Single day created: id={mon_id}')
    else:
        print(f'Single day failed: {r.status_code} {r.json()}')
        sys.exit(1)

print('\n=== 4. Уроки ===')
lessons = [
    (1, subj_short['Математика'], teach_short['Иванов'], class_short['101'], 'Математика, Иванов, 101'),
    (2, subj_short['Физика'], teach_short['Петров'], class_short['202'], 'Физика, Петров, 202'),
    (3, subj_short['Информатика'], teach_short['Сидорова'], class_short['303'], 'Информатика, Сидорова, 303'),
]
gid = group_ids.get('Группа 1')
if not gid:
    print('ERROR: group not found')
    sys.exit(1)

for period, subj_id, teach_id, class_id, label in lessons:
    r = s.post(f'{BASE}/api/days/{mon_id}/lessons', json={
        'period': period, 'subject_id': subj_id, 'teacher_id': teach_id,
        'classroom_id': class_id, 'group_id': gid
    })
    status = 'OK id=' + str(r.json().get('id')) if r.status_code == 201 else f'FAIL {r.status_code} {r.json()}'
    print(f'  Lesson {label}: {status}')

print('\n=== 5. Конфликт ===')
r = s.post(f'{BASE}/api/days/{mon_id}/lessons', json={
    'period': 1, 'subject_id': subj_short['Физика'], 'teacher_id': teach_short['Иванов'],
    'classroom_id': class_short['202'], 'group_id': gid
})
if r.status_code == 409:
    print('OK: Conflict blocked (409)')
else:
    print(f'WARNING: No conflict! Status {r.status_code}: {r.json()}')

print('\n=== 6. Расписание ===')
r = s.get(f'{BASE}/api/schedule-table', params={'group': 'Группа 1', 'monday': monday})
if r.status_code == 200:
    data = r.json()
    days = data.get('days', [])
    periods = data.get('periods', [])
    print(f'Schedule: {len(days)} days, {len(periods)} periods')
    for p in periods:
        ls = p.get('lessons', {}).get(monday, [])
        for l in ls:
            print(f'  Period {p["period"]}: {l["subject"]} — {l["teacher"]} — {l["classroom"]}')
else:
    print(f'Error: {r.status_code} {r.json()}')

print('\n=== Проверка завершена ===')
