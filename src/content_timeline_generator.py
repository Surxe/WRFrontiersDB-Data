"""
Create a timeline of all the new content that has released over time.

TODO: Add it to the CI pipeline
* Remove dupe Volta
* Remove early release pilots
"""

from datetime import datetime
import os
from loguru import logger
from typing import Literal
import json

from summarizer import VersionConfig, LANGS

def strip_list(list_of_str: list[str]) -> list[str]:
    if not list_of_str:
        return list_of_str
    first_elem = list_of_str[0]
    if first_elem.isspace() or first_elem == '':
        return strip_list(list_of_str[1:])
    last_elem = list_of_str[-1]
    if last_elem.isspace() or last_elem == '':
        return strip_list(list_of_str[:-1])
    return list_of_str

class ContentTimelineGenerator:
    def __init__(self, lang_code):
        if lang_code not in ['en', 'id']:
            raise ValueError("lang_code must be either 'en' or 'id'")
        
        self.summaries_dir = 'summaries'
        self.timeline_dir = os.path.join(self.summaries_dir, 'timeline')
        self.lang_code = lang_code
        self.summaries = self._load_categorize_summaries()
        self.versions_configs = load_versions_config()
        self._gen_timeline(self.summaries)

    def _load_summaries(self,
                        summaries_dir='summaries', 
                        lang_code='en', 
                        versions: Literal['all'] | list[str] = 'all'
                        ) -> dict[str, list[str]]:
        """
        From summaries/patch/<from_to_version>/<lang_code>.md,
        Save each line that starts with "* Added" into 
        a dict: {from_to_version: [lines]}
        """
        patch_dir = os.path.join(summaries_dir, 'patch')
        summaries = {}
        if not os.path.exists(patch_dir):
            logger.warning(f"Patch directory not found: {patch_dir}")
            return summaries

        for from_to_version in os.listdir(patch_dir): #from_to_version e.g. 2025-03-10_to_2025-03-13
            from_version, to_version = from_to_version.split('_to_')
            if not (versions == 'all' or to_version in versions):
                continue

            subdir_path = os.path.join(patch_dir, from_to_version)
            if not os.path.isdir(subdir_path):
                continue # e.g. summaries/.gitkeep
            file_to_read = os.path.join(subdir_path, f'{lang_code}.md')
            if os.path.isfile(file_to_read):
                additions = []
                with open(file_to_read, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('* Added '):
                            logger.debug(f"Found addition in {from_to_version}: {line.strip()}")
                            additions.append(line.strip().removeprefix('* Added '))
                if additions:
                    summaries[to_version] = additions
            else:
                raise FileNotFoundError(f"Summary file not found: {file_to_read}")
        logger.info(f"Loaded summaries for {len(summaries)} version(s).")
        return summaries

    def _load_categorize_summaries(self):
        summaries_en_per_season = {}
        for season_version, patch_versions in season_releases.items():
            summaries_en_per_season[season_version] = self._load_summaries(lang_code=self.lang_code, 
                                                                    versions=patch_versions)
        return summaries_en_per_season

    def _version_to_date(self, yyyy_mm_dd:str) -> str:
        """
        Convert a version string (YYYY-MM-DD) to a formatted date string.
        """
        if self.lang_code == 'id':
            return yyyy_mm_dd  # Keep as is for Indonesian
        elif self.lang_code == 'en':
            # 2025-11-15 -> November 15, 2025
            return datetime.strptime(yyyy_mm_dd, "%Y-%m-%d").strftime("%B %d, %Y")
        else:
            raise ValueError("lang_code invalid")

    def _gen_timeline(self, summaries: dict[str, dict[str, list[str]]]):
        """
        summaries example: {'2025-03-13': {'2025-03-15': ['line1']}} where 13 is season release date, 
            15 is patch release date in that season
        """
        
        timeline_lines = ['# Added robots/pilots since the first public steam release', '']
        for season_version, season_summaries in summaries.items():
            season_config = self.versions_configs[season_version]
            season_title = season_config["title"]

            timeline_lines.append(f"## {season_title}")
            timeline_lines.append("")  # Add a blank line for spacing

            for to_version, additions in season_summaries.items():
                version_config = self.versions_configs[to_version]
                to_date = self._version_to_date(version_config["date_utc"])
                patch_notes_url = version_config["patch_notes_url"]
                patch_md = f"[{to_date}]({patch_notes_url})" if patch_notes_url else f"{to_date}"

                if not additions:
                    continue

                timeline_lines.append(f"### {patch_md}")
                for addition in additions:
                    timeline_lines.append(f"* {addition}")
                timeline_lines.append("")  # Add a blank line for spacing
            timeline_lines.append("")  # Add a blank line after each season

        self.timeline_lines = strip_list(timeline_lines)
    
    def save_timeline(self, output_file:str):
        """
        Save the generated timeline to a markdown file.
        """
        if not output_file.endswith('.md'):
            raise ValueError("output_file must be a markdown file with .md extension")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in self.timeline_lines:
                f.write(line + '\n')
        logger.info(f"Timeline saved to {output_file}.")

def load_versions_config(config_path='versions.json') -> dict:
    """
    Load the versions configuration from a JSON file.
    """
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Versions config file not found: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        versions_config = json.load(f)
    logger.info(f"Loaded versions config with {len(versions_config)} entries.")
    return versions_config

def get_season_releases(version_configs: dict[str, VersionConfig]) -> dict[str, list[str]]:
    """
    Returns:
        {
            <version_that_is_a_season_release>: [version_that_is_a_patch_release, ... 
                for each version that appeared before that season and after the previous season]
        }
    """
    season_releases = {}
    # version_configs is already sorted in reverse such that the latest version is first
    # reverse the sort to process from oldest to newest
    version_configs = dict(sorted(version_configs.items(), key=lambda item: item[0]))
    previous_season_version = None
    for version, config in version_configs.items():
        if config.get('is_season_release', False):
            season_releases[version] = [version]  # Start with the season release itself
            previous_season_version = version
        else:
            if previous_season_version:
                season_releases[previous_season_version].append(version)
        
    return season_releases


if __name__ == "__main__":
    summaries_dir = 'summaries'
    timeline_dir = os.path.join(summaries_dir, 'timeline')

    # Season summmaries next
    versions_config_path = "versions.json"
    versions_config = load_versions_config(versions_config_path)

    season_releases = get_season_releases(versions_config)
    logger.info(f"Identified {len(season_releases)} season releases.")
    logger.debug(f"Season releases: {list(season_releases.keys())}")
    logger.debug(f"Season releases patches: {season_releases}")

    for lang in LANGS:
        gen = ContentTimelineGenerator(lang_code=lang)
        gen.save_timeline(output_file=os.path.join(timeline_dir, f'{lang}.md'))