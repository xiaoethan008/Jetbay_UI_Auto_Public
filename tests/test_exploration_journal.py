"""Offline infrastructure tests; no account, browser or business environment."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from framework.exploration_journal import ExplorationJournal


class ExplorationJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"
        self.journal = ExplorationJournal.create(self.root, environment="test", module="cms")

    def begin(self):
        return self.journal.begin("TC-DEMO", expected="field visible", next_action="inspect field")

    def test_resume_keeps_unfinished_attempt_and_cleanup(self):
        step = self.begin()
        baseline = self.journal.json_evidence(step, {"id": "qa-row", "name": "original"})
        self.journal.require_cleanup("qa-row", action="restore name", baseline=baseline)
        reopened = ExplorationJournal(self.root)
        self.assertEqual(reopened.summary()["counts"], {"running": 1})
        self.assertEqual(reopened.summary()["pending_cleanup_count"], 1)
        self.assertEqual(reopened.read()["steps"][0]["id"], step)

    def test_missing_or_modified_evidence_cannot_be_passed(self):
        step = self.begin()
        with self.assertRaises(ValueError):
            self.journal.finish(step, status="passed", actual="visible")
        evidence = self.journal.json_evidence(step, {"visible": True})
        evidence.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.journal.finish(step, status="passed", actual="visible")
        self.assertEqual(self.journal.summary()["counts"], {"running": 1})

    def test_failed_checkpoint_replace_preserves_last_committed_state(self):
        before = self.journal.path.read_bytes()
        with patch("framework.exploration_journal.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.begin()
        self.assertEqual(self.journal.path.read_bytes(), before)
        self.assertFalse((self.root / ".journal.lock").exists())
        self.begin()  # next operation is recoverable

    def test_run_cannot_be_overwritten_or_external_evidence_attached(self):
        with self.assertRaises(FileExistsError):
            ExplorationJournal.create(self.root, environment="prod", module="other")
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text("{}")
        with self.assertRaises(ValueError):
            self.journal.attach(self.begin(), outside)

    def test_secrets_redacted_and_summary_does_not_dump_payload(self):
        step = self.begin()
        evidence = self.journal.json_evidence(step, {
            "headers": {"admAuthorization": "abc", "Cookie": "xyz"},
            "items": [{"password": "secret", "accessToken": "sensitive"}],
            "body": "x" * 10000,
        })
        data = json.loads(evidence.read_text(encoding="utf-8"))
        self.assertEqual(data["headers"]["admAuthorization"], "<redacted>")
        self.assertEqual(data["items"][0]["accessToken"], "<redacted>")
        self.assertNotIn("xxx", json.dumps(self.journal.summary()))

    def test_completion_cleanup_and_attempt_history(self):
        step = self.begin()
        evidence = self.journal.json_evidence(step, {"visible": True})
        self.journal.require_cleanup("row", action="restore", baseline=evidence)
        self.journal.finish(step, status="passed", actual="visible")
        self.journal.confirm_cleanup("row", evidence=evidence)
        with self.assertRaises(ValueError):
            self.journal.finish(step, status="failed", actual="overwrite history")
        self.begin()
        self.assertEqual(self.journal.summary()["counts"], {"passed": 1, "running": 1})
        self.assertEqual(self.journal.summary()["pending_cleanup_count"], 0)


if __name__ == "__main__":
    unittest.main()
