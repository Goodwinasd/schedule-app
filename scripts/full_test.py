#!/usr/bin/env python3
import requests, json, sys
from datetime import datetime, timedelta

BASE = 'http://127.0.0.1:5000'
s = requests.Session()

passed, failed = 0, 0
results = []

def check(name, ok, detail=''):
    global passed, failed
    if ok:
        passed += 1
        print(f'  OK: {name}')
    else:
        failed += 1
        print(f'  FAIL: {name} — {detail}')
    results.append((name, ok))

def api(method, path, data=None):
    url = f'{BASE}/api{path}'
    if method == 'GET':
        return s.get(url)
    elif method == 'POST':
        return s.post(url, json=data or {})
    elif method == 'PUT':
        return s.put(url, json=data or {})
    elif method == 'DELETE':
        return s.delete(url)

def create_or_find(table, name, extra=None):
    r = api('GET', f'/{table}')
    if r.status_code == 200:
        items = r.json()
        if isinstance(items, list):
            for item in items:
                if item.get('name') == name:
                    return item['id']
    payload = {'name': name}
    if extra:
        payload.update(extra)
    r = api('POST', f'/{table}', payload)
    if r.status_code in (200, 201):
        return r.json().get('id')
    if r.status_code == 409:
        r = api('GET', f'/{table}')
        if r.status_code == 200:
            items = r.json()
            if isinstance(items, list):
                for item in items:
                    if item.get('name') == name:
                        return item['id']
    return None

print('=== Login ===')
r = api('POST', '/auth/login', {'password': 'admin123!'})
if r.status_code != 200:
    print(f'Login failed: {r.status_code} {r.text}')
    sys.exit(1)
csrf = r.json().get('csrf_token', '')
s.headers.update({'X-CSRF-Token': csrf})
print('OK')

ts = datetime.now().strftime('%H%M%S')

print('\n=== 1. Spravochniki ===')
teachers = {}
for name in [f'Ivanov_{ts}', f'Petrov_{ts}', f'Sidorova_{ts}']:
    tid = create_or_find('teachers', name)
    if tid: teachers[name] = tid
check('3 teachers', len(teachers) == 3, f'got {len(teachers)}')

subjects = {}
for name in [f'Math_{ts}', f'Phys_{ts}', f'Inf_{ts}', f'Chem_{ts}']:
    sid = create_or_find('subjects', name)
    if sid: subjects[name] = sid
check('4 subjects', len(subjects) == 4, f'got {len(subjects)}')

classrooms = {}
for name in [f'Rm1_{ts}', f'Rm2_{ts}', f'Rm3_{ts}']:
    cid = create_or_find('classrooms', name)
    if cid: classrooms[name] = cid
check('3 classrooms', len(classrooms) == 3, f'got {len(classrooms)}')

groups = {}
for name in [f'GroupA_{ts}', f'GroupB_{ts}']:
    gid = create_or_find('groups', name, {'course': 1})
    if gid: groups[name] = gid
check('2 groups', len(groups) == 2, f'got {len(groups)}')

# Map short names for lesson creation
tmap = dict(zip(['Ivanov','Petrov','Sidorova'], list(teachers.values())))
smap = dict(zip(['Math','Phys','Inf','Chem'], list(subjects.values())))
cmap = dict(zip(['Rm1','Rm2','Rm3'], list(classrooms.values())))
g1_id = list(groups.values())[0]
g1_name = list(groups.keys())[0]

print('\n=== 2. Week + Lessons ===')
monday_str = '2026-08-10'
r = api('POST', '/days/batch', {'days': [
    {'day_name': 'Monday', 'date': monday_str, 'group_name': g1_name},
    {'day_name': 'Tuesday', 'date': '2026-08-11', 'group_name': g1_name},
]})
if r.status_code == 201:
    ids = r.json().get('ids', [])
    day_id = ids[0] if ids else None
    check('Week created', bool(day_id))
else:
    r = api('POST', '/days', {'day_name': 'Monday', 'date': monday_str, 'group_name': g1_name})
    day_id = r.json().get('id') if r.status_code == 201 else None
    check('Week (single day)', r.status_code == 201, r.text)

if not day_id:
    print('Cannot continue without day')
    sys.exit(1)

lesson_ids = []
for period, subj, teach, room in [(1,'Math','Ivanov','Rm1'),(2,'Phys','Petrov','Rm2'),(3,'Inf','Sidorova','Rm3')]:
    r = api('POST', f'/days/{day_id}/lessons', {
        'period': period, 'subject_id': smap[subj], 'teacher_id': tmap[teach],
        'classroom_id': cmap[room], 'group_id': g1_id
    })
    if r.status_code == 201:
        lid = r.json().get('id')
        lesson_ids.append(lid)
        print(f'  Lesson {period}: OK id={lid}')
    else:
        print(f'  Lesson {period}: FAIL {r.status_code} {r.json()}')
check('3 lessons created', len(lesson_ids) == 3, f'got {len(lesson_ids)}')

if not lesson_ids:
    sys.exit(1)

print('\n=== 3. Conflict ===')
r = api('POST', f'/days/{day_id}/lessons', {
    'period': 1, 'subject_id': smap['Phys'], 'teacher_id': tmap['Ivanov'],
    'classroom_id': cmap['Rm2'], 'group_id': g1_id
})
check('Conflict blocked', r.status_code == 409, f'{r.status_code} {r.json()}')

print('\n=== 4. Edit lesson ===')
r = api('PUT', f'/lessons/{lesson_ids[0]}', {'period': 1, 'subject_id': smap['Chem'], 'teacher_id': tmap['Petrov'],
    'classroom_id': cmap['Rm2'], 'group_id': g1_id})
check('Lesson edited', r.status_code == 200, r.text)

print('\n=== 5. Delete lesson ===')
r = api('DELETE', f'/lessons/{lesson_ids[0]}')
check('Lesson deleted', r.status_code == 200, r.text)

print('\n=== 6. Trash ===')
r = api('GET', '/trash')
check('Trash loaded', r.status_code == 200)
if r.status_code == 200:
    trash = r.json()
    print(f'  Trash items: days={len(trash.get("days",[]))} lessons={len(trash.get("lessons",[]))}')

print('\n=== 7. Restore from trash ===')
r = api('POST', f'/lessons/{lesson_ids[0]}/restore')
check('Lesson restored', r.status_code == 200, r.text)
if r.status_code == 200:
    item = r.json().get('item', {})
    print(f'  Restored: {item.get("type")} — {item.get("subject_name") or item.get("name")}')

print('\n=== 8. Purge trash ===')
r = api('POST', '/db/purge-trash')
check('Trash purged', r.status_code == 200, r.text)

print('\n=== 9. Settings ===')
r = api('GET', '/settings')
check('Settings loaded', r.status_code == 200)
if r.status_code == 200:
    sets = r.json()
    print(f'  Settings: {dict(list(sets.items())[:4])}')
r = api('PUT', '/settings/session_lifetime', {'value': '7200'})
check('Setting updated', r.status_code == 200, r.text)
if r.status_code == 200:
    r = api('GET', '/settings')
    val = r.json().get('session_lifetime') if r.status_code == 200 else ''
    print(f'  session_lifetime = {val}')

print('\n=== 10. Schedule ===')
r = api('GET', '/schedule-table', {'group': g1_name, 'monday': monday_str})
check('Schedule loaded', r.status_code == 200, r.text)
if r.status_code == 200:
    data = r.json()
    print(f'  Days: {len(data.get("days",[]))}, Periods: {len(data.get("periods",[]))}')

print('\n' + '=' * 40)
total = passed + failed
pct = passed / total * 100 if total else 0
print(f'RESULTS: {passed}/{total} passed ({pct:.0f}%)')
if failed == 0:
    print('ALL TESTS PASSED')
else:
    print(f'{failed} FAILURE(S)')
    for name, ok in results:
        if not ok:
            print(f'  FAIL: {name}')
