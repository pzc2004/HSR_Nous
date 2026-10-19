"""Isolated DeepSeek Harness headless process transport."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hsr_nous.common import repo_root, research_root

MODEL_ENV_KEYS = frozenset({
    "HSR_NOUS_LLM_AGENTS_API_KEY",
    "HSR_NOUS_LLM_AGENTS_MODEL",
    "HSR_NOUS_LLM_AGENTS_API_BASE",
})


class DshError(RuntimeError):
    pass


class DshTimeoutError(DshError):
    pass


@dataclass(frozen=True)
class DshResult:
    events: tuple[dict[str, Any], ...]
    returncode: int
    stderr: str

    @property
    def session_id(self) -> str | None:
        for event in self.events:
            if event.get("type") == "session" and isinstance(event.get("sessionId"), str):
                return event["sessionId"]
        return None

    @property
    def final_text(self) -> str:
        for event in reversed(self.events):
            if event.get("type") == "final" and isinstance(event.get("text"), str):
                return event["text"]
        return ""


def _prepare_root(root: Path | None) -> Path:
    resolved = (root or research_root()).resolve()
    repository = repo_root().resolve()
    if resolved == repository or resolved in repository.parents or repository in resolved.parents:
        raise DshError("research root must be disjoint from the repository")
    for path in (resolved, resolved / "home", resolved / "dsh-home"):
        path.mkdir(parents=True, exist_ok=True)
    return resolved


def _executable(dsh_bin: str | Path | None) -> str:
    configured = dsh_bin or os.environ.get("HSR_NOUS_DSH_BIN")
    if configured:
        return str(configured)
    local = repo_root() / "external" / "dsh" / "node_modules" / ".bin" / "dsh"
    return str(local) if local.is_file() else "dsh"


def _environment(
    root: Path,
    model_env: Mapping[str, str] | None,
) -> dict[str, str]:
    overrides = dict(model_env or {})
    unknown = set(overrides) - MODEL_ENV_KEYS
    if unknown:
        raise ValueError(f"unsupported model environment keys: {sorted(unknown)}")
    if any(not isinstance(value, str) or not value for value in overrides.values()):
        raise ValueError("model environment values must be non-empty strings")
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(root / "home"),
        "DSH_HOME": str(root / "dsh-home"),
        "DSH_PERMISSION_MODE": "read-only",
        "DSH_TELEMETRY_DISABLED": "1",
        "DSH_TOOLS_MODE": "native",
        "HSR_NOUS_RESEARCH_ROOT": str(root),
        "HSR_NOUS_PYTHON": sys.executable,
        "HSR_NOUS_PYTHONPATH": str(repo_root() / "src"),
        **overrides,
    }


def _signal(process: subprocess.Popen[str], sig: int) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, sig)
        elif sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except ProcessLookupError:
        pass


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        _signal(process, signal.SIGTERM)
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        _signal(process, signal.SIGKILL)
        process.communicate()


def _parse_events(stdout: str) -> tuple[dict[str, Any], ...]:
    events = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise DshError("DSH produced a malformed JSON event") from error
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise DshError("DSH produced an invalid JSON event")
        events.append(event)
    return tuple(events)


def run_headless(
    task: str,
    *,
    root: Path | None = None,
    dsh_bin: str | Path | None = None,
    timeout_s: float = 900,
    model_env: Mapping[str, str] | None = None,
    use_openai: bool | None = None,
) -> DshResult:
    if not task.strip():
        raise ValueError("task must be non-empty")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive and finite")
    workspace = _prepare_root(root)
    profile_dir = Path(__file__).parent / "dsh_profile"
    profiles = [profile_dir / "research.cordis.yml"]
    if use_openai is None:
        has_model_name = bool(model_env and model_env.get("HSR_NOUS_LLM_AGENTS_MODEL"))
        has_env_file = (repo_root() / ".env").is_file() or \
            (workspace / "dsh-home" / ".env").is_file()
        use_openai = has_model_name or has_env_file
    if use_openai:
        profiles.append(profile_dir / "openai.cordis.yml")
    argv = [_executable(dsh_bin), "--profile", "headless"]
    for profile in profiles:
        argv.extend(["--patch", str(profile)])
    argv.append("--json")
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=repo_root(),
            env=_environment(workspace, model_env),
            start_new_session=True,
        )
    except OSError as error:
        raise DshError(f"cannot start DSH: {error}") from error
    try:
        stdout, stderr = process.communicate(input=task, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _stop(process)
        raise DshTimeoutError(f"DSH exceeded {timeout_s:g}s") from None
    except BaseException:
        _stop(process)
        raise
    return DshResult(_parse_events(stdout), process.returncode, stderr)
