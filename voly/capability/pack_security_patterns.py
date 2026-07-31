"""Static indicators used by external capability-pack admission."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PackRiskPattern:
    finding_id: str
    severity: str
    permission: str
    message: str
    regex: re.Pattern[str]
    kinds: frozenset[str] | None = None


PACK_RISK_PATTERNS = (
    PackRiskPattern(
        "prompt_instruction_override",
        "high",
        "prompt_control",
        "Instruction attempts to override prior or system guidance",
        re.compile(r"(?i)\b(ignore|disregard|override)\b.{0,50}\b(previous|prior|system)\b"),
        frozenset({"agent", "skill", "rule", "legacy_command"}),
    ),
    PackRiskPattern(
        "prompt_secret_exfiltration",
        "critical",
        "secrets",
        "Instruction requests disclosure or transmission of secrets",
        re.compile(
            r"(?i)\b(reveal|print|send|upload|exfiltrat\w*)\b.{0,80}"
            r"\b(secret|token|password|api[_ -]?key|\.env)\b"
        ),
    ),
    PackRiskPattern(
        "destructive_command",
        "critical",
        "filesystem_write",
        "Destructive filesystem or Git command detected",
        re.compile(
            r"(?i)(rm\s+-rf\b|remove-item\b.{0,60}-recurse\b|"
            r"git\s+reset\s+--hard\b|format\s+[a-z]:)"
        ),
    ),
    PackRiskPattern(
        "subprocess_execution",
        "medium",
        "subprocess",
        "Component may launch a subprocess",
        re.compile(
            r"(?i)(\bsubprocess\b|\bchild_process\b|\bos\.system\b|"
            r"\bexecSync\b|\bspawnSync\b|\"command\"\s*:)"
        ),
        frozenset({"hook", "mcp_config", "legacy_command", "skill"}),
    ),
    PackRiskPattern(
        "network_access",
        "medium",
        "network",
        "Component may access the network",
        re.compile(r"(?i)(https?://|\bcurl\b|\bwget\b|\bfetch\s*\(|\brequests\.)"),
    ),
    PackRiskPattern(
        "secret_access",
        "high",
        "secrets",
        "Component may read credentials or secret-bearing environment data",
        re.compile(
            r"(?i)(\bprocess\.env\b|\bos\.environ\b|\bgetenv\s*\(|"
            r"\.env\b|api[_ -]?key|access[_ -]?token)"
        ),
        frozenset({"hook", "mcp_config", "legacy_command", "skill"}),
    ),
    PackRiskPattern(
        "filesystem_write",
        "medium",
        "filesystem_write",
        "Component may modify the filesystem",
        re.compile(
            r"(?i)(write_text|writeFile|appendFile|mkdir|copy-item|move-item|"
            r"remove-item|>\s*[./~]|tee\s+)"
        ),
        frozenset({"hook", "legacy_command", "skill"}),
    ),
)


def is_negated(text: str, match_start: int) -> bool:
    """Return true when an indicator is presented as an explicit prohibition."""
    prefix = text[max(0, match_start - 50):match_start]
    return bool(
        re.search(
            r"(?i)(never|do\s+not|don't|must\s+not|avoid|prevent|block|detect)"
            r"[^.\n]{0,35}$",
            prefix,
        )
    )
