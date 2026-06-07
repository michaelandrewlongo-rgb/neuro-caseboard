from engine.query import QueryResult
from server.auth import expected_token, cookie_is_valid, login_page, COOKIE_NAME


def test_expected_token_is_deterministic_and_passcode_specific():
    assert expected_token("abc") == expected_token("abc")
    assert expected_token("abc") != expected_token("xyz")
    assert len(expected_token("abc")) == 64  # sha256 hex


def test_cookie_is_valid_logic():
    assert cookie_is_valid("anything", "") is True          # auth disabled
    assert cookie_is_valid("", "secret") is False           # no cookie
    assert cookie_is_valid("wrong", "secret") is False
    assert cookie_is_valid(expected_token("secret"), "secret") is True


def test_login_page_has_passcode_field():
    body = login_page().body.decode()
    assert 'name="passcode"' in body
    assert "neuro" in body.lower()
    assert "passcode" in login_page(error=True).body.decode().lower()


def _app(monkeypatch, passcode):
    import server.main as m
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m, "get_engine", lambda config=None: object())
    monkeypatch.setattr(m, "engine_query", lambda q, config=None: QueryResult(answer="ok"))
    monkeypatch.setattr(m.CONFIG, "app_passcode", passcode)
    return TestClient(m.app)


def test_open_when_no_passcode(monkeypatch):
    with _app(monkeypatch, "") as c:
        assert c.get("/healthz").status_code == 200
        assert c.post("/ask", json={"question": "x"}).status_code == 200


def test_gated_without_cookie(monkeypatch):
    with _app(monkeypatch, "letmein") as c:
        nav = c.get("/", follow_redirects=False)
        assert nav.status_code == 303 and nav.headers["location"] == "/login"
        assert c.post("/ask", json={"question": "x"}).status_code == 401
        assert c.get("/login").status_code == 200
        assert c.get("/healthz").status_code == 200   # liveness stays open


def test_service_worker_script_is_open(monkeypatch):
    # The SW script must be fetchable WITHOUT auth. A logged-out device's browser
    # checks /sw.js for updates; if that 303-redirects to /login it is an invalid
    # SW script and the update fails, so a stale cache-first worker can never be
    # replaced by the kill-switch worker. Keeping /sw.js open is what lets a
    # trapped device self-heal.
    with _app(monkeypatch, "letmein") as c:
        r = c.get("/sw.js", follow_redirects=False)
        assert r.status_code == 200
        assert "javascript" in r.headers["content-type"]


def test_login_flow_grants_access(monkeypatch):
    with _app(monkeypatch, "letmein") as c:
        bad = c.post("/login", data={"passcode": "nope"}, follow_redirects=False)
        assert bad.status_code == 200                  # login page re-shown
        assert COOKIE_NAME not in bad.cookies
        good = c.post("/login", data={"passcode": "letmein"}, follow_redirects=False)
        assert good.status_code == 303
        assert good.cookies.get(COOKIE_NAME)           # cookie set
        # TestClient keeps the cookie; gated route now works
        assert c.post("/ask", json={"question": "x"}).status_code == 200
