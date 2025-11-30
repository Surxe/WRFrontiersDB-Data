"""
1. Get the latest commit on a given branch
2. Get the git tag to determine the version it upgraded from
3. Summarize the changes between the two versions
"""

import json
from loguru import logger
from typing import Literal, Optional, TypedDict
import os
from dotenv import load_dotenv

LANGS = ['id', 'en']

def setup_logger():
    logger.remove()
    logger.add(lambda msg: print(msg, end=''), level="DEBUG")
    logger.debug("Logger initialized.")


class VersionConfig(TypedDict):
    title: str
    date_utc: str
    manifest_id: str
    patch_notes_url: str
    is_season_release: bool

class PatchSummarizer:
    """Generates patch summaries by comparing game data between versions."""
    
    def __init__(self, repo_root: Optional[str] = None):
        """Initialize the summarizer.
        
        Args:
            repo_root: Path to repository root. If None, auto-detects from script location.
        """
        if repo_root is None:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.repo_root = repo_root
        self.archive_dir = os.path.join(repo_root, 'archive')
        self.summaries_dir = os.path.join(repo_root, 'summaries', 'patch')
        self.version_config_file = os.path.join(repo_root, 'versions.json')
        self.langs = LANGS
        self.files_to_retrieve = {
            "Module": "Objects/Module.json",
            "Pilot": "Objects/Pilot.json",
            "PilotTalent": "Objects/PilotTalent.json",
        }
    
    def get_version_archive_dir(self, version: str) -> str:
        """Get the directory path for a specific version in the archive."""
        return os.path.join(self.archive_dir, version)
    
    def get_archive_content(self, version: str, file_path: str) -> dict:
        """Load JSON content from an archived version.
        
        Args:
            version: Version string (e.g., "2025-06-03")
            file_path: Relative path to file within version archive (e.g., "Objects/Module.json")
            
        Returns:
            Parsed JSON content as dictionary
        """
        version_archive_dir = self.get_version_archive_dir(version)
        file = os.path.join(version_archive_dir, file_path)
        if not os.path.isfile(file):
            raise FileNotFoundError(f"Archive file not found: {file}")
        with open(file, encoding='utf-8') as f:
            content = json.load(f)
        logger.debug(f"Loaded archived content from {file} for version {version}, {len(content)} entries found.")
        return content
    
    def get_latest_two_versions(self) -> tuple[str, str]:
        """Auto-detect the latest two versions from archive directory.
        
        Returns:
            Tuple of (previous_version, new_version)
        """
        versions = [d for d in os.listdir(self.archive_dir) 
                   if os.path.isdir(os.path.join(self.archive_dir, d))]
        versions = sorted(versions)
        if len(versions) < 2:
            raise ValueError(f"Need at least 2 versions in archive, found {len(versions)}")
        previous_version = versions[-2]
        new_version = versions[-1]
        logger.info(f"Latest two versions detected: {previous_version} -> {new_version}")
        return previous_version, new_version
    
    @staticmethod
    def is_prod_ready(parse_object_class: Literal['Module', 'Pilot', 'PilotTalent'], 
                      obj_dict: dict) -> bool:
        """Check if an object is production ready.
        
        Args:
            parse_object_class: Type of game object
            obj_dict: The object data dictionary
            
        Returns:
            True if production ready, False otherwise
        """
        if parse_object_class == 'Module':
            return obj_dict.get("production_status", "NotReady") == "Ready"
        else:
            # Pilots and talents only added when ready
            return True
    
    @staticmethod
    def localize(name_dict: dict, lang: str) -> str:
        """Extract localized name from name dictionary.
        
        Args:
            name_dict: Dictionary with keys like "Key", "TableNamespace", "en"
            lang: Language code
            
        Returns:
            Localized string
        """
        if lang == 'en':
            return name_dict['en']
        else:
            raise NotImplementedError("Only 'en' localization is implemented at the moment.")
            # in the future this will need to be rewritten to lookup from localization tables
    
    @staticmethod
    def get_first_last_name(pilot_data: dict, lang: str) -> str:
        """Get the name, combining first and second names if present."""
        if lang == 'id':
            return pilot_data['id']
        first_name_data = pilot_data['first_name']
        second_name_data = pilot_data.get('second_name', None)
        localized_first_name = PatchSummarizer.localize(first_name_data, lang)
        if second_name_data is None:
            return localized_first_name
        localized_second_name = PatchSummarizer.localize(second_name_data, lang)
        if localized_second_name == " ":
            return localized_first_name
        return f"{localized_first_name} {localized_second_name}"
    
    @staticmethod
    def get_name(module_data: dict, lang: str) -> str:
        """Get the name."""
        if lang == 'id':
            return module_data['id']
        return PatchSummarizer.localize(module_data['name'], lang)
    
    def get_added_parse_objects(self, 
                                parse_object_class: Literal['Module', 'Pilot', 'PilotTalent'],
                                before: dict, after: dict
                                ) -> list[str]:
        """
        Get list of added parse objects between two versions.
        
        Args:
            parse_object_class: Type of objects being compared
            before: Content before the patch
            after: Content after the patch

        Returns:
            List of added object dictionaries
        """
        added_objects = []

        for key, value in after.items():
            is_added = False

            if key not in before:
                logger.debug(f"New {parse_object_class} detected: {key}")
                if not self.is_prod_ready(parse_object_class, value):
                    logger.debug(f"{parse_object_class} {key} is not production ready, skipping.")
                    continue
                is_added = True
            else:
                # existing object
                before_value = before[key]
                # If prev is not prod ready, and now is, consider it added
                if (not self.is_prod_ready(parse_object_class, before_value)) and \
                     self.is_prod_ready(parse_object_class, value):
                    logger.debug(f"{parse_object_class} {key} became production ready, considering it Added.")
                    is_added = True
            
            if is_added:
                added_objects.append(value)
        
        return added_objects

    def summarize_changes(self, 
                          parse_object_class: Literal['Module', 'Pilot', 'PilotTalent'],
                          added_objects: list[dict]
                          ) -> dict[str, list[str]]:
        """Compare before/after content and generate summary lines.
        
        Args:
            parse_object_class: Type of objects being compared
            added_objects: List of added object dictionaries
            
        Returns:
            Dictionary mapping language codes to lists of summary lines
        """
        parse_object_class_to_name_getter = {
            'Module': self.get_name,
            'Pilot': self.get_first_last_name,
            'PilotTalent': self.get_name,
        }
        
        summary_lines = {lang: set() for lang in self.langs}

        for value in added_objects:
            for lang in self.langs:
                name_getter_func = parse_object_class_to_name_getter[parse_object_class]
                localized_name = name_getter_func(value, lang)
                # Remove BOM and other special characters
                localized_name = localized_name.replace('\ufeff', '').replace('\u200b', '')
                type_string = ""
                if parse_object_class == 'PilotTalent':
                    type_string = "Pilot Talent "
                elif parse_object_class == 'Pilot':
                    type_string = "Pilot "
                summary_lines[lang].add(f"* Added {type_string}{localized_name}")
        
        return {lang: list(sorted(lines)) for lang, lines in summary_lines.items()}
    
    def generate(self, from_version: Optional[str] = None, to_version: Optional[str] = None):
        """Generate patch summary files.
        
        Args:
            from_version: Starting version. If None, auto-detects latest two versions.
            to_version: Ending version. If None, auto-detects latest two versions.
        """
        if from_version is None and to_version is None:
            logger.debug("No versions provided, searching archive for latest two versions.")
            from_version, to_version = self.get_latest_two_versions()
        elif from_version is None or to_version is None:
            raise ValueError("Both from_version and to_version must be provided, or neither to auto-detect.")
        
        all_langs_summary_lines = {lang: [] for lang in self.langs}
        
        # Retrieve the summary for each object type for each language
        for parse_object_class, file_path in self.files_to_retrieve.items():
            logger.info(f"Retrieving changes for {parse_object_class} ({file_path})")
            
            before_content = self.get_archive_content(from_version, file_path)
            after_content = self.get_archive_content(to_version, file_path)
            
            logger.debug(f"Changes in {parse_object_class} ({file_path}):")

            added_objects = self.get_added_parse_objects(parse_object_class, before_content, after_content)
            added_objects = self.summary_fixer(to_version, added_objects)
            
            langs_summary_lines = self.summarize_changes(parse_object_class, added_objects)

            for lang in self.langs:
                lang_summary_lines = langs_summary_lines[lang]

                all_langs_summary_lines[lang].extend(lang_summary_lines)
            logger.info(f"Summary extended for each language.")
        
        # Write summary files
        self.save_summaries(all_langs_summary_lines, from_version, to_version)
        
        logger.info(f"Patch summary generation complete for {from_version} to {to_version}.")

    def summary_fixer(self, 
                      version_name: str, 
                      added_objects: list[dict]
                      ) -> list[dict]:
        """
        Would call this summary_patcher, but patch is already used to represent the version in some cases.

        Sometimes the game data is updated to contain production ready items before they are actually ready.
        Or it may add variations of production ready items that aren't actually available to players.
        Unfortunately, there is no flag for "available_to_players" in the data.
        This function aims to remove these from the summaries. This will need to be updated manually if more are spotted.
        """

        """
        * DA_Module_ChassisSpire_3dVar01.2
        * DA_Module_ChassisSpire_3dVar02.2
        * DA_Module_ChassisSpire_3dVar03.2
        * DA_Module_ShoulderLSpire_3dVar01.0
        * DA_Module_ShoulderLSpire_3dVar02.0
        * DA_Module_ShoulderLSpire_3dVar03.0
        * DA_Module_ShoulderRSpire_3dVar01.0
        * DA_Module_ShoulderRSpire_3dVar02.0
        * DA_Module_TorsoSpire_3dVar01.0
        * DA_Module_TorsoSpire_3dVar02.0
        * DA_Module_TorsoSpire_3dVar03.0
        """

        modified_added_objects = []

        exclusions_by_version = {
            "2025-09-09": {
                "DA_Module_ChassisSpire_3dVar01.2": True,
                "DA_Module_ChassisSpire_3dVar02.2": True,
                "DA_Module_ChassisSpire_3dVar03.2": True,
                "DA_Module_ShoulderLSpire_3dVar01.0": True,
                "DA_Module_ShoulderLSpire_3dVar02.0": True,
                "DA_Module_ShoulderLSpire_3dVar03.0": True,
                "DA_Module_ShoulderRSpire_3dVar01.0": True,
                "DA_Module_ShoulderRSpire_3dVar02.0": True,
                "DA_Module_TorsoSpire_3dVar01.0": True,
                "DA_Module_TorsoSpire_3dVar02.0": True,
                "DA_Module_TorsoSpire_3dVar03.0": True,
                "DA_Pilot_Halloween_Dredge.0": True,
                "DA_Pilot_Halloween_Emma.0": True,
                "DA_Pilot_Rare_Giancarlo.0": True,
            }
        }

        for obj in added_objects:
            obj_id = obj.get('id', None)
            if obj_id is None:
                raise ValueError("Added object missing 'id' field.")

            exclusions_for_version = exclusions_by_version.get(version_name, {})
            if obj_id in exclusions_for_version:
                logger.info(f"Excluding {obj_id} from summary for version {version_name}.")
                continue

            modified_added_objects.append(obj)

        return modified_added_objects


    def save_summaries(self, all_langs_summary_lines, from_version: str, to_version: str):
        summary_dir = os.path.join(self.summaries_dir, f"{from_version}_to_{to_version}")

        for lang, summary_lines in all_langs_summary_lines.items():
            summary_file_path = os.path.join(summary_dir, f"{lang}.md")
            if not summary_lines:
                logger.info(f"No changes detected for language {lang}, skipping creation of summary file.")
                
                # If the summary file already exists, remove it
                if os.path.isfile(summary_file_path):
                    os.remove(summary_file_path)
                    logger.info(f"Existing summary file found, deleting it: {summary_file_path}")

                # If the parent dir is empty, remove it
                if os.path.isdir(summary_dir) and not os.listdir(summary_dir):
                    os.rmdir(summary_dir)
                    logger.info(f"Removed empty summary directory: {summary_dir}")
                
            else:
                summary_lines = sorted(summary_lines)
                os.makedirs(summary_dir, exist_ok=True)
                with open(summary_file_path, encoding='utf-8', mode='w') as summary_file:
                    summary_file.write('\n'.join(summary_lines))
                    logger.info(f"Wrote summary for language {lang} to {summary_file_path} with {len(summary_lines)} lines.")

    def load_versions_config(self) -> dict[str, VersionConfig]:
        """
        Load versions from version_config_file
        """
        if not os.path.isfile(self.version_config_file):
            raise FileNotFoundError(f"Version config file not found: {self.version_config_file}")
        with open(self.version_config_file, 'r', encoding='utf-8') as f:
            versions_config = json.load(f)
        return versions_config

    def generate_all(self):
        """
        For each version in version_config_file, generate patch summaries
        """
        versions_config = self.load_versions_config()
        sorted_versions = sorted(versions_config.keys())
        for i in range(1, len(sorted_versions)):
            from_version = sorted_versions[i-1]
            to_version = sorted_versions[i]
            logger.info(f"Generating patch summary from {from_version} to {to_version}")
            self.generate(from_version, to_version)


def main(from_version: Optional[str] = None, to_version: Optional[str] = None, gen_all: bool = False):
    """Main entry point for generating patch summaries."""
    setup_logger()
    logger.info(f"Inputs: from_version={from_version}, to_version={to_version}, gen_all={gen_all}")
    summarizer = PatchSummarizer()
    if gen_all:
        summarizer.generate_all()
    else:
        summarizer.generate(from_version, to_version)

if __name__ == "__main__":
    import sys
    load_dotenv()
    from_ver = os.getenv('FROM_VERSION')
    # If env var is empty string, treat as None
    if from_ver == '': from_ver = None
        
    to_ver = os.getenv('TO_VERSION')
    if to_ver == '': to_ver = None

    gen_all = os.getenv('GEN_ALL', 'false').lower() == 'true'

    main(from_ver, to_ver, gen_all)