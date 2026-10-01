"""Fail immediately if a test tries real HTTP instead of a mock transport."""

import httpx
import pytest


@pytest.fixture(autouse=True)
def disable_external_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Backend tests must not use the internet")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
