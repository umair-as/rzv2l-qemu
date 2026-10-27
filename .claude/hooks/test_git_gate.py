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
        self.dirty = mock.patch.object(git_gate, "submodule_dirty", return_value=False)
        self.dirty_mock = self.dirty.start()

    def tearDown(self):
        self.dirty.stop()
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
    def test_push_asks(self):
        self.assertEqual(self.decide("git push origin main"), "ask")

    def test_push_dash_C_asks(self):
        self.assertEqual(self.decide("git -C qemu push origin unit/x"), "ask")

    def test_gh_pr_create_asks(self):
        self.assertEqual(self.decide("gh pr create --fill"), "ask")

    def test_gh_pr_merge_asks(self):
        self.assertEqual(self.decide("gh pr merge 3"), "ask")

    def test_push_in_quoted_text_is_not_push(self):
        self.assertIsNone(self.decide('git commit -m "run tests before git push"'))

    def test_add_qemu_clean_allowed(self):
        self.assertIsNone(self.decide("git add qemu"))

    def test_add_qemu_dirty_asks(self):
        self.dirty_mock.return_value = True
        self.assertEqual(self.decide("git add qemu"), "ask")

    def test_broad_add_with_dirty_pointer_asks(self):
        self.dirty_mock.return_value = True
        for cmd in ("git add -A", "git add .", "git commit -a -m x"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide(cmd), "ask")

    def test_broad_add_with_clean_pointer_allowed(self):
        self.assertIsNone(self.decide("git add -A"))

    def test_newline_separated_build_denied(self):
        self.assertEqual(self.decide("cd qemu\nninja"), "deny")

    def test_nested_shell_build_denied(self):
        self.assertEqual(self.decide('bash -lc "cd qemu && ninja"'), "deny")

    def test_nested_shell_push_asks(self):
        self.assertEqual(self.decide("sh -c 'git push origin main'"), "ask")

    def test_commit_pathspec_qemu_dirty_asks(self):
        self.dirty_mock.return_value = True
        for cmd in ("git commit -m x -- qemu", "git commit qemu -m x"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide(cmd), "ask")

    def test_commit_message_word_qemu_is_not_pathspec(self):
        self.dirty_mock.return_value = True
        self.assertIsNone(self.decide("git commit -m qemu"))

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
