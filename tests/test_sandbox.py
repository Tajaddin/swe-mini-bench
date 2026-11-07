"""Sandbox selection and the Docker command line (Docker itself is not needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from swe_mini_bench import sandbox


def test_docker_command_isolates_the_run(tmp_path: Path) -> None:
    work, out = tmp_path / "work", tmp_path / "out"
    cmd = sandbox.docker_command(work, out, image="img", name="run-1")

    def value(flag: str) -> str:
        return cmd[cmd.index(flag) + 1]

    assert cmd[:3] == ["docker", "run", "--rm"]
    assert value("--network") == "none"
    assert "--read-only" in cmd
    assert value("--cap-drop") == "ALL"
    assert f"{work}:/work:ro" in cmd
    assert f"{out}:/out" in cmd
    assert "--junitxml=/out/report.xml" in cmd
    assert cmd[cmd.index("img") + 1 :][:4] == ["python", "-B", "-m", "pytest"]


def test_auto_falls_back_to_local_without_docker(monkeypatch) -> None:
    monkeypatch.setattr(sandbox, "docker_available", lambda image=sandbox.SANDBOX_IMAGE: False)
    run = sandbox.execute({"test_ok.py": "def test_ok():\n    pass\n"}, sandbox="auto")
    assert run.sandbox == "local"
    assert run.exitcode == 0
    assert 'name="test_ok"' in (run.junit_xml or "")


def test_unknown_sandbox_is_rejected() -> None:
    with pytest.raises(ValueError):
        sandbox.execute({}, sandbox="vm")
