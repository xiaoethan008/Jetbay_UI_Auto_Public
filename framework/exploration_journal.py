"""Durable evidence/checkpoints for agent exploration, independent of pytest.

Each run belongs to one environment and one worker. No browser actions are
replayed by this module. Inspect unfinished steps before resuming a business flow.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4


STATUSES = {"passed", "failed", "partial", "blocked"}


def sanitize(value):
    """Redact credential-shaped fields; callers still select approved evidence."""
    if isinstance(value, dict):
        return {
            str(k): "<redacted>" if any(
                word in re.sub(r"[^a-z]", "", str(k).lower())
                for word in ("password", "passwd", "pwd", "token", "authorization", "cookie", "secret")
            ) else sanitize(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer <redacted>", value)
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, data):
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(sanitize(data), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


class ExplorationJournal:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.path = self.root / "checkpoint.json"

    @classmethod
    def create(cls, directory, *, environment, module):
        journal = cls(directory)
        journal.root.mkdir(parents=True, exist_ok=True)
        with journal._lock():
            if journal.path.exists():
                raise FileExistsError("Run already exists; open it and inspect pending work.")
            atomic_json(journal.path, {
                "schema": 1, "environment": environment, "module": module,
                "created_at": now(), "steps": [], "cleanup": {},
            })
        return journal

    @contextmanager
    def _lock(self):
        lock = self.root / ".journal.lock"
        # Exclusive creation: never silently overwrite another worker's progress.
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink(missing_ok=True)

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    @contextmanager
    def _edit(self):
        with self._lock():
            state = self.read()
            yield state
            state["updated_at"] = now()
            atomic_json(self.path, state)

    @staticmethod
    def _step(state, step_id):
        for step in state["steps"]:
            if step["id"] == step_id:
                return step
        raise KeyError(step_id)

    def begin(self, case_id, *, expected, next_action):
        if not case_id or not expected or not next_action:
            raise ValueError("case_id, expected and next_action are required")
        if len(case_id) > 128 or len(expected) > 600 or len(next_action) > 600:
            raise ValueError("Keep case IDs <=128 and checkpoint descriptions <=600 characters")
        with self._edit() as state:
            step_id = uuid4().hex
            state["steps"].append({
                "id": step_id, "case_id": case_id, "status": "running",
                "expected": expected, "next_action": next_action,
                "started_at": now(), "evidence": [],
            })
        return step_id

    def _evidence(self, filename):
        path = (self.root / filename).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("Evidence must be an existing file inside this run directory")
        if path == self.path or path.name == ".journal.lock":
            raise ValueError("The checkpoint itself is not execution evidence")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"path": path.relative_to(self.root).as_posix(), "sha256": digest}

    def attach(self, step_id, filename):
        with self._edit() as state:
            step = self._step(state, step_id)
            if step["status"] != "running":
                raise ValueError("Finished attempts are immutable; begin another attempt")
            step["evidence"].append(self._evidence(filename))

    def json_evidence(self, step_id, payload):
        with self._edit() as state:
            step = self._step(state, step_id)
            if step["status"] != "running":
                raise ValueError("Finished attempts are immutable")
            evidence_dir = self.root / "evidence"
            evidence_dir.mkdir(exist_ok=True)
            path = evidence_dir / (uuid4().hex + ".json")
            atomic_json(path, payload)
            step["evidence"].append(self._evidence(path))
        return path

    def finish(self, step_id, *, status, actual, next_action=""):
        if status not in STATUSES:
            raise ValueError("Use passed, failed, partial or blocked")
        if not actual or len(actual) > 600 or len(next_action) > 600:
            raise ValueError("Provide an actual result; summary fields must be <=600 characters")
        with self._edit() as state:
            step = self._step(state, step_id)
            if step["status"] != "running":
                raise ValueError("Finished attempts are immutable")
            if status in {"passed", "failed"} and not step["evidence"]:
                raise ValueError("Passed/failed results require execution evidence")
            for evidence in step["evidence"]:
                if self._evidence(evidence["path"]) != evidence:
                    raise ValueError("Evidence changed after attachment")
            step.update(status=status, actual=actual, next_action=next_action, finished_at=now())

    def require_cleanup(self, key, *, action, baseline):
        with self._edit() as state:
            if key in state["cleanup"]:
                raise ValueError("Cleanup key already exists")
            state["cleanup"][key] = {
                "status": "pending", "action": action,
                "baseline": self._evidence(baseline),
            }

    def confirm_cleanup(self, key, *, evidence):
        with self._edit() as state:
            cleanup = state["cleanup"][key]
            cleanup.update(status="verified", evidence=self._evidence(evidence), verified_at=now())

    def summary(self, limit=5):
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        state = self.read()
        counts = {}
        for step in state["steps"]:
            counts[step["status"]] = counts.get(step["status"], 0) + 1
        return {
            "checkpoint": str(self.path), "environment": state["environment"],
            "module": state["module"], "counts": counts,
            "pending_cleanup_count": sum(x["status"] != "verified" for x in state["cleanup"].values()),
            "recent": [{k: s.get(k, "") for k in ("id", "case_id", "status", "next_action")}
                       for s in state["steps"][-limit:]],
        }


def main():
    parser = argparse.ArgumentParser(description="Read a concise exploration checkpoint; no browser actions")
    parser.add_argument("directory")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(ExplorationJournal(args.directory).summary(args.limit), ensure_ascii=False))


if __name__ == "__main__":
    main()
