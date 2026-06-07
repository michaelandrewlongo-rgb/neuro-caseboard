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
