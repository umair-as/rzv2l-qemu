#!/usr/bin/env python3
"""Tests for git_gate.py. Run: python3 .claude/hooks/test_git_gate.py -v"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_gate  # noqa: E402


class ClaudeGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "qemu").mkdir()
        (self.root / "build" / "qemu").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def decide(self, command, cwd=None):
        result = git_gate.classify_command(command, cwd or self.root, self.root)
        return result[0] if result else None

    # tree guard
    def test_ninja_in_fork_denied(self):
        self.assertEqual(self.decide("cd qemu && ninja"), "deny")

    def test_configure_in_fork_denied(self):
        self.assertEqual(self.decide("./configure --target-list=aarch64-softmmu",
                                     cwd=self.root / "qemu"), "deny")

    def test_ninja_dash_C_outside_fork_allowed(self):
        self.assertIsNone(self.decide("cd qemu && ninja -C ../build/qemu"))

    def test_make_dash_C_into_fork_denied(self):
        self.assertEqual(self.decide("make -C qemu"), "deny")

    def test_build_dir_allowed(self):
        self.assertIsNone(self.decide("cd build/qemu && ninja qemu-system-aarch64"))

    # ask gate
    def test_newline_separated_build_denied(self):
        self.assertEqual(self.decide("cd qemu\nninja"), "deny")

    def test_nested_shell_build_denied(self):
        self.assertEqual(self.decide('bash -lc "cd qemu && ninja"'), "deny")

    def test_heredoc_message_with_apostrophe_parses(self):
        cmd = ("git add -A docs && git commit -q -F - <<'EOF' && git log -1\n"
               "fix(docs): qtest's limit, a \"quoted\" word\n\nEOF")
        self.assertIsNone(self.decide(cmd))

    def test_heredoc_body_is_not_a_command(self):
        cmd = "cat > notes.txt <<'EOF'\ngit push origin main\nEOF"
        self.assertIsNone(self.decide(cmd))

    def test_unquoted_heredoc_substitution_raises(self):
        with self.assertRaises(ValueError):
            self.decide("cat <<EOF\n$(git push)\nEOF")

    def test_agent_git_cycle_is_silent(self):
        for cmd in ("git push origin main", "gh pr create --fill", "git add qemu",
                    "git commit -am 'bump'", "git -C qemu push origin unit/x"):
            self.assertIsNone(self.decide(cmd), cmd)

    def test_build_after_heredoc_denied(self):
        cmd = "git commit -F - <<'EOF'\nit's done\nEOF\ncd qemu && ninja"
        self.assertEqual(self.decide(cmd), "deny")

    def test_plain_commands_silent(self):
        for cmd in ("ls -la", "git status", "git log --oneline -5"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decide(cmd))

    # entry point
    def test_bad_json_asks(self):
        out = json.loads(git_gate.main_claude("{not json"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_non_bash_or_empty_is_silent(self):
        self.assertEqual(git_gate.main_claude(json.dumps({"tool_input": {}})), "")

    def test_json_deny_shape(self):
        payload = {"tool_name": "Bash", "cwd": str(self.root),
                   "tool_input": {"command": "cd qemu && ninja"}}
        with mock.patch.object(git_gate, "project_root", return_value=self.root):
            out = json.loads(git_gate.main_claude(json.dumps(payload)))
        hso = out["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertIn("build/", hso["permissionDecisionReason"])


class GitHookTest(unittest.TestCase):
    def test_fork_signoff_rejected(self):
        errs = git_gate.check_message("hw/arm: x\n\nSigned-off-by: A <a@b>\n", "fork", "unit/x")
        self.assertTrue(errs)

    def test_signoff_in_comment_ignored(self):
        errs = git_gate.check_message("hw/arm: x\n# Signed-off-by: A <a@b>\n", "fork", "unit/x")
        self.assertEqual(errs, [])

    def test_signoff_below_scissors_ignored(self):
        msg = "hw/arm: x\n# ------------------------ >8 ------------------------\nSigned-off-by: A\n"
        self.assertEqual(git_gate.check_message(msg, "fork", "unit/x"), [])

    def test_project_signoff_allowed(self):
        errs = git_gate.check_message("docs: x\n\nSigned-off-by: A <a@b>\n", "project", "main")
        self.assertEqual(errs, [])

    def test_fork_base_branch_rejected(self):
        self.assertTrue(git_gate.check_message("hw/arm: x\n", "fork", "rzv2l-base"))

    def test_fork_dev_branch_ok(self):
        self.assertEqual(git_gate.check_message("hw/arm: x\n", "fork", "rzv2l-dev"), [])


if __name__ == "__main__":
    unittest.main()
