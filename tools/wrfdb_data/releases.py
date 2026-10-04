"""Record newly-released robots and known patch builds into `index/`.

A robot is a `VirtualBot` in the published data iff its modules are used by a
factory preset, and the studio only ships an obtainable robot with one, so a new
id appearing in `current/Objects/VirtualBot.json` **is** the release signal (no
`ProductionStatus` check needed; the Parser gates on the factory preset, which
agrees 1:1 with `Ready` core modules).

The store *is* the dedup source: `index/robot_release_dates.json` keys every
robot by its `virtual_bot_ref` (`OBJID_VirtualBot::<id>`), in `robots{}` and
`titans{}`. A roster id whose ref is already a key is already recorded, so
detection is a pure file comparison: no git diff against the previous patch, no
separate state file. For each roster id we either:

  * append a fresh entry if its ref is not a key yet (Mechs -> `robots{}`,
    Titans -> `titans{}`); or
  * settle a `pending_roster` entry (one hand-recorded from the news before the
    robot reached the datamined roster, e.g. Angler) by filling only its
    still-null sourced fields and clearing the flag, so hand-curated data is
    never overwritten.

An auto-added entry can only carry what the pipeline can source: the in-house
version id (`release_date`) and the Steam depot `manifest_id`. Article-derived
fields (`release_context`, `source_article_ids`) are left null/[] for the
news-scraper or a human to fill.

Patch metadata lives once per build in `index/patch_manifests.json`, keyed by
manifest GID (`version`, `buildid`, `patch_released_at_utc`); a robot's
`manifest_id` points into it. `record_patch_manifests` merges in builds the
caller knows about, fill-only.

Id stability: a robot id is the Parser's slug of its localized name, so a rename
is rare. If a recorded ref leaves the roster the same run a new id appears, it is
reported as `orphaned` (a rename suspect): the new bot is still recorded, but a
human should confirm it is a real release. WRF does not retire robots, so an
orphan is itself worth eyeballing. Relic variants are distinct ids and distinct
robots, recorded like any other.

Console-I/O free: the caller presents the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .paths import (
    PATCHES_REL,
    RELEASE_DATES_REL,
    DataRepoError,
    load_json,
    objects_file,
    save_json,
)

# Per-build fields in index/patch_manifests.json, in file order.
PATCH_FIELDS = ("version", "buildid", "patch_released_at_utc")


@dataclass
class RecordResult:
    version: str
    new_bots: list[dict] = field(default_factory=list)      # freshly appended entries
    backfilled: list[dict] = field(default_factory=list)    # pending_roster entries settled
    orphaned_refs: list[str] = field(default_factory=list)  # recorded refs no longer in roster
    changed: bool = False

    @property
    def suspected_rename(self) -> bool:
        # A new id appearing while a recorded ref left the roster is more likely
        # a rename than a real simultaneous retire-and-release.
        return bool(self.new_bots and self.orphaned_refs)


@dataclass
class PatchResult:
    added: list[str] = field(default_factory=list)   # GIDs newly recorded
    filled: list[str] = field(default_factory=list)  # recorded GIDs given a still-null field
    conflicts: list[tuple[str, str, object, object]] = field(default_factory=list)
    """(gid, field, recorded value, offered value): kept the recorded one."""

    @property
    def changed(self) -> bool:
        return bool(self.added or self.filled)


# --- helpers -----------------------------------------------------------------
def virtual_bot_ref(bot_id: str) -> str:
    return f"OBJID_VirtualBot::{bot_id}"


def _bot_name(bot: dict) -> str:
    name = bot.get("name")
    if isinstance(name, dict):
        return name.get("en") or name.get("Key") or bot.get("id", "")
    return bot.get("id", "")


def read_roster(data_dir: Path) -> dict[str, dict]:
    """Return {bot_id: {'name', 'character_type'}} from the published roster."""
    raw = load_json(objects_file(data_dir, "VirtualBot"), "VirtualBot roster")
    return {
        bot_id: {"name": _bot_name(bot), "character_type": bot.get("character_type")}
        for bot_id, bot in raw.items()
    }


def load_release_dates(data_dir: Path) -> dict:
    path = Path(data_dir) / RELEASE_DATES_REL
    doc = load_json(path, "robot release dates")
    if not all(isinstance(doc.get(k), dict) for k in ("robots", "titans")):
        raise DataRepoError(f"robot release dates missing robots/titans objects keyed by ref: {path}")
    return doc


def load_patch_manifests(data_dir: Path) -> dict:
    path = Path(data_dir) / PATCHES_REL
    doc = load_json(path, "patch manifests")
    if not isinstance(doc.get("patches"), dict):
        raise DataRepoError(f"patch manifests missing patches object keyed by GID: {path}")
    return doc


def _new_entry(name: str, release_date, manifest_id) -> dict:
    """An entry in the file's field order for an auto-detected release."""
    return {
        "name": name,
        "release_date": release_date,
        "manifest_id": manifest_id,
        "pre_launch": False,
        "release_context": None,      # article-derived; not sourceable here
        "source_article_ids": [],     # ditto
    }


# --- detection + recording ---------------------------------------------------
def record_releases(
    data_dir: Path,
    version: str,
    manifest_id: str | None,
    *,
    write: bool = True,
) -> RecordResult:
    """Diff the roster against the release dates; append/settle; optionally save.

    Raises DataRepoError if the data repo can't be read. Only writes the file when
    something actually changed.
    """
    roster = read_roster(data_dir)
    doc = load_release_dates(data_dir)
    robots: dict[str, dict] = doc["robots"]
    titans: dict[str, dict] = doc["titans"]
    recorded = {**robots, **titans}

    result = RecordResult(version=version)

    for bot_id, meta in roster.items():
        ref = virtual_bot_ref(bot_id)
        entry = recorded.get(ref)

        if entry is None:
            # Genuinely new robot: add it under its ref.
            new = _new_entry(meta["name"], version, manifest_id)
            (titans if meta.get("character_type") == "Titan" else robots)[ref] = new
            result.new_bots.append({
                "id": bot_id, "name": meta["name"],
                "character_type": meta.get("character_type"),
                "release_date": version, "manifest_id": manifest_id,
            })
        elif entry.get("pending_roster"):
            # Hand-recorded from the news before it hit the roster (e.g. Angler): it
            # has now shipped, so fill only still-null sourced fields (never clobber).
            filled = {}
            for key, value in (("release_date", version), ("manifest_id", manifest_id)):
                if entry.get(key) is None and value:
                    entry[key] = value
                    filled[key] = value
            del entry["pending_roster"]
            result.backfilled.append({"id": bot_id, "name": meta["name"], "filled": filled})
        # else: already recorded; the dedup that makes this idempotent

    roster_refs = {virtual_bot_ref(b) for b in roster}
    result.orphaned_refs = sorted(
        ref for ref, e in recorded.items()
        if ref not in roster_refs and not e.get("pending_roster")
    )

    result.changed = bool(result.new_bots or result.backfilled)

    if result.changed:
        meta = doc.get("_meta")
        if isinstance(meta, dict):
            meta["robot_count"] = len(robots)
            meta["titan_count"] = len(titans)
            meta["robots_with_known_date"] = sum(1 for r in robots.values() if r.get("release_date"))
            meta["generated"] = date.today().isoformat()
        if write:
            save_json(Path(data_dir) / RELEASE_DATES_REL, doc)

    return result


def record_patch_manifests(
    data_dir: Path,
    builds: dict[str, dict],
    *,
    write: bool = True,
) -> PatchResult:
    """Merge `builds` ({gid: {version, buildid, patch_released_at_utc}}) into the file.

    Fill-only: a new GID is added; a recorded GID only gains fields still null there.
    A conflicting non-null value keeps the recorded one and is returned in
    `conflicts`. Only writes the file when something actually changed.
    """
    doc = load_patch_manifests(data_dir)
    patches: dict[str, dict] = doc["patches"]
    result = PatchResult()

    for gid, fields in builds.items():
        gid = str(gid)
        entry = patches.get(gid)
        if entry is None:
            patches[gid] = {k: fields.get(k) for k in PATCH_FIELDS}
            result.added.append(gid)
            continue
        for key in PATCH_FIELDS:
            value = fields.get(key)
            if value is None or entry.get(key) == value:
                continue
            if entry.get(key) is None:
                entry[key] = value
                if gid not in result.filled:
                    result.filled.append(gid)
            else:
                result.conflicts.append((gid, key, entry[key], value))

    if result.changed:
        # Chronological by version id (yyyy-mm-dd[-N] sorts lexically).
        doc["patches"] = dict(sorted(patches.items(), key=lambda kv: kv[1].get("version") or ""))
        meta = doc.get("_meta")
        if isinstance(meta, dict):
            meta["patch_count"] = len(patches)
            meta["generated"] = date.today().isoformat()
        if write:
            save_json(Path(data_dir) / PATCHES_REL, doc)

    return result
