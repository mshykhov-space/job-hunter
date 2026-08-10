import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".rulesync" / "hooks" / "no-ai-trailers.py"


class NoAiTrailersTest(unittest.TestCase):
    def run_hook(self, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(HOOK)],
            input=json.dumps(payload),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_allows_conventional_commit_without_trailer(self) -> None:
        result = self.run_hook(
            {"tool_name": "Bash", "tool_input": {"command": 'git commit -m "chore: migrate config"'}},
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_blocks_trailer_in_claude_shell_payload(self) -> None:
        result = self.run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git commit -m "chore: migrate config\n\nCo-Authored-By: Bot"'},
            },
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("forbidden trailer", result.stderr)

    def test_blocks_trailer_in_generic_shell_payload(self) -> None:
        result = self.run_hook(
            {
                "toolName": "shell",
                "input": {"cmd": 'git commit -m "chore: migrate config\n\nSigned-off-by: Bot"'},
            },
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("forbidden trailer", result.stderr)

    def test_ignores_non_commit_commands(self) -> None:
        result = self.run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git status --short"}},
        )

        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
