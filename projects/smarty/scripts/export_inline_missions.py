#!/usr/bin/env python3
"""Legacy helper — inline missions were exported to missions/*.yaml.

Missions are now file-only. To add a mission:
    python3 -m codeops.cli smarty combat init <name>
"""
from __future__ import annotations

import sys

print(
    "Inline missions removed from cli_commands.py.\n"
    "All missions live in codeops/projects/smarty/missions/*.yaml\n"
    "Use: codeops smarty combat init <name>",
    file=sys.stderr,
)
sys.exit(1)
