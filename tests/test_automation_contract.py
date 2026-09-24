import configparser
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KOTLIN_PACKAGE = (
    ROOT
    / "api"
    / "src"
    / "main"
    / "kotlin"
    / "com"
    / "mshykhov"
    / "jobhunter"
    / "application"
    / "automation"
)
TYPESCRIPT_HEALTH = ROOT / "automation" / "src" / "domain" / "health.ts"

VOCABULARY = {
    "AutomationState": ("READY", "DEGRADED", "AUTH_REQUIRED", "UNAVAILABLE"),
    "AutomationComponent": (
        "LAUNCHER",
        "API",
        "DATABASE",
        "CHROME",
        "PLAYWRIGHT",
        "BROWSER_MCP",
        "JOB_HUNTER_MCP",
        "CODEX",
    ),
    "AutomationReason": (
        "NONE",
        "API_UNAVAILABLE",
        "DATABASE_UNAVAILABLE",
        "CHROME_UNAVAILABLE",
        "PROFILE_UNREADABLE",
        "PLAYWRIGHT_UNAVAILABLE",
        "MCP_UNAVAILABLE",
        "CODEX_AUTH_REQUIRED",
        "SITE_AUTH_REQUIRED",
        "CANARY_FAILED",
        "CLOCK_SKEW",
        "STALE_GENERATION",
        "INVALID_REPORT",
        "OTHER",
    ),
    "ProbeType": ("HEARTBEAT", "PREFLIGHT", "CODEX"),
    "ProbeOutcome": ("SUCCESS", "FAILURE"),
}

TYPESCRIPT_CONSTANTS = {
    "AutomationState": "AUTOMATION_STATES",
    "AutomationComponent": "AUTOMATION_COMPONENTS",
    "AutomationReason": "AUTOMATION_REASONS",
    "ProbeType": "PROBE_TYPES",
    "ProbeOutcome": "PROBE_OUTCOMES",
}


def kotlin_enum_values(name: str) -> tuple[str, ...]:
    source = (KOTLIN_PACKAGE / f"{name}.kt").read_text()
    match = re.search(rf"enum class {name}\s*\{{(?P<body>[^}}]+)}}", source)
    if match is None:
        raise AssertionError(f"Kotlin enum {name} was not found")
    return tuple(re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*,?\s*$", match["body"], re.MULTILINE))


def typescript_union_values(constant: str) -> tuple[str, ...]:
    source = TYPESCRIPT_HEALTH.read_text()
    match = re.search(
        rf"export const {constant}\s*=\s*\[(?P<body>.*?)]\s*as const;",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"TypeScript constant {constant} was not found")
    return tuple(re.findall(r'"([A-Z][A-Z0-9_]*)"', match["body"]))


class AutomationContractTest(unittest.TestCase):
    def test_kotlin_and_typescript_share_exact_wire_vocabulary(self) -> None:
        for name, expected in VOCABULARY.items():
            with self.subTest(vocabulary=name):
                self.assertEqual(expected, kotlin_enum_values(name))
                self.assertEqual(expected, typescript_union_values(TYPESCRIPT_CONSTANTS[name]))

    def test_automation_submodule_uses_expected_public_repository(self) -> None:
        config = configparser.ConfigParser()
        config.read(ROOT / ".gitmodules")

        self.assertEqual(
            "automation",
            config["submodule \"automation\""]["path"],
        )
        self.assertEqual(
            "https://github.com/mshykhov-space/job-hunter-automation.git",
            config["submodule \"automation\""]["url"],
        )


if __name__ == "__main__":
    unittest.main()
