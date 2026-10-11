from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import accounts


def request_with_attempts(attempts):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(login_attempts=attempts)))


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(accounts.time, "monotonic", lambda: 100)


def test_eight_attempts_allowed_and_rejection_leaves_history_unchanged():
    attempts = {"login:client": [0]}
    request = request_with_attempts(attempts)
    for _ in range(8):
        assert accounts.rate_limit("login:client", request) is None
    assert attempts == {"login:client": [100] * 8}

    history = attempts["login:client"]
    history.insert(0, 0)
    with pytest.raises(HTTPException) as error:
        accounts.rate_limit("login:client", request)
    assert error.value.status_code == 429
    assert error.value.detail == "Too many attempts. Try again in a minute."
    assert attempts["login:client"] is history
    assert history == [0, *([100] * 8)]


def test_accepted_attempt_prunes_timestamps_at_the_exact_window_boundary():
    attempts = {"setup:client": [39, 40, 40.001, 99]}
    accounts.rate_limit("setup:client", request_with_attempts(attempts))
    assert attempts == {"setup:client": [40.001, 99, 100]}


def test_attempt_budgets_are_independent_for_each_key():
    attempts = {}
    request = request_with_attempts(attempts)
    for key in ("login:client", "setup:client", "login:other"):
        for _ in range(8):
            accounts.rate_limit(key, request)
    with pytest.raises(HTTPException):
        accounts.rate_limit("login:client", request)
    assert attempts == {key: [100] * 8 for key in ("login:client", "setup:client", "login:other")}


@pytest.mark.parametrize("key_count", [10000, 10001])
def test_expired_key_cleanup_requires_exceeding_threshold_and_window(key_count):
    attempts = {f"key:{i}": [100] for i in range(key_count - 3)}
    attempts.update({"expired": [39], "boundary": [40], "active": [100]})
    accounts.rate_limit("active", request_with_attempts(attempts))
    assert attempts["active"] == [100, 100]
    assert attempts["boundary"] == [40]
    assert ("expired" in attempts) is (key_count == 10000)
    assert len(attempts) == 10000
    assert all(attempts[f"key:{i}"] == [100] for i in range(key_count - 3))


def test_rejected_attempt_does_not_clean_up_expired_keys():
    attempts = {f"key:{i}": [100] for i in range(9999)}
    attempts.update({"expired": [0], "login:client": [100] * 8})
    before = {key: list(history) for key, history in attempts.items()}
    with pytest.raises(HTTPException):
        accounts.rate_limit("login:client", request_with_attempts(attempts))
    assert attempts == before


def test_clock_is_read_while_attempt_lock_is_held(monkeypatch):
    clock_calls = []

    def clock():
        assert accounts._attempt_lock.locked()
        clock_calls.append(True)
        return 100

    monkeypatch.setattr(accounts.time, "monotonic", clock)
    attempts = {}
    accounts.rate_limit("accept:client", request_with_attempts(attempts))
    assert clock_calls == [True]
    assert attempts == {"accept:client": [100]}
    assert not accounts._attempt_lock.locked()
