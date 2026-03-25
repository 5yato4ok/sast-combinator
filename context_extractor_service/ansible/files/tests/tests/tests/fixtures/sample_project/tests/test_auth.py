"""Test auth module — findings here should be classified as FP."""

SECRET_KEY = "hardcoded-test-secret-key-12345"
DB_PASSWORD = "test_password_not_real"


def test_login_success():
    password = "admin123"
    assert authenticate("admin", password) is True


def test_login_failure():
    assert authenticate("admin", "wrong") is False
