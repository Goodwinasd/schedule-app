import secrets


class TestCsrfToken:
    def test_get_csrf_token_creates_session(self, client):
        resp = client.get('/api/auth/csrf-token')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'csrf_token' in data
        assert len(data['csrf_token']) > 10

    def test_csrf_token_persists_in_session(self, client):
        resp = client.get('/api/auth/csrf-token')
        token1 = resp.get_json()['csrf_token']
        resp = client.get('/api/auth/csrf-token')
        token2 = resp.get_json()['csrf_token']
        assert token1 == token2


class TestLogin:
    def test_login_success(self, client):
        resp = client.post('/api/auth/login', json={'password': 'TestPass123!'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'csrf_token' in data
        with client.session_transaction() as sess:
            assert sess.get('is_admin') is True

    def test_login_wrong_password(self, client):
        resp = client.post('/api/auth/login', json={'password': 'wrong'})
        assert resp.status_code == 401
        data = resp.get_json()
        assert 'error' in data

    def test_login_no_csrf_required(self, client):
        resp = client.post('/api/auth/login', json={'password': 'TestPass123!'},
                           headers={'X-CSRF-Token': ''})
        assert resp.status_code == 200

    def test_login_rate_limiting(self, client):
        from config import LOGIN_RATE_LIMIT
        for _ in range(LOGIN_RATE_LIMIT):
            client.post('/api/auth/login', json={'password': 'wrong'})
        resp = client.post('/api/auth/login', json={'password': 'TestPass123!'})
        assert resp.status_code == 429


class TestLogout:
    def test_logout_clears_admin(self, client):
        with client.session_transaction() as sess:
            sess['is_admin'] = True
        resp = client.post('/api/auth/logout')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        with client.session_transaction() as sess:
            assert sess.get('is_admin') is None


class TestCheckAuth:
    def test_check_not_admin(self, client):
        resp = client.get('/api/auth/check')
        assert resp.status_code == 200
        assert resp.get_json()['is_admin'] is False

    def test_check_is_admin(self, client):
        with client.session_transaction() as sess:
            sess['is_admin'] = True
        resp = client.get('/api/auth/check')
        assert resp.get_json()['is_admin'] is True


class TestCsrfProtection:
    def test_write_endpoint_blocked_without_token(self, client):
        with client.session_transaction() as sess:
            sess['is_admin'] = True
            sess['csrf_token'] = 'real-token'
        resp = client.post('/api/subjects', json={'name': 'Test'})
        assert resp.status_code == 403
        assert 'CSRF' in resp.get_json().get('error', '')

    def test_write_endpoint_allowed_with_token(self, client, seed_refs):
        with client.session_transaction() as sess:
            sess['is_admin'] = True
            sess['csrf_token'] = 'real-token'
        resp = client.post('/api/subjects', json={'name': 'Test'},
                           headers={'X-CSRF-Token': 'real-token'})
        assert resp.status_code == 201

    def test_get_endpoint_no_csrf_check(self, client):
        resp = client.get('/api/subjects')
        assert resp.status_code == 200
