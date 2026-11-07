"""Run a patch's tests in a separate process, in a network-less container when possible.

The child process only produces raw material: exit code, output, and a JUnit
XML report. Deciding pass/fail is left to the caller, in its own process.
"""

from __future__ import annotations

import contextlib
import functools
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SANDBOX_IMAGE = "swe-mini-bench-sandbox"
PYTEST_FLAGS = ("-q", "--tb=short", "-p", "no:cacheprovider")
MAX_REPORT_BYTES = 2_000_000

# The local fallback passes only these through, so the child does not inherit API
# keys or other secrets in its environment. That is not isolation: the child runs
# as the same user and can still read the parent's /proc/<pid>/environ on Linux
# and files in the home directory.
_LOCAL_ENV_KEEP = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG")


@dataclass
class Execution:
    sandbox: str  # "docker" or "local"
    exitcode: int | None  # None when the run was killed at the timeout
    stdout: str
    stderr: str
    junit_xml: str | None
    timed_out: bool


@functools.lru_cache(maxsize=None)
def docker_available(image: str = SANDBOX_IMAGE) -> bool:
    """True when a Docker daemon is reachable and ``image`` has been built."""
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def docker_command(
    workdir: Path, outdir: Path, *, image: str, name: str, pytest_args: Iterable[str] = ()
) -> list[str]:
    """``docker run`` with no network, a read-only filesystem and the inputs mounted read-only."""
    return [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "--read-only", "--tmpfs", "/tmp",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "512m", "--pids-limit", "128", "--cpus", "1",
        "-v", f"{workdir}:/work:ro",
        "-v", f"{outdir}:/out",
        "-w", "/work",
        image,
        "python", "-B", "-m", "pytest", *PYTEST_FLAGS,
        "--junitxml=/out/report.xml", *pytest_args, "/work",
    ]


def _local_command(workdir: Path, outdir: Path, pytest_args: Iterable[str]) -> list[str]:
    return [
        sys.executable, "-B", "-X", "utf8", "-m", "pytest", *PYTEST_FLAGS,
        f"--junitxml={outdir / 'report.xml'}", *pytest_args, str(workdir),
    ]


def execute(
    files: dict[str, str],
    *,
    sandbox: str = "auto",
    timeout_s: float = 60,
    image: str = SANDBOX_IMAGE,
    pytest_args: Iterable[str] = (),
) -> Execution:
    """Write ``files`` to a fresh directory and run pytest on it in a child process.

    ``sandbox`` is ``"docker"``, ``"local"``, or ``"auto"`` (Docker when the
    image is available, otherwise a local subprocess with a stripped environment).
    """
    if sandbox == "auto":
        sandbox = "docker" if docker_available(image) else "local"
    if sandbox not in ("docker", "local"):
        raise ValueError(f"unknown sandbox: {sandbox!r}")

    with tempfile.TemporaryDirectory(prefix="swe_", ignore_cleanup_errors=True) as td:
        workdir, outdir = Path(td) / "work", Path(td) / "out"
        workdir.mkdir()
        outdir.mkdir()
        for rel, text in files.items():
            (workdir / rel).write_text(text, encoding="utf-8")

        if sandbox == "docker":
            # The container runs as an unprivileged user.
            workdir.chmod(0o755)
            outdir.chmod(0o777)
            name = f"swe-mini-bench-{uuid.uuid4().hex[:12]}"
            cmd = docker_command(workdir, outdir, image=image, name=name, pytest_args=pytest_args)
            env = None
        else:
            name = ""
            cmd = _local_command(workdir, outdir, pytest_args)
            env = {k: os.environ[k] for k in _LOCAL_ENV_KEEP if k in os.environ}

        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            if name:
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
            return Execution(
                sandbox=sandbox,
                exitcode=None,
                stdout=_text(exc.stdout),
                stderr=_text(exc.stderr),
                junit_xml=None,
                timed_out=True,
            )

        report = outdir / "report.xml"
        junit_xml = None
        if report.is_file() and report.stat().st_size <= MAX_REPORT_BYTES:
            junit_xml = report.read_text(encoding="utf-8", errors="replace")
        return Execution(
            sandbox=sandbox,
            exitcode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            junit_xml=junit_xml,
            timed_out=False,
        )


def _text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data
