"""Build `index/slug_map.json`: object id -> the URL path segment of its page.

An object's page is `/<route>/<slug>/` on the Site, and every other consumer (the
Discord bot, ...) links to it the same way, so this map is the one place slugs
are decided. Only objects with a page get an entry: membership in the map means
"published".

The rules per type, ported from the Site's former `slug_generator.ts`:

* Pilot: `<first name>-<last name>` (English).
* Module: `<module group name>-<module name>`, or `titan-shoulder-<side>-<robot id>`
  for titan shoulders; only `production_status == "Ready"` modules.
* CharacterPreset: factory presets by name; AI presets from the id (camelToKebab).
* VirtualBot (robots): the id itself. The Parser already made it from the robot's
  name, so it is copied, never re-slugified.
* Everything else: the English name.

Console-I/O free: problems come back in the result for the caller to report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .paths import SLUG_MAP_REL, DataRepoError, load_json, objects_file, save_json

# Object types that have pages, in the map's order.
OBJECT_TYPES = (
    "Module",
    "Pilot",
    "PilotTalent",
    "PilotTalentType",
    "PilotClass",
    "PilotPersonality",
    "ModuleCategory",
    "ModuleGroup",
    "Rarity",
    "CharacterPreset",
    "VirtualBot",
    "Currency",
    "CharacterClass",
    "Faction",
)

SlugMap = dict[str, str]


@dataclass
class SlugMapResult:
    slug_map: SlugMap
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """(object id, reason) for objects that should have a page but got no slug."""
    collisions: list[tuple[str, str, list[str]]] = field(default_factory=list)
    """(object type, slug, object ids) where one type uses a slug more than once."""
    changed: bool = False
    """The file on disk was different (or missing) and has been rewritten."""


# --- string helpers (match the Site's slug_base.ts exactly) -------------------
def to_slug(text: str) -> str:
    text = text.lower().replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def camel_to_kebab(text: str) -> str:
    """AI preset ids -> slugs: strip prefixes/suffixes, split camelCase, expand abbreviations."""
    text = re.sub(r"^DA_Preset_", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\.[0-9]+$", "", text)
    text = text.replace("_", "-")  # before the \b rules, so they see word boundaries
    text = re.sub(r"([a-z])([A-Z])", r"\1-\2", text)
    text = text.lower()
    text = re.sub(r"\badv\b", "advanced", text)
    text = re.sub(r"\bbegin\b", "beginner", text)
    text = re.sub(r"\binterm\b", "intermediate", text)
    text = re.sub(r"^(bot|devbot)-", "", text, flags=re.IGNORECASE)
    text = re.sub(r"-(bot|devbot)-", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def default_string(key) -> str | None:
    """English text of a localization key; InvariantString when it isn't localized."""
    if not key:
        return None
    if key.get("Key") and key.get("TableNamespace"):
        found = key.get("en") or key.get("InvariantString")
    else:
        found = key.get("InvariantString") or key.get("en")
    if not found:
        raise ValueError("localization key has no InvariantString or en text")
    return found


def ref_to_id(ref: str) -> str:
    """`OBJID_Class::id` -> `id`."""
    class_part, sep, object_id = ref.partition("::")
    if not sep or not class_part.startswith("OBJID_"):
        raise ValueError(f"invalid object reference: {ref}")
    return object_id.split("::")[0]


# --- per-type rules ------------------------------------------------------------
def _pilot_slug(pilot: dict) -> str:
    first = default_string(pilot.get("first_name")) or ""
    last = default_string(pilot.get("last_name") or pilot.get("second_name")) or ""
    return f"{to_slug(first)}-{to_slug(last)}".rstrip("-")


def _module_slug(module: dict, module_groups: dict[str, dict]) -> str:
    group_ref = module.get("module_group_ref")
    if group_ref and "titan-shoulder" in group_ref and module.get("shoulder_side") \
            and module.get("virtual_bot_ref"):
        side = "left" if module["shoulder_side"] == "L" else "right"
        return f"titan-shoulder-{side}-{ref_to_id(module['virtual_bot_ref'])}"

    name = default_string(module.get("name")) or ""
    group = module_groups.get(ref_to_id(group_ref)) if group_ref else None
    if group is None:
        return f"module-{to_slug(name)}".rstrip("-")
    group_name = group["name"].get("en") or default_string(group["name"]) or ""
    return f"{to_slug(group_name)}-{to_slug(name)}".rstrip("-")


def _character_preset_slug(preset: dict, object_id: str) -> str:
    if preset.get("is_factory_preset"):
        return to_slug(default_string(preset.get("name")) or "")
    return camel_to_kebab(preset.get("id", object_id))


def _currency_slug(currency: dict) -> str:
    name = currency.get("name") or {}
    return to_slug(name.get("en") or default_string(name) or "")


def _slug_for(object_type: str, object_id: str, obj: dict, module_groups: dict[str, dict]) -> str:
    if object_type == "Pilot":
        return _pilot_slug(obj)
    if object_type == "Module":
        return _module_slug(obj, module_groups)
    if object_type == "CharacterPreset":
        return _character_preset_slug(obj, object_id)
    if object_type == "VirtualBot":
        return object_id
    if object_type == "Currency":
        return _currency_slug(obj)
    return to_slug(default_string(obj.get("name")) or "")


def _has_page(object_type: str, obj: dict) -> bool:
    # A module without a status is not ready; other types have no status.
    return object_type != "Module" or obj.get("production_status") == "Ready"


# --- build / write ---------------------------------------------------------------
def build_slug_map(data_dir: Path) -> SlugMapResult:
    """Compute the slug map from `current/Objects`. Raises DataRepoError if a file is unreadable."""
    objects = {t: load_json(objects_file(data_dir, t), f"{t} objects") for t in OBJECT_TYPES}
    module_groups = objects["ModuleGroup"]

    result = SlugMapResult(slug_map={})
    by_type: dict[str, dict[str, list[str]]] = {}
    for object_type in OBJECT_TYPES:
        for object_id, obj in objects[object_type].items():
            if not _has_page(object_type, obj):
                continue
            try:
                slug = _slug_for(object_type, object_id, obj, module_groups)
            except (ValueError, KeyError, AttributeError, TypeError) as exc:
                result.skipped.append((object_id, f"{object_type}: {exc}"))
                continue
            if not slug:
                result.skipped.append((object_id, f"{object_type}: empty slug"))
                continue
            result.slug_map[object_id] = slug
            by_type.setdefault(object_type, {}).setdefault(slug, []).append(object_id)

    result.collisions = [
        (object_type, slug, ids)
        for object_type, slugs in by_type.items()
        for slug, ids in slugs.items()
        if len(ids) > 1
    ]
    return result


def write_slug_map(data_dir: Path) -> SlugMapResult:
    """Build the slug map and write `index/slug_map.json` if it changed."""
    result = build_slug_map(data_dir)
    path = Path(data_dir) / SLUG_MAP_REL
    try:
        current = load_json(path, "slug map")
    except DataRepoError:
        current = None
    if current != result.slug_map or list(current) != list(result.slug_map):
        save_json(path, result.slug_map)
        result.changed = True
    return result
