"""Run the index tools by hand: `PYTHONPATH=tools python3 -m wrfdb_data <command>`.

Prints one JSON object with the result. Exit code: 0 ok, 1 error, and for
`releases`, 20 when a new robot was recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import deploy_record, nicknames, releases, slug_map
from .paths import DataRepoError, read_version

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NEW_RELEASE = 20

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2]


def _slug_map(args: argparse.Namespace) -> int:
    if args.no_write:
        result = slug_map.build_slug_map(args.data_dir)
    else:
        result = slug_map.write_slug_map(args.data_dir)
    _print({
        "slugs": len(result.slug_map), "changed": result.changed,
        "skipped": result.skipped, "collisions": result.collisions,
    })
    return EXIT_ERROR if result.collisions else EXIT_OK


def _nicknames(args: argparse.Namespace) -> int:
    if args.no_write:
        result = nicknames.build_nicknames(args.data_dir)
    else:
        result = nicknames.write_nicknames(args.data_dir)
    _print({
        "nicknames": len(result.nicknames), "changed": result.changed,
        "conflicts": result.conflicts, "ambiguous": result.ambiguous,
    })
    return EXIT_ERROR if result.conflicts else EXIT_OK


def _releases(args: argparse.Namespace) -> int:
    version = args.version or read_version(args.data_dir)
    write = not args.no_write
    result = releases.record_releases(args.data_dir, version, args.manifest_id, write=write)
    out = asdict(result) | {"suspected_rename": result.suspected_rename}
    if args.manifest_id:
        build = {"version": version, "buildid": args.buildid, "patch_released_at_utc": args.patch_utc}
        patches = releases.record_patch_manifests(args.data_dir, {args.manifest_id: build}, write=write)
        out["patches"] = asdict(patches)
    _print(out)
    return EXIT_NEW_RELEASE if result.new_bots else EXIT_OK


def _deploy_record(args: argparse.Namespace) -> int:
    record = deploy_record.build_record(args.data_dir, args.app_dir)
    if args.out:
        deploy_record.write_record(args.out, record)
    _print(record)
    return EXIT_OK


def _print(doc: dict) -> None:
    print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wrfdb_data", description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="WRFrontiersDB-Data checkout (default: the one these tools are in).")
    commands = parser.add_subparsers(dest="command", required=True)

    slugs = commands.add_parser("slug-map", help="Rebuild index/slug_map.json.")
    slugs.add_argument("--no-write", action="store_true", help="Build and report only.")
    slugs.set_defaults(run=_slug_map)

    nicks = commands.add_parser("nicknames", help="Rebuild index/nicknames.json.")
    nicks.add_argument("--no-write", action="store_true", help="Build and report only.")
    nicks.set_defaults(run=_nicknames)

    rel = commands.add_parser("releases", help="Record new robots (and optionally one build).")
    rel.add_argument("--version", help="In-house version id; default: current/version.txt.")
    rel.add_argument("--manifest-id", help="Steam depot manifest GID of this build (also "
                     "records it in index/patch_manifests.json).")
    rel.add_argument("--buildid", help="Steam buildid of this build.")
    rel.add_argument("--patch-utc", help="Build publish time, e.g. 2026-09-15T07:16:00Z.")
    rel.add_argument("--no-write", action="store_true", help="Detect only; do not modify index/.")
    rel.set_defaults(run=_releases)

    dep = commands.add_parser("deploy-record", help="Print (and write) a frontend build's deploy "
                              "record: which Data commit it was built from.")
    dep.add_argument("--app-dir", type=Path, default=Path.cwd(),
                     help="The frontend's checkout (default: the working directory).")
    dep.add_argument("--out", type=Path, help="Also write the record here, e.g. dist/deploy.json.")
    dep.set_defaults(run=_deploy_record)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except DataRepoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
