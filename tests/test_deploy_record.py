"""A frontend build's deploy record, built from real (temporary) git checkouts.

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "tools"))

from wrfdb_data import deploy_record  # noqa: E402
from wrfdb_data.__main__ import main  # noqa: E402
from wrfdb_data.paths import VERSION_REL, DataRepoError  # noqa: E402

NOW = datetime(2026, 10, 5, 18, 0, 0, tzinfo=timezone.utc)
GH_ENV = {
    "GITHUB_RUN_ID": "123",
    "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": "Surxe/WRFrontiersDB-Site",
    "GITHUB_EVENT_NAME": "push",
}


def git_repo(path: Path, commit_date: str, files: dict[str, str]) -> str:
    """Init a repo at `path` with one commit of `files`; returns its sha."""
    path.mkdir(parents=True)
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text, encoding="utf-8")
    env = {"GIT_AUTHOR_DATE": commit_date, "GIT_COMMITTER_DATE": commit_date,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "c"]):
        subprocess.run(["git", "-C", str(path), *cmd], check=True, env=env)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


class DeployRecordCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data_sha = git_repo(self.root / "data", "2026-10-04T15:10:39-05:00",
                                 {str(VERSION_REL): "2026-09-29\n"})
        self.app_sha = git_repo(self.root / "my-app", "2026-10-05T10:00:00Z", {"a.txt": "a"})

    def test_record_in_ci(self):
        record = deploy_record.build_record(self.root / "data", self.root / "my-app",
                                            env=GH_ENV, now=NOW)
        self.assertEqual(record, {
            "app": "WRFrontiersDB-Site",
            "app_commit": self.app_sha,
            "run_id": "123",
            "run_url": "https://github.com/Surxe/WRFrontiersDB-Site/actions/runs/123",
            "trigger": "push",
            "built_at_utc": "2026-10-05T18:00:00Z",
            "data_commit": self.data_sha,
            "data_commit_date_utc": "2026-10-04T20:10:39Z",
            "data_version": "2026-09-29",
        })

    def test_record_by_hand_has_no_run(self):
        record = deploy_record.build_record(self.root / "data", self.root / "my-app",
                                            env={}, now=NOW)
        self.assertEqual(record["app"], "my-app")
        self.assertIsNone(record["run_id"])
        self.assertIsNone(record["run_url"])
        self.assertIsNone(record["trigger"])

    def test_not_a_checkout_is_an_error(self):
        (self.root / "plain").mkdir()
        with self.assertRaises(DataRepoError):
            deploy_record.build_record(self.root / "data", self.root / "plain", env={})

    def test_cli_writes_out(self):
        out = self.root / "dist" / "deploy.json"
        out.parent.mkdir()
        with redirect_stdout(io.StringIO()) as printed:
            rc = main(["--data-dir", str(self.root / "data"), "deploy-record",
                       "--app-dir", str(self.root / "my-app"), "--out", str(out)])
        self.assertEqual(rc, 0)
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written["data_commit"], self.data_sha)
        self.assertEqual(json.loads(printed.getvalue()), written)
        self.assertFalse(out.with_name("deploy.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
