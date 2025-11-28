"""
1. Get the latest commit on a given branch
2. Get the git tag to determine the version it upgraded from
3. Summarize the changes between the two versions
"""

import json
from loguru import logger
from typing import Literal, Optional
import os
import sys

LANGS = ['id', 'en']

def setup_logger():
    logger.remove()
    logger.add(lambda msg: print(msg, end=''), level="DEBUG")
    logger.debug("Logger initialized.")

def get_archive_dir(version) -> str:
    archive_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'archive')
    version_archive_dir = os.path.join(archive_dir, version)
    return version_archive_dir

def get_archive_content(version: str, file_path: str) -> dict:
    version_archive_dir = get_archive_dir(version)
    file =  os.path.join(version_archive_dir, file_path)
    if not os.path.isfile(file):
        raise FileNotFoundError(f"Archive file not found: {file}")
    # Read as json
    with open(file, encoding='utf-8') as f:
        content = json.load(f)
    return content

def is_prod_ready(parse_object_class: Literal['Module', 'Pilot'], module_dict: dict) -> bool:
    if parse_object_class == 'Module':
        return module_dict.get("production_status", "NotReady") == "Ready"
    else:
        return True #pilots dont have prod status field. They seem to only be added when ready.

# For now, lang will be 'en' and retrieve from the 'name' field
#  or it will be 'id' and return just the id of the object and not the localization key
# In the future, this function should also accept the appropriate Localization/<lang>.json file,
# and use that to get localized names.
def localize(name_dict: dict, lang: str) -> str:
    """
    name_dict: {
        "Key": "module_code_name",
        "TableNamespace": "ModuleNamespace",
        "en": "English Name",
    }
    """
    if lang == 'en':
        return name_dict['en']
    else:
        raise ValueError(f"Unsupported language: {lang}")

def get_pilot_name(pilot_data: dict, lang: str) -> str:
    if lang == 'id':
        return pilot_data['id']
    first_name_data = pilot_data['first_name']
    second_name_data = pilot_data.get('second_name', None)
    localized_first_name = localize(first_name_data, lang)
    if second_name_data is None:
        return localized_first_name
    localized_second_name = localize(second_name_data, lang)
    if localized_second_name == " ":  # empty second name
        return localized_first_name
    return f"{localized_first_name} {localized_second_name}"

def get_module_name(module_data: dict, lang: str) -> str:
    if lang == 'id':
        return module_data['id']
    return localize(module_data['name'], lang)


def summarize_changes(parse_object_class: Literal['Module', 'Pilot', 'PilotTalent'], before: dict, after: dict) -> dict[str, list[str]]:
    """
    Summarize changes in Module.json content.
    
    Args:
        before: dict representing the Module.json content before the commit
        after: dict representing the Module.json content after the commit

    Returns:
        dict mapping language codes to lists of summary lines:
        {
            "en": ["* Added EngModuleName", "* Updated EngModuleName"],
            "id": ["* Added ModuleId", "* Updated ModuleId"],
        }
    """

    parse_object_class_to_name_getter = {
        'Module': get_module_name,
        'Pilot': get_pilot_name,
        'PilotTalent': get_module_name, # name is stored the same
    }

    # {"en": set(), "id": set()}
    summary_lines = {lang: set() for lang in LANGS} 
    # CMP_name_Nipper_Chassis and CMP_name_Nipper_Torso both translate to "Crix", so use a set to avoid duplicates. 
    # This also conveniently summarizes "Added Torso, Chassis, Shoulder of Crix" to just "Added Crix"

    for key, value in after.items():
        # Check if its production ready. We do not want to accidentally list unreleased modules
        if not is_prod_ready(parse_object_class, value):
            continue
        #logger.debug(f"Processing production ready module: {value['name']['Key']}")

        def register(new_updated: Literal['Added', 'Updated']):
            for lang in LANGS:
                name_getter_func = parse_object_class_to_name_getter[parse_object_class]
                localized_name = name_getter_func(value, lang)
                # Remove BOM and other special characters
                localized_name = localized_name.replace('\ufeff', '').replace('\u200b', '')
                type_string = ""
                if parse_object_class == 'PilotTalent':
                    type_string = "Pilot Talent "
                elif parse_object_class == 'Pilot':
                    type_string = "Pilot "
                    # dont prefix shoulders/weapons/torsos/chassis with "Module" since they will be confused. 
                    # The english will also be "Added Crix" so it would be confusing to be "Added Module Crix" when 
                    # its more like "Added Robot Crix" at that point
                summary_lines[lang].add(f"* {new_updated} {type_string}{localized_name}")
        
        if key not in before: # new parse object
            logger.debug(f"New {parse_object_class} detected: {key}")
            register('Added')
        else: # existing parse object, check for changes
            before_value = before[key]
            if before_value != value:
                logger.debug(f"Updated {parse_object_class} detected: {key}")
                # Check if the before version is not production ready. If its not, treat it as a new parse object.
                # e.g. Parse Object was added to files early as NotReady, then updated to Ready in later patch, but key is in both versions.
                # This makes sure they are added as 'Added' not 'Updated' (or even worse, the extreme case where its not added at all if the value didn't even change)
                if not is_prod_ready(parse_object_class, before_value):
                    logger.debug(f"Previous version of {parse_object_class} {key} was not production ready, treating as new {parse_object_class.lower()}.")
                    register('Added')
                else:
                    register('Updated')

    # Sort lines for consistent output
    return {lang: list(sorted(lines)) for lang, lines in summary_lines.items()}

def get_latest_two_versions() -> tuple[str, str]:
    archive_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'archive')
    versions = [d for d in os.listdir(archive_dir) if os.path.isdir(os.path.join(archive_dir, d))]
    versions = sorted(versions)
    previous_version = versions[-2]
    new_version = versions[-1]
    logger.info(f"Latest two versions detected: {previous_version} -> {new_version}")
    return previous_version, new_version

def main(from_version: Optional[str]=None, to_version: Optional[str]=None):
    setup_logger()
    
    if from_version is None and to_version is None:
        logger.debug(f"No versions provided, searching archive for latest two versions.")
        from_version, to_version = get_latest_two_versions()
    elif from_version is None or to_version is None:
        raise ValueError("Both from_version and to_version must be provided, or neither to auto-detect latest two versions.")


    # Make summaries at repo/summaries, where this file is in repo/src/summarizer.py
    summaries_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'summaries', 'patch')
    files_to_retrieve = {
        "Module": "Objects/Module.json",
        "Pilot": "Objects/Pilot.json",
        "PilotTalent": "Objects/PilotTalent.json",
    }
    all_langs_summary_lines = {lang: [] for lang in LANGS}
    for obj_name, file_path in files_to_retrieve.items():
        logger.info(f"Retrieving changes for {obj_name} ({file_path})")

        # Get before and after content
        before_content = get_archive_content(from_version, file_path)
        after_content = get_archive_content(to_version, file_path)

        logger.debug(f"Changes in {obj_name} ({file_path}):")

        # Summarize changes
        langs_summary_lines = summarize_changes(obj_name, before_content, after_content)
        for lang in LANGS:
            all_langs_summary_lines[lang].extend(langs_summary_lines[lang])
        logger.info(f"Summary extended for each language.")

    # Add summary to file
    summary_dir = os.path.join(summaries_dir, f"{from_version}_to_{to_version}")
    for lang, summary_lines in all_langs_summary_lines.items():
        if not summary_lines:
            logger.info(f"No changes detected for language {lang}, skipping summary file.")
            continue
        # Sort summary lines
        summary_lines = sorted(summary_lines)
        summary_file_path = os.path.join(summary_dir, f"{lang}.md")
        os.makedirs(summary_dir, exist_ok=True)
        with open(summary_file_path, encoding='utf-8', mode='w') as summary_file:
            summary_file.write('\n'.join(summary_lines))
            logger.info(f"Wrote summary for language {lang} to {summary_file_path} that has {len(summary_lines)} lines.")


if __name__ == "__main__":
    main()