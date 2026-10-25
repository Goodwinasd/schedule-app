import pytest
import tempfile
import os
import sqlite3

from config import get_bell_schedule, save_bell_schedule, BELL_SCHEDULE, BELL_SCHEDULE_PRESETS
import config


@pytest.fixture
def bell_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    monkeypatch.setattr(config, 'DB_PATH', tmp.name)
    conn = sqlite3.connect(tmp.name)
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    conn.commit()
    conn.close()
    yield
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def test_public_bell_schedule_fallback(client):
    resp = client.get('/api/bell-schedule')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == len(BELL_SCHEDULE)
    assert data[0]['period'] == 1
    assert 'start' in data[0] and 'end' in data[0]


def test_admin_get_returns_schedule_and_presets(client, admin_csrf):
    resp = client.get('/api/admin/bell-schedule')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data['schedule'], list)
    assert len(data['schedule']) == len(BELL_SCHEDULE)
    keys = {p['id'] for p in data['presets']}
    assert 'short' in keys and 'saturday' in keys and 'standard' in keys


def test_admin_get_requires_auth(client):
    resp = client.get('/api/admin/bell-schedule')
    assert resp.status_code == 401


def test_admin_put_saves_schedule(client, admin_csrf):
    new_schedule = [
        {'period': 1, 'start': '9:05', 'end': '9:50', 'shift': 1},
        {'period': 2, 'start': '10:00', 'end': '10:45', 'shift': 1},
    ]
    resp = client.put('/api/admin/bell-schedule',
                      json={'schedule': new_schedule},
                      headers={'X-CSRF-Token': admin_csrf})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['schedule'][0]['start'] == '09:05'
    assert data['schedule'][0]['end'] == '09:50'

    public = client.get('/api/bell-schedule').get_json()
    assert len(public) == 2
    assert public[0]['start'] == '09:05'


def test_admin_put_requires_csrf(client, admin_csrf):
    resp = client.put('/api/admin/bell-schedule', json={'schedule': []})
    assert resp.status_code in (400, 403)


def test_admin_put_rejects_bad_time(client, admin_csrf):
    resp = client.put('/api/admin/bell-schedule',
                      json={'schedule': [{'period': 1, 'start': '25:00', 'end': '9:50', 'shift': 1}]},
                      headers={'X-CSRF-Token': admin_csrf})
    assert resp.status_code == 400


def test_admin_put_rejects_missing_schedule(client, admin_csrf):
    resp = client.put('/api/admin/bell-schedule',
                      json={},
                      headers={'X-CSRF-Token': admin_csrf})
    assert resp.status_code == 400


def test_apply_short_preset(bell_db):
    preset = BELL_SCHEDULE_PRESETS['short']
    norm = save_bell_schedule(preset['schedule'])
    assert len(norm) == 8
    assert norm[0]['start'] == '08:30'
    assert norm[-1]['end'] == '18:00'
    assert get_bell_schedule() == norm


def test_apply_saturday_preset(bell_db):
    preset = BELL_SCHEDULE_PRESETS['saturday']
    norm = save_bell_schedule(preset['schedule'])
    assert len(norm) == 6
    assert get_bell_schedule() == norm


def test_save_normalizes_and_sorts(bell_db):
    slots = [
        {'period': 2, 'start': '9:05', 'end': '9:50', 'shift': 2},
        {'period': 1, 'start': '8:00', 'end': '8:45', 'shift': 1},
    ]
    norm = save_bell_schedule(slots)
    assert [s['period'] for s in norm] == [1, 2]
    assert norm[0]['start'] == '08:00'
    assert norm[1]['start'] == '09:05'
    assert norm[1]['shift'] == 2


def test_save_rejects_duplicate_period(bell_db):
    with pytest.raises(ValueError):
        save_bell_schedule([
            {'period': 1, 'start': '08:00', 'end': '08:45', 'shift': 1},
            {'period': 1, 'start': '09:00', 'end': '09:45', 'shift': 1},
        ])


def test_save_rejects_period_out_of_range(bell_db):
    with pytest.raises(ValueError):
        save_bell_schedule([{'period': 9, 'start': '08:00', 'end': '08:45', 'shift': 1}])


def test_save_rejects_bad_time_format(bell_db):
    with pytest.raises(ValueError):
        save_bell_schedule([{'period': 1, 'start': '8-00', 'end': '08:45', 'shift': 1}])
    with pytest.raises(ValueError):
        save_bell_schedule([{'period': 1, 'start': '08:00', 'end': '8:70', 'shift': 1}])
    with pytest.raises(ValueError):
        save_bell_schedule([{'period': 1, 'start': '08:00', 'end': '24:00', 'shift': 1}])


def test_save_rejects_missing_fields(bell_db):
    with pytest.raises(ValueError):
        save_bell_schedule([{'period': 1, 'start': '08:00', 'shift': 1}])
    with pytest.raises(ValueError):
        save_bell_schedule([{'period': 1, 'start': '08:00', 'end': '08:45'}, 'not-a-dict'])


def test_save_default_shift_is_one(bell_db):
    norm = save_bell_schedule([{'period': 1, 'start': '08:00', 'end': '08:45'}])
    assert norm[0]['shift'] == 1


def test_restore_standard_preset(bell_db):
    save_bell_schedule(BELL_SCHEDULE_PRESETS['short']['schedule'])
    assert get_bell_schedule()[0]['start'] == '08:30'
    save_bell_schedule(BELL_SCHEDULE_PRESETS['standard']['schedule'])
    restored = get_bell_schedule()
    assert len(restored) == len(BELL_SCHEDULE)
    assert restored[0]['period'] == BELL_SCHEDULE[0]['period']
    assert restored[0]['shift'] == BELL_SCHEDULE[0]['shift']
    assert restored[0]['start'] == BELL_SCHEDULE[0]['start'].zfill(5)
    assert restored[0]['end'] == BELL_SCHEDULE[0]['end'].zfill(5)


def test_bell_schedule_flows_into_schedule_table(client, seed_refs, seed_days, admin_csrf):
    save_bell_schedule(BELL_SCHEDULE_PRESETS['short']['schedule'])
    resp = client.get('/api/schedule-table?group=%D0%93%D1%80%D1%83%D0%BF%D0%BF%D0%B0-1&monday=2026-09-07')
    assert resp.status_code == 200
    periods = resp.get_json().get('periods', [])
    assert periods[0]['start'] == '08:30'
    assert periods[-1]['end'] == '18:00'
