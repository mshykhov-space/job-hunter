#!/usr/bin/env python3
import json
import re
import sys


FORBIDDEN = (
    re.compile(r"co-authored-by", re.IGNORECASE),
    re.compile(r"signed-off-by", re.IGNORECASE),
    re.compile(r"generated with", re.IGNORECASE),
    re.compile(r"noreply@anthropic", re.IGNORECASE),
    re.compile("\N{ROBOT FACE}"),
)
SHELL_TOOLS = {"bash", "execute", "shell"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return 0

    tool_name = str(payload.get("tool_name") or payload.get("toolName") or "").lower()
    if tool_name and tool_name not in SHELL_TOOLS:
        return 0

    tool_input = payload.get("tool_input") or payload.get("toolInput") or payload.get("input") or {}
    if not isinstance(tool_input, dict):
        return 0

    command = str(tool_input.get("command") or tool_input.get("cmd") or "")
    if not re.search(r"\bgit\b[\s\S]*\bcommit\b", command):
        return 0
    if not any(pattern.search(command) for pattern in FORBIDDEN):
        return 0

    sys.stderr.write(
        "Commit blocked: message contains a forbidden trailer or AI attribution. "
        "Remove it and retry.\n",
    )
    return 2


raise SystemExit(main())
