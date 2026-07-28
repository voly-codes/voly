"""Versioned golden datasets and deterministic offline regression replay."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

GOLDEN_SCHEMA_VERSION = 1
GOLDEN_REPORT_SCHEMA_VERSION = 1
VALID_CASE_CATEGORIES = frozenset({"typical", "edge", "adversarial"})
MAX_CASES = 1000
MAX_TIMEOUT_SECONDS = 300
MAX_OUTPUT_CHARS = 20_000
MAX_EXPECTED_FILE_BYTES = 1_000_000

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ROOT_KEYS = frozenset(
    {"schema_version", "dataset_id", "version", "description", "cases"}
)
_CASE_KEYS = frozenset(
    {"id", "category", "description", "fixture", "argv", "timeout_seconds", "expected"}
)
_EXPECTED_KEYS = frozenset(
    {
        "exit_code",
        "stdout_contains",
        "stdout_not_contains",
        "stderr_contains",
        "stderr_not_contains",
        "files",
    }
)
_FILE_KEYS = frozenset({"path", "exists", "sha256", "contains"})


class GoldenDatasetError(ValueError):
    """Raised when a golden dataset is malformed or unsafe."""


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GoldenDatasetError(f"{where} must be an object")
    return value


def _known_keys(value: dict[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GoldenDatasetError(f"{where} has unknown keys: {unknown}")


def _safe_id(value: Any, where: str) -> str:
    normalized = str(value or "").strip()
    if not _ID_RE.fullmatch(normalized):
        raise GoldenDatasetError(
            f"{where} must contain 1-128 ASCII letters, digits, '.', '_' or '-'"
        )
    return normalized


def _relative_path(value: Any, where: str) -> str:
    raw = str(value or "").strip()
    if not raw or "\\" in raw:
        raise GoldenDatasetError(f"{where} must be a non-empty forward-slash relative path")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise GoldenDatasetError(f"{where} must stay inside the dataset")
    return path.as_posix()


def _string_list(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise GoldenDatasetError(f"{where} must be an array of strings")
    if any(not item for item in value):
        raise GoldenDatasetError(f"{where} entries must not be empty")
    return tuple(value)


@dataclass(frozen=True)
class GoldenFileExpectation:
    path: str
    exists: bool = True
    sha256: str = ""
    contains: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Any, where: str) -> GoldenFileExpectation:
        data = _mapping(value, where)
        _known_keys(data, _FILE_KEYS, where)
        exists = data.get("exists", True)
        if not isinstance(exists, bool):
            raise GoldenDatasetError(f"{where}.exists must be a boolean")
        digest = str(data.get("sha256") or "").lower()
        if digest and not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise GoldenDatasetError(f"{where}.sha256 must be a lowercase SHA-256 digest")
        contains = _string_list(data.get("contains"), f"{where}.contains")
        if not exists and (digest or contains):
            raise GoldenDatasetError(
                f"{where} cannot combine exists=false with sha256 or contains"
            )
        return cls(
            path=_relative_path(data.get("path"), f"{where}.path"),
            exists=exists,
            sha256=digest,
            contains=contains,
        )


@dataclass(frozen=True)
class GoldenExpectation:
    exit_code: int = 0
    stdout_contains: tuple[str, ...] = ()
    stdout_not_contains: tuple[str, ...] = ()
    stderr_contains: tuple[str, ...] = ()
    stderr_not_contains: tuple[str, ...] = ()
    files: tuple[GoldenFileExpectation, ...] = ()

    @classmethod
    def from_dict(cls, value: Any, where: str) -> GoldenExpectation:
        data = _mapping(value, where)
        _known_keys(data, _EXPECTED_KEYS, where)
        exit_code = data.get("exit_code", 0)
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise GoldenDatasetError(f"{where}.exit_code must be an integer")
        raw_files = data.get("files") or []
        if not isinstance(raw_files, list):
            raise GoldenDatasetError(f"{where}.files must be an array")
        files = tuple(
            GoldenFileExpectation.from_dict(item, f"{where}.files[{index}]")
            for index, item in enumerate(raw_files)
        )
        paths = [item.path for item in files]
        if len(paths) != len(set(paths)):
            raise GoldenDatasetError(f"{where}.files contains duplicate paths")
        return cls(
            exit_code=exit_code,
            stdout_contains=_string_list(
                data.get("stdout_contains"), f"{where}.stdout_contains"
            ),
            stdout_not_contains=_string_list(
                data.get("stdout_not_contains"), f"{where}.stdout_not_contains"
            ),
            stderr_contains=_string_list(
                data.get("stderr_contains"), f"{where}.stderr_contains"
            ),
            stderr_not_contains=_string_list(
                data.get("stderr_not_contains"), f"{where}.stderr_not_contains"
            ),
            files=files,
        )


@dataclass(frozen=True)
class GoldenCase:
    id: str
    category: str
    description: str
    fixture: str
    argv: tuple[str, ...]
    timeout_seconds: int
    expected: GoldenExpectation

    @classmethod
    def from_dict(cls, value: Any, index: int) -> GoldenCase:
        where = f"cases[{index}]"
        data = _mapping(value, where)
        _known_keys(data, _CASE_KEYS, where)
        category = str(data.get("category") or "").strip()
        if category not in VALID_CASE_CATEGORIES:
            raise GoldenDatasetError(
                f"{where}.category must be one of {sorted(VALID_CASE_CATEGORIES)}"
            )
        raw_argv = data.get("argv")
        if (
            not isinstance(raw_argv, list)
            or not raw_argv
            or any(not isinstance(item, str) or not item for item in raw_argv)
        ):
            raise GoldenDatasetError(f"{where}.argv must be a non-empty array of strings")
        timeout = data.get("timeout_seconds", 60)
        if (
            not isinstance(timeout, int)
            or isinstance(timeout, bool)
            or not 1 <= timeout <= MAX_TIMEOUT_SECONDS
        ):
            raise GoldenDatasetError(
                f"{where}.timeout_seconds must be in 1..{MAX_TIMEOUT_SECONDS}"
            )
        return cls(
            id=_safe_id(data.get("id"), f"{where}.id"),
            category=category,
            description=str(data.get("description") or "").strip(),
            fixture=_relative_path(data.get("fixture"), f"{where}.fixture"),
            argv=tuple(raw_argv),
            timeout_seconds=timeout,
            expected=GoldenExpectation.from_dict(data.get("expected"), f"{where}.expected"),
        )


@dataclass(frozen=True)
class GoldenDataset:
    schema_version: int
    dataset_id: str
    version: str
    description: str
    cases: tuple[GoldenCase, ...]
    path: Path = field(compare=False)
    fingerprint: str = field(compare=False)


def _dataset_fingerprint(
    data: dict[str, Any],
    base: Path,
    cases: tuple[GoldenCase, ...],
) -> str:
    encoded = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(encoded)
    for relative in sorted({case.fixture for case in cases}):
        fixture = _resolved_child(base, relative, f"fixture {relative}")
        digest.update(b"\0fixture\0")
        digest.update(relative.encode("utf-8"))
        for item in sorted(path for path in fixture.rglob("*") if path.is_file()):
            digest.update(b"\0file\0")
            digest.update(item.relative_to(fixture).as_posix().encode("utf-8"))
            digest.update(b"\0")
            with item.open("rb") as handle:
                for chunk in iter(lambda: handle.read(64 * 1024), b""):
                    digest.update(chunk)
    return digest.hexdigest()


def _resolved_child(base: Path, relative: str, where: str) -> Path:
    root = base.resolve()
    target = (root / Path(relative)).resolve()
    if target == root or root not in target.parents:
        raise GoldenDatasetError(f"{where} must resolve below {root}")
    return target


def _reject_symlinks(root: Path, where: str) -> None:
    if root.is_symlink():
        raise GoldenDatasetError(f"{where} must not be a symlink")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise GoldenDatasetError(f"{where} contains symlink: {path.relative_to(root)}")


def load_golden_dataset(path: str | Path) -> GoldenDataset:
    """Load and strictly validate one versioned JSON golden dataset."""
    dataset_path = Path(path)
    try:
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoldenDatasetError(f"cannot read golden dataset {dataset_path}: {exc}") from exc
    root = _mapping(data, "dataset")
    _known_keys(root, _ROOT_KEYS, "dataset")
    if root.get("schema_version") != GOLDEN_SCHEMA_VERSION:
        raise GoldenDatasetError(
            f"dataset.schema_version must be {GOLDEN_SCHEMA_VERSION}"
        )
    version = _safe_id(root.get("version"), "dataset.version")
    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise GoldenDatasetError("dataset.cases must be a non-empty array")
    if len(raw_cases) > MAX_CASES:
        raise GoldenDatasetError(f"dataset.cases exceeds {MAX_CASES} entries")
    cases = tuple(GoldenCase.from_dict(item, index) for index, item in enumerate(raw_cases))
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise GoldenDatasetError("dataset.cases contains duplicate ids")

    base = dataset_path.parent
    for case in cases:
        fixture = _resolved_child(base, case.fixture, f"case {case.id} fixture")
        if not fixture.is_dir():
            raise GoldenDatasetError(f"case {case.id} fixture is not a directory: {case.fixture}")
        _reject_symlinks(fixture, f"case {case.id} fixture")

    return GoldenDataset(
        schema_version=GOLDEN_SCHEMA_VERSION,
        dataset_id=_safe_id(root.get("dataset_id"), "dataset.dataset_id"),
        version=version,
        description=str(root.get("description") or "").strip(),
        cases=cases,
        path=dataset_path.resolve(),
        fingerprint=_dataset_fingerprint(root, base, cases),
    )


def _tail(path: Path, max_chars: int = MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_chars * 4:
            handle.seek(-max_chars * 4, os.SEEK_END)
        value = handle.read().decode("utf-8", errors="replace")
    truncated = len(value) > max_chars or size > max_chars * 4
    return value[-max_chars:], truncated


def _resolved_argv(argv: tuple[str, ...]) -> list[str]:
    return [sys.executable if item == "{python}" else item for item in argv]


def _sanitized_env(temp_dir: str) -> dict[str, str]:
    """Keep runtime essentials while excluding credentials from replay cases."""
    allowed = {
        "CI",
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TERM",
        "WINDIR",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    isolated_home = str(Path(temp_dir) / "home")
    isolated_tmp = str(Path(temp_dir) / "tmp")
    Path(isolated_home).mkdir()
    Path(isolated_tmp).mkdir()
    env.update(
        {
            "HOME": isolated_home,
            "USERPROFILE": isolated_home,
            "TMP": isolated_tmp,
            "TEMP": isolated_tmp,
            "TMPDIR": isolated_tmp,
        }
    )
    return env


def _file_check(root: Path, expected: GoldenFileExpectation) -> dict[str, Any]:
    try:
        target = _resolved_child(root, expected.path, f"expected file {expected.path}")
    except GoldenDatasetError as exc:
        return {"id": f"file:{expected.path}", "passed": False, "message": str(exc)}
    present = target.is_file()
    if present != expected.exists:
        state = "exist" if expected.exists else "be absent"
        return {
            "id": f"file:{expected.path}",
            "passed": False,
            "message": f"expected file to {state}",
        }
    if not expected.exists:
        return {
            "id": f"file:{expected.path}",
            "passed": True,
            "message": "file is absent",
        }
    if target.stat().st_size > MAX_EXPECTED_FILE_BYTES and expected.contains:
        return {
            "id": f"file:{expected.path}",
            "passed": False,
            "message": f"file exceeds {MAX_EXPECTED_FILE_BYTES} bytes for content checks",
        }
    if expected.sha256:
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != expected.sha256:
            return {
                "id": f"file:{expected.path}",
                "passed": False,
                "message": "SHA-256 mismatch",
            }
    if expected.contains:
        content = target.read_text(encoding="utf-8", errors="replace")
        missing = [needle for needle in expected.contains if needle not in content]
        if missing:
            return {
                "id": f"file:{expected.path}",
                "passed": False,
                "message": f"missing {len(missing)} expected content fragment(s)",
            }
    return {
        "id": f"file:{expected.path}",
        "passed": True,
        "message": "file expectation matched",
    }


def _text_checks(stream: str, name: str, present: tuple[str, ...], absent: tuple[str, ...]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for index, needle in enumerate(present):
        checks.append(
            {
                "id": f"{name}:contains:{index}",
                "passed": needle in stream,
                "message": "expected fragment found" if needle in stream else "expected fragment missing",
            }
        )
    for index, needle in enumerate(absent):
        checks.append(
            {
                "id": f"{name}:not_contains:{index}",
                "passed": needle not in stream,
                "message": "forbidden fragment absent" if needle not in stream else "forbidden fragment found",
            }
        )
    return checks


def run_golden_case(dataset: GoldenDataset, case: GoldenCase) -> dict[str, Any]:
    """Replay one case in an isolated copy of its fixture."""
    fixture = _resolved_child(dataset.path.parent, case.fixture, f"case {case.id} fixture")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"voly-golden-{case.id}-") as temp_dir:
        workspace = Path(temp_dir) / "workspace"
        shutil.copytree(fixture, workspace)
        stdout_path = Path(temp_dir) / "stdout.txt"
        stderr_path = Path(temp_dir) / "stderr.txt"
        argv = _resolved_argv(case.argv)
        timed_out = False
        launch_error = ""
        return_code: int | None = None
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    shell=False,
                    env=_sanitized_env(temp_dir),
                )
                try:
                    return_code = process.wait(timeout=case.timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.kill()
                    return_code = process.wait()
            except OSError as exc:
                launch_error = f"{type(exc).__name__}: {exc}"

        stdout, stdout_truncated = _tail(stdout_path)
        stderr, stderr_truncated = _tail(stderr_path)
        checks: list[dict[str, Any]] = []
        if launch_error:
            checks.append({"id": "process:launch", "passed": False, "message": launch_error})
        elif timed_out:
            checks.append(
                {
                    "id": "process:timeout",
                    "passed": False,
                    "message": f"exceeded {case.timeout_seconds}s",
                }
            )
        else:
            checks.append(
                {
                    "id": "process:exit_code",
                    "passed": return_code == case.expected.exit_code,
                    "message": f"expected {case.expected.exit_code}, got {return_code}",
                }
            )
        checks.extend(
            _text_checks(
                stdout,
                "stdout",
                case.expected.stdout_contains,
                case.expected.stdout_not_contains,
            )
        )
        checks.extend(
            _text_checks(
                stderr,
                "stderr",
                case.expected.stderr_contains,
                case.expected.stderr_not_contains,
            )
        )
        checks.extend(_file_check(workspace, item) for item in case.expected.files)

    return {
        "case_id": case.id,
        "category": case.category,
        "passed": bool(checks) and all(check["passed"] for check in checks),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "declared_argv": list(case.argv),
        "resolved_argv": argv,
        "return_code": return_code,
        "timed_out": timed_out,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "checks": checks,
    }


def run_golden_dataset(
    dataset: GoldenDataset,
    *,
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Replay selected cases and return a versioned local JSON report."""
    known = {case.id for case in dataset.cases}
    unknown = sorted((case_ids or set()) - known)
    if unknown:
        raise GoldenDatasetError(f"unknown case ids: {unknown}")
    selected = [
        case for case in dataset.cases if case_ids is None or case.id in case_ids
    ]
    results = [run_golden_case(dataset, case) for case in selected]
    passed = sum(1 for result in results if result["passed"])
    return {
        "schema_version": GOLDEN_REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": dataset.dataset_id,
            "version": dataset.version,
            "schema_version": dataset.schema_version,
            "fingerprint_sha256": dataset.fingerprint,
        },
        "runner": {
            "name": "voly-offline-golden",
            "schema_version": GOLDEN_REPORT_SCHEMA_VERSION,
            "python": sys.version.split()[0],
            "network_policy": "not_enforced",
            "environment_policy": "credentials_removed",
            "shell": False,
        },
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
        },
        "cases": results,
    }


def save_golden_report(report: dict[str, Any], path: str | Path) -> Path:
    """Atomically save a local golden replay report."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target
