"""Direct checks for password_hash, check_password, and valid_email."""

import pytest

from app.security import CmsError, check_password, password_hash, valid_email

PASSWORD_MESSAGE = "Use a password of 12–128 characters."
EMAIL_MESSAGE = "Enter a valid email address."


def _reject_password(password):
    with pytest.raises(CmsError) as caught:
        password_hash(password)
    assert str(caught.value) == PASSWORD_MESSAGE


def _reject_email(value):
    with pytest.raises(CmsError) as caught:
        valid_email(value)
    assert str(caught.value) == EMAIL_MESSAGE


@pytest.mark.parametrize("length", [12, 64, 128], ids=["12", "64", "128"])
def test_password_hash_accepts_lengths_in_range(length):
    password = "a" * length
    stored = password_hash(password)
    scheme, salt, digest = stored.split("$")
    assert scheme == "scrypt"
    assert salt
    assert digest
    assert check_password(password, stored) is True


def test_password_hash_accepts_unicode_character_length():
    password = "א" * 80
    assert len(password) == 80
    assert len(password.encode()) > 128
    stored = password_hash(password)
    assert check_password(password, stored) is True


@pytest.mark.parametrize(
    "password",
    ["a" * 11, "", "a" * 129, None, 12, b"a" * 12, ["a" * 12]],
    ids=["11-chars", "empty", "129-chars", "none", "int", "bytes", "list"],
)
def test_password_hash_rejects_short_long_and_non_strings(password):
    _reject_password(password)


def test_check_password_accepts_matching_scrypt_digest():
    password = "correct-horse"
    stored = password_hash(password)
    other_encoding = password_hash(password)
    assert stored != other_encoding
    assert check_password(password, stored) is True
    assert check_password(password, other_encoding) is True
    assert check_password(password + "!", stored) is False


def truncate_tail(stored):
    return stored[:-1]


def drop_digest(stored):
    return stored.rsplit("$", 1)[0]


def swap_parts(stored):
    scheme, salt, digest = stored.split("$")
    return f"{scheme}${digest}${salt}"


def swap_hash(_stored):
    return password_hash("battery-staple-x")


def non_scrypt_prefix(stored):
    _, salt, digest = stored.split("$")
    return f"bcrypt${salt}${digest}"


def non_scrypt_literal(_stored):
    return "sha256$aa$bb"


@pytest.mark.parametrize(
    "mutate",
    [truncate_tail, drop_digest, swap_parts, swap_hash, non_scrypt_prefix, non_scrypt_literal],
    ids=[
        "truncated-tail",
        "truncated-missing-digest",
        "swapped-parts",
        "swapped-hash",
        "non-scrypt-prefix",
        "non-scrypt-literal",
    ],
)
def test_check_password_rejects_truncated_swapped_and_non_scrypt(mutate):
    password = "correct-horse"
    stored = password_hash(password)
    assert check_password(password, mutate(stored)) is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("editor@example.com", "editor@example.com"),
        ("  Editor@Example.COM ", "editor@example.com"),
        ("שלום@example.com", "שלום@example.com"),
        ("שלום@Example.COM", "שלום@example.com"),
        ("a" * 242 + "@example.com", "a" * 242 + "@example.com"),
    ],
    ids=["simple", "normalized", "hebrew-local", "hebrew-local-normalized", "254-chars"],
)
def test_valid_email_accepts_well_formed_addresses(raw, expected):
    assert len(raw.strip()) <= 254
    assert valid_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "a" * 243 + "@example.com",
        "editor.example.com",
        "editor@localhost",
        "editor@example",
        "editor@example.com\n",
        "editor\n@example.com",
        "edi\ntor@example.com",
        "editor@example.com\r\n",
        "editor@exam\rple.com",
        "a@b@example.com",
        "editor@example.com@other.test",
    ],
    ids=[
        "empty",
        "whitespace",
        "255-chars",
        "missing-at",
        "missing-domain-dot-localhost",
        "missing-domain-dot",
        "trailing-newline",
        "newline-before-at",
        "newline-in-local",
        "crlf",
        "carriage-return",
        "multiple-at",
        "multiple-at-dotted",
    ],
)
def test_valid_email_rejects_empty_long_and_malformed(raw):
    _reject_email(raw)
