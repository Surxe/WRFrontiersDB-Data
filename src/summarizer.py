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
        self.files_to_retrieve = {
            "Module": "Objects/Module.json",
            "Pilot": "Objects/Pilot.json",
            "PilotTalent": "Objects/PilotTalent.json",
        }
        self.changed_objects_file = os.path.join(repo_root, 'summaries', 'changed_objects.json')
        self.changed_objects = self.read_changed_objects()
    
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
                      obj_id: str,
                      objs: dict) -> bool:
        """Check if an object is production ready.
        
        Args:
            parse_object_class: Type of game object
            obj_dict: The object data dictionary
            
        Returns:
            True if production ready, False otherwise
        """
        obj = objs.get(obj_id)
        if obj is None: # If the object doesnt even exist, its not prod ready
            return False
        if parse_object_class == 'Module':
            return obj.get("production_status", "NotReady") == "Ready"
        else:
            # Pilots and talents only added when ready
            return True
    
    def get_changed_parse_objects(self, 
                                parse_object_class: Literal['Module', 'Pilot', 'PilotTalent'],
                                before: dict, after: dict
                                ) -> dict[str, bool]:
        """
        Get list of added parse objects between two versions.
        
        Args:
            parse_object_class: Type of objects being compared
            before: Content before the patch
            after: Content after the patch

        Returns:
            {changed_object_id: True}
        """
        changed_objects = {}

        for key, after_value in after.items():
            is_changed = False
            before_is_prod_ready = self.is_prod_ready(parse_object_class, key, before)
            after_is_prod_ready = self.is_prod_ready(parse_object_class, key, after)

            if key not in before:
                logger.debug(f"New {parse_object_class} detected: {key}")
                if not after_is_prod_ready:
                    logger.debug(f"{parse_object_class} {key} is not production ready, skipping.")
                    continue
                is_changed = True
            else:
                # existing object
                before_value = before[key]
                # If prev is not prod ready, and now is, consider it added
                if (not before_is_prod_ready) and after_is_prod_ready:
                    logger.debug(f"{parse_object_class} {key} became production ready, considering it Added.")
                    is_changed = True
                # If it was ready and now is not, consider it removed
                elif before_is_prod_ready and (not after_is_prod_ready):
                    logger.debug(f"{parse_object_class} {key} became not production ready, considering it Removed.")
                    is_changed = True
                # If it was ready and still is, check if the object itself changed
                elif before_is_prod_ready and after_is_prod_ready:
                    if before_value != after_value:
                        logger.debug(f"{parse_object_class} {key} changed.")
                        is_changed = True
            
            if is_changed:
                changed_objects[key] = True
        
        return changed_objects

    def read_changed_objects(self):
        """Reads the changed objects file and returns it as a dictionary."""
        if not os.path.exists(self.changed_objects_file):
            return {}
        with open(self.changed_objects_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_changed_objects(self):
        """Saves the changed objects file."""
        # deep order the changed objects
        for parse_object_class in self.changed_objects:
            for changed_object_id in self.changed_objects[parse_object_class]:
                self.changed_objects[parse_object_class][changed_object_id] = sorted(self.changed_objects[parse_object_class][changed_object_id])
        with open(self.changed_objects_file, 'w', encoding='utf-8') as f:
            json.dump(self.changed_objects, f, indent=4)
    
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
        
        # Retrieve the summary for each object type for each language
        changed_objects_per_object_type = {}
        for parse_object_class, file_path in self.files_to_retrieve.items():
            logger.info(f"Retrieving changes for {parse_object_class} ({file_path})")
            
            before_content = self.get_archive_content(from_version, file_path)
            after_content = self.get_archive_content(to_version, file_path)

            changed_objects = self.get_changed_parse_objects(parse_object_class, before_content, after_content)
            changed_objects_per_object_type[parse_object_class] = changed_objects

        # Add this patch to each changed object in the changed objects file
        for parse_object_class, changed_objects in changed_objects_per_object_type.items():
            for changed_object_id in changed_objects:
                if parse_object_class not in self.changed_objects:
                    self.changed_objects[parse_object_class] = {}
                if changed_object_id not in self.changed_objects[parse_object_class]:
                    self.changed_objects[parse_object_class][changed_object_id] = []
                # Add the object if not already added
                if to_version not in self.changed_objects[parse_object_class][changed_object_id]:
                    self.changed_objects[parse_object_class][changed_object_id].append(to_version)
        
        logger.info(f"Patch summary generation complete for {from_version} to {to_version}.")

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
    summarizer.save_changed_objects()

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