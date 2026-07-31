"""Static security admission for inert external capability-pack content."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from voly.capability.pack_security_patterns import PACK_RISK_PATTERNS, is_negated
from voly.capability.packs import PackDiscoveryReport

MAX_COMPONENT_BYTES = 512_000
MAX_FINDINGS = 200

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class PackSecurityFinding:
    finding_id: str
    severity: str
    path: str
    line: int
    message: str
    evidence: str


@dataclass(frozen=True)
class PackPermissionDeclaration:
    path: str
    permissions: tuple[str, ...]


@dataclass(frozen=True)
class PackAdmissionReport:
    schema_version: int
    decision: str
    risk_level: str
    scanned_components: int
    findings: tuple[PackSecurityFinding, ...] = field(default_factory=tuple)
    permissions: tuple[PackPermissionDeclaration, ...] = field(default_factory=tuple)

    @property
    def quarantined_components(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.path
                    for item in self.findings
                    if item.severity in {"high", "critical"}
                }
            )
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["quarantined_components"] = self.quarantined_components
        return data


def admit_external_pack(report: PackDiscoveryReport) -> PackAdmissionReport:
    """Scan discovered components without importing or executing them."""
    root = Path(report.provenance.source_path).resolve(strict=True)
    findings: list[PackSecurityFinding] = []
    permission_map: dict[str, set[str]] = {}
    scanned = 0

    for component in report.components:
        path = _component_path(root, component.path)
        scanned += 1
        text = _read_bounded_text(path, component.path, findings)
        if text is None:
            continue
        if component.kind == "mcp_config":
            _inspect_mcp_config(component.path, text, findings, permission_map)
        _scan_patterns(
            component.kind,
            component.path,
            text,
            findings,
            permission_map,
        )
        if len(findings) >= MAX_FINDINGS:
            break

    findings = sorted(
        findings[:MAX_FINDINGS],
        key=lambda item: (-_RISK_ORDER[item.severity], item.path, item.line, item.finding_id),
    )
    risk_level = _overall_risk(findings)
    decision = "quarantine" if risk_level in {"high", "critical"} else "allow"
    permissions = tuple(
        PackPermissionDeclaration(path=path, permissions=tuple(sorted(values)))
        for path, values in sorted(permission_map.items())
    )
    return PackAdmissionReport(
        schema_version=1,
        decision=decision,
        risk_level=risk_level,
        scanned_components=scanned,
        findings=tuple(findings),
        permissions=permissions,
    )


def _component_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"component escapes capability pack source: {relative}") from exc
    return path


def _read_bounded_text(
    path: Path,
    relative: str,
    findings: list[PackSecurityFinding],
) -> str | None:
    try:
        if path.stat().st_size > MAX_COMPONENT_BYTES:
            findings.append(
                PackSecurityFinding(
                    finding_id="component_too_large",
                    severity="high",
                    path=relative,
                    line=0,
                    message="Component exceeds the static admission size limit",
                    evidence=f">{MAX_COMPONENT_BYTES} bytes",
                )
            )
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        findings.append(
            PackSecurityFinding(
                finding_id="component_unreadable",
                severity="high",
                path=relative,
                line=0,
                message="Component could not be read for admission",
                evidence=str(exc)[:160],
            )
        )
        return None


def _scan_patterns(
    kind: str,
    relative: str,
    text: str,
    findings: list[PackSecurityFinding],
    permission_map: dict[str, set[str]],
) -> None:
    for pattern in PACK_RISK_PATTERNS:
        if pattern.kinds is not None and kind not in pattern.kinds:
            continue
        match = pattern.regex.search(text)
        if match is None:
            continue
        if pattern.severity in {"high", "critical"} and is_negated(text, match.start()):
            continue
        permission_map.setdefault(relative, set()).add(pattern.permission)
        findings.append(
            PackSecurityFinding(
                finding_id=pattern.finding_id,
                severity=pattern.severity,
                path=relative,
                line=text.count("\n", 0, match.start()) + 1,
                message=pattern.message,
                evidence=_safe_evidence(match.group(0)),
            )
        )


def _inspect_mcp_config(
    relative: str,
    text: str,
    findings: list[PackSecurityFinding],
    permission_map: dict[str, set[str]],
) -> None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        findings.append(
            PackSecurityFinding(
                finding_id="invalid_mcp_json",
                severity="high",
                path=relative,
                line=exc.lineno,
                message="MCP configuration is not valid JSON",
                evidence=exc.msg,
            )
        )
        return
    if not isinstance(payload, dict):
        _add_invalid_mcp_shape(relative, findings)
        return
    servers = payload.get("mcpServers", payload)
    if not isinstance(servers, dict):
        _add_invalid_mcp_shape(relative, findings)
        return
    for value in servers.values():
        if not isinstance(value, dict):
            _add_invalid_mcp_shape(relative, findings)
            return
        if value.get("command"):
            permission_map.setdefault(relative, set()).add("subprocess")
        if value.get("url"):
            permission_map.setdefault(relative, set()).add("network")


def _add_invalid_mcp_shape(
    relative: str,
    findings: list[PackSecurityFinding],
) -> None:
    findings.append(
        PackSecurityFinding(
            finding_id="invalid_mcp_shape",
            severity="high",
            path=relative,
            line=1,
            message="MCP configuration must contain a server mapping",
            evidence="unexpected JSON structure",
        )
    )


def _safe_evidence(value: str) -> str:
    return " ".join(value.split())[:160]


def _overall_risk(findings: list[PackSecurityFinding]) -> str:
    if not findings:
        return "low"
    return max((item.severity for item in findings), key=_RISK_ORDER.__getitem__)
