from xavier.auth import LoginOutcome, _mask_email
from xavier.config import Settings, redact


def test_mask_email_long_local():
    assert _mask_email("kaick.xavier@meli.com") == "k**********r@meli.com"


def test_mask_email_short_local():
    assert _mask_email("ab@c.com") == "a*@c.com"


def test_mask_email_invalid():
    assert _mask_email("notanemail") == "***"


def test_login_outcome_values():
    # Garante que os enums não foram renomeados acidentalmente
    assert LoginOutcome.SUCCESS.value == "success"
    assert LoginOutcome.CAPTCHA.value == "captcha"
    assert LoginOutcome.TWO_FACTOR.value == "two_factor"
    assert LoginOutcome.INVALID_CREDENTIALS.value == "invalid_credentials"
    assert LoginOutcome.ALREADY_LOGGED_IN.value == "already_logged_in"


def test_settings_credentials_check():
    s = Settings(webhook_url=None, ml_email="x@y.com", ml_password="pw")
    assert s.has_ml_credentials
    s2 = Settings(webhook_url=None, ml_email="x@y.com", ml_password=None)
    assert not s2.has_ml_credentials
    s3 = Settings(webhook_url=None, ml_email=None, ml_password="pw")
    assert not s3.has_ml_credentials


def test_redact_does_not_leak_value():
    assert redact("super-secret") == "set"
    assert redact("") == "unset"
    assert redact(None) == "unset"
