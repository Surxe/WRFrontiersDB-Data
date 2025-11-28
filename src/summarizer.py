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
    
    def summarize_changes(self, parse_object_class: Literal['Module', 'Pilot', 'PilotTalent'],
                         before: dict, after: dict) -> dict[str, list[str]]:
        """Compare before/after content and generate summary lines.
        
        Args:
            parse_object_class: Type of objects being compared
            before: Content before the patch
            after: Content after the patch
            
        Returns:
            Dictionary mapping language codes to lists of summary lines
        """
        parse_object_class_to_name_getter = {
            'Module': self.get_name,
            'Pilot': self.get_first_last_name,
            'PilotTalent': self.get_name,
        }
        
        summary_lines = {lang: set() for lang in self.langs}
        
        for key, value in after.items():
            if not self.is_prod_ready(parse_object_class, value):
                continue
            
            def register(new_updated: Literal['Added', 'Updated']):
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
                    summary_lines[lang].add(f"* {new_updated} {type_string}{localized_name}")
            
            if key not in before:
                logger.debug(f"New {parse_object_class} detected: {key}")
                register('Added')
            else:
                before_value = before[key]
                if before_value != value:
                    logger.debug(f"Updated {parse_object_class} detected: {key}")
                    if not self.is_prod_ready(parse_object_class, before_value):
                        logger.debug(f"Previous version of {parse_object_class} {key} was not production ready, treating as new {parse_object_class.lower()}.")
                        register('Added')
                    else:
                        register('Updated')
        
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
        for obj_name, file_path in self.files_to_retrieve.items():
            logger.info(f"Retrieving changes for {obj_name} ({file_path})")
            
            before_content = self.get_archive_content(from_version, file_path)
            after_content = self.get_archive_content(to_version, file_path)
            
            logger.debug(f"Changes in {obj_name} ({file_path}):")
            
            langs_summary_lines = self.summarize_changes(obj_name, before_content, after_content)
            for lang in self.langs:
                all_langs_summary_lines[lang].extend(langs_summary_lines[lang])
            logger.info(f"Summary extended for each language.")
        
        # Write summary files
        summary_dir = os.path.join(self.summaries_dir, f"{from_version}_to_{to_version}")
        for lang, summary_lines in all_langs_summary_lines.items():
            if not summary_lines:
                logger.info(f"No changes detected for language {lang}, skipping summary file.")
                continue
            
            summary_lines = sorted(summary_lines)
            summary_file_path = os.path.join(summary_dir, f"{lang}.md")
            os.makedirs(summary_dir, exist_ok=True)
            with open(summary_file_path, encoding='utf-8', mode='w') as summary_file:
                summary_file.write('\n'.join(summary_lines))
                logger.info(f"Wrote summary for language {lang} to {summary_file_path} with {len(summary_lines)} lines.")


def main(from_version: Optional[str] = None, to_version: Optional[str] = None):
    """Main entry point for generating patch summaries."""
    setup_logger()
    summarizer = PatchSummarizer()
    summarizer.generate(from_version, to_version)


if __name__ == "__main__":
    main()