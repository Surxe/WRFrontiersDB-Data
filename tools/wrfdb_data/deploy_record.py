"""Build a frontend's deploy record: which Data commit a build was made from.

The Site and the Discount Visualizer both build from a checkout of this repo. At
build time each writes the record into its output as `/deploy.json` (via the
`record-deploy` action in `.github/actions/`), so the live page always says which
data it serves, however the deploy was triggered. The same file is uploaded as the
`deploy-record` run artifact, which the Orchestrator copies into its local deploy
state for the Discord bot.

The record is flat so `curl .../deploy.json | jq .data_commit` works:

* `app`, `app_commit`: the frontend repo and the commit it was built from. That's
  the workspace's HEAD, not `GITHUB_SHA`: a job may pull a newer commit first.
* `run_id`, `run_url`, `trigger`: the GitHub Actions run (null when run by hand).
* `built_at_utc`: when the record was written, right after the build.
* `data_commit`, `data_commit_date_utc`, `data_version`: this repo's checkout.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .paths import DataRepoError, read_version, save_json


def _git(repo_dir: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo_dir), *args], check=True,
                             capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", None) or exc
        raise DataRepoError(f"git {' '.join(args)} failed in {repo_dir}: {str(detail).strip()}") from exc
    return out.strip()


def _utc(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_name(app_dir: Path, env: dict) -> str:
    repo = env.get("GITHUB_REPOSITORY")
    if repo:
        return repo.split("/", 1)[-1]
    return Path(_git(app_dir, "rev-parse", "--show-toplevel")).name


def build_record(data_dir: Path, app_dir: Path, env: dict | None = None,
                 now: datetime | None = None) -> dict:
    """The deploy record for a build of `app_dir` from the Data checkout `data_dir`."""
    env = os.environ if env is None else env
    run_id = env.get("GITHUB_RUN_ID") or None
    run_url = None
    if run_id and env.get("GITHUB_SERVER_URL") and env.get("GITHUB_REPOSITORY"):
        run_url = f"{env['GITHUB_SERVER_URL']}/{env['GITHUB_REPOSITORY']}/actions/runs/{run_id}"
    now = now or datetime.now(timezone.utc)
    return {
        "app": _repo_name(app_dir, env),
        "app_commit": _git(app_dir, "rev-parse", "HEAD"),
        "run_id": run_id,
        "run_url": run_url,
        "trigger": env.get("GITHUB_EVENT_NAME") or None,
        "built_at_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_commit": _git(data_dir, "rev-parse", "HEAD"),
        "data_commit_date_utc": _utc(_git(data_dir, "log", "-1", "--format=%cI")),
        "data_version": read_version(data_dir),
    }


def write_record(out: Path, record: dict) -> None:
    """Write `record` to `out` atomically."""
    out = Path(out)
    tmp = out.with_name(out.name + ".tmp")
    try:
        save_json(tmp, record)
        os.replace(tmp, out)
    except OSError as exc:
        raise DataRepoError(f"could not write the deploy record {out}: {exc}") from exc
