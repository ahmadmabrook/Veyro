"""The disposable-Postgres harness fails closed (errors, never mocks or skips)
and keeps its credential out of docker's argv."""

from pathlib import Path

import pytest

from tests.harness.postgres import disposable_postgres


def test_missing_docker_is_an_error_not_a_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # no `docker` anywhere
    with pytest.raises(RuntimeError, match="never substitutes a mock"), disposable_postgres():
        pass


def test_superuser_password_never_in_docker_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "docker"
    fake.write_text('#!/bin/sh\necho "argv: $*" >&2\nexit 1\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(RuntimeError) as caught, disposable_postgres():
        pass
    msg = str(caught.value)
    assert "argv: run -d --rm" in msg  # the fake really received the call
    assert "-e POSTGRES_PASSWORD -p" in msg  # name only, value comes via env
    assert "POSTGRES_PASSWORD=" not in msg
