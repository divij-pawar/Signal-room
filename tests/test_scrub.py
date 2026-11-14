import pytest

from signalroom.common.scrub import REDACTED, scrub


@pytest.mark.parametrize("text, secret, kind", [
    ("Authorization: Bearer abcdef123456789xyz", "abcdef123456789xyz", "bearer"),
    ("key AKIAIOSFODNN7EXAMPLE used", "AKIAIOSFODNN7EXAMPLE", "aws_access_key"),
    ("using sk-or-v1-0123456789abcdef0123", "sk-or-v1-0123456789abcdef0123", "api_key"),
    ("token ghp_abcdefghijklmnopqrstuvwxyz123456", "ghp_abcdefghijklmnopqrstuvwxyz123456", "api_key"),
    ("postgres://app:S3cr3tPassw0rd@db:5432/shop", "S3cr3tPassw0rd", "url_credentials"),
    ('{"password": "hunter22"}', "hunter22", "key_value"),
    ("api_key=abc123def", "abc123def", "key_value"),
    ("jwt eyJhbGciOiJI.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4", "eyJhbGciOiJI", "jwt"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----", "MIIEow", "private_key"),
])
def test_secrets_are_redacted(text, secret, kind):
    result = scrub(text)
    assert secret not in result.text
    assert REDACTED in result.text
    assert result.counts[kind] >= 1


@pytest.mark.parametrize("text", [
    "password reset email sent to user 1234",
    "GET /api/products 200 in 42ms",
    "token bucket refilled",
    "https://example.com/path?q=1",
])
def test_normal_text_is_untouched(text):
    result = scrub(text)
    assert result.text == text
    assert result.redacted == 0


def test_scrub_is_idempotent():
    once = scrub("password=hunter22 and Bearer abcdef123456789").text
    assert scrub(once).text == once
