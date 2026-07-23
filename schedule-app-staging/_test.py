import urllib.request, urllib.parse, http.cookiejar, json

BASE = 'http://127.0.0.1:5001'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def api(method, path, data=None):
    body = json.dumps(data).encode() if data else None
    url = BASE + path
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header('Content-Type', 'application/json')
    try:
        resp = opener.open(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except:
            return e.code, body.decode()

def api_get(path):
    url = BASE + path
    req = urllib.request.Request(url)
    resp = opener.open(req)
    return resp.status, json.loads(resp.read())

# Login
api('POST', '/api/auth/login', {'password': 'admin123'})

# Cleanup leftover groups
status, groups = api('GET', '/api/groups')
for g in groups:
    if '01-09/25' in g['name']:
        api('DELETE', '/api/groups/%d' % g['id'])
        print("Cleaned group: %s (id=%d)" % (g['name'], g['id']))

# Clean leftover days
status, days = api_get('/api/days')
for d in days:
    if '01-09/25' in (d.get('group_name') or ''):
        api('DELETE', '/api/days/%d' % d['id'])
        print("Cleaned day: id=%d" % d['id'])

print("Cleanup done. Running tests...")

# STEP 1: Create group
print("=" * 60)
print("STEP 1: Create group 'Gruppa 01-09/25'")
status, resp = api('POST', '/api/groups', {'name': 'Gruppa 01-09/25', 'course': 1})
print("  Status: %d, Response: %s" % (status, resp))
assert status == 201, "FAIL: expected 201, got %d" % status
group_id = resp['id']

# STEP 2: Case-insensitive duplicate
print("")
print("=" * 60)
print("STEP 2: Try create 'gruppa 01-09/25' (expect 400)")
status, resp = api('POST', '/api/groups', {'name': 'gruppa 01-09/25', 'course': 1})
print("  Status: %d, Response: %s" % (status, resp))
assert status == 400, "FAIL: expected 400, got %d" % status
print("  PASS: Duplicate correctly rejected")

# STEP 3: Create day
print("")
print("=" * 60)
print("STEP 3: Create day (Ponedelnik 2026-07-27)")
status, resp = api('POST', '/api/days', {'day_name': 'Ponedelnik', 'date': '2026-07-27', 'group_name': 'Gruppa 01-09/25'})
print("  Status: %d, Response: %s" % (status, resp))
assert status == 201, "FAIL: expected 201, got %d" % status
day_id = resp['id']

# STEP 4: Add lesson
print("")
print("=" * 60)
print("STEP 4: Add lesson (period 1)")
status, resp = api('POST', '/api/days/%d/lessons' % day_id, {
    'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'groups': 'Gruppa 01-09/25'
})
print("  Status: %d, Response: %s" % (status, resp))
assert status == 201, "FAIL: expected 201, got %d" % status
lesson_id = resp['id']

# STEP 5: Soft delete lesson
print("")
print("=" * 60)
print("STEP 5: DELETE lesson %d (soft delete)" % lesson_id)
status, resp = api('DELETE', '/api/lessons/%d' % lesson_id)
print("  Status: %d, Response: %s" % (status, resp))
assert status == 200, "FAIL: expected 200, got %d" % status

# STEP 6: Verify in trash
print("")
print("=" * 60)
print("STEP 6: Check trash (lesson should be there)")
status, resp = api('GET', '/api/trash')
print("  Status: %d" % status)
deleted_lessons = [l for l in resp.get('lessons', []) if l['id'] == lesson_id]
deleted_days = [d for d in resp.get('days', []) if d['id'] == day_id]
print("  Lesson %d in trash: %s" % (lesson_id, 'YES' if deleted_lessons else 'NO'))
print("  Day %d in trash: %s" % (day_id, 'YES' if deleted_days else 'NO'))
assert deleted_lessons, "FAIL: lesson %d not in trash" % lesson_id
assert not deleted_days, "FAIL: day %d should NOT be in trash yet" % day_id
print("  PASS")

# STEP 7: Restore lesson
print("")
print("=" * 60)
print("STEP 7: Restore lesson %d" % lesson_id)
status, resp = api('POST', '/api/lessons/%d/restore' % lesson_id)
print("  Status: %d, Response: %s" % (status, resp))
assert status == 200

# STEP 8: Verify lesson back
print("")
print("=" * 60)
print("STEP 8: Verify lesson restored")
grp_url = '/api/schedule-table?group=' + urllib.parse.quote('Gruppa 01-09/25') + '&monday=2026-07-27'
status, resp = api('GET', grp_url)
found = False
for p in resp.get('periods', []):
    for date, lesson in p.get('lessons', {}).items():
        if lesson and lesson.get('id') == lesson_id:
            found = True
            print("  Found lesson %d at period %d, %s" % (lesson_id, p['period'], date))
assert found, "FAIL: lesson %d not found in schedule" % lesson_id
print("  PASS")

# STEP 9: Soft delete day + cascade
print("")
print("=" * 60)
print("STEP 9: DELETE day %d (cascade soft delete)" % day_id)
status, resp = api('DELETE', '/api/days/%d' % day_id)
print("  Status: %d, Response: %s" % (status, resp))
assert status == 200

# STEP 10: Verify both in trash
print("")
print("=" * 60)
print("STEP 10: Check trash (day + lesson should both be there)")
status, resp = api('GET', '/api/trash')
deleted_days = [d for d in resp.get('days', []) if d['id'] == day_id]
deleted_lessons = [l for l in resp.get('lessons', []) if l['id'] == lesson_id]
print("  Day %d in trash: %s" % (day_id, 'YES' if deleted_days else 'NO'))
print("  Lesson %d in trash: %s" % (lesson_id, 'YES' if deleted_lessons else 'NO'))
assert deleted_days, "FAIL: day %d not in trash" % day_id
assert deleted_lessons, "FAIL: lesson %d not in trash" % lesson_id
print("  PASS")

# STEP 11: Restore day + cascade
print("")
print("=" * 60)
print("STEP 11: Restore day %d (cascade restore)" % day_id)
status, resp = api('POST', '/api/days/%d/restore' % day_id)
print("  Status: %d, Response: %s" % (status, resp))
assert status == 200

# STEP 12: Verify everything restored
print("")
print("=" * 60)
print("STEP 12: Verify day + lesson restored")
grp_url = '/api/schedule-table?group=' + urllib.parse.quote('Gruppa 01-09/25') + '&monday=2026-07-27'
status, resp = api('GET', grp_url)
found = False
for p in resp.get('periods', []):
    for date, lesson in p.get('lessons', {}).items():
        if lesson and lesson.get('id') == lesson_id:
            found = True
            print("  Found lesson %d at period %d, %s" % (lesson_id, p['period'], date))
assert found, "FAIL: lesson %d not found after day restore" % lesson_id
print("  PASS")

# Cleanup
print("")
print("=" * 60)
print("CLEANUP")
api('DELETE', '/api/lessons/%d' % lesson_id)
api('DELETE', '/api/days/%d' % day_id)
api('DELETE', '/api/groups/%d' % group_id)
print("  Done.")

print("")
print("=" * 60)
print("ALL TESTS PASSED")
