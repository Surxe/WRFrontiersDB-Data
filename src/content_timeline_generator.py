"""
Create a timeline of all the new content that has released over time.

TODO: Add it to the CI pipeline
"""

from datetime import datetime
import os
from loguru import logger
from typing import TypedDict

class SummaryEntry(TypedDict):
    lines: list[str]

def load_summaries(summaries_dir='summaries', lang_code='en') -> dict[str, list[str]]:
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
                summaries[from_to_version] = additions
        else:
            raise FileNotFoundError(f"Summary file not found: {file_to_read}")
    logger.info(f"Loaded summaries for {len(summaries)} version(s).")
    return summaries

class ContentTimelineGenerator:
    def __init__(self, summaries: SummaryEntry, lang_code='en'):
        if lang_code not in ['en', 'id']:
            raise ValueError("lang_code must be either 'en' or 'id'")
        
        self.summaries_dir = 'summaries'
        self.timeline_dir = os.path.join(self.summaries_dir, 'timeline')
        self.lang_code = lang_code
        self.summaries = summaries
        self.timeline_lines = self._generate_timeline()
        self._save_timeline(output_file=os.path.join(self.timeline_dir, f'content_timeline_{lang_code}.md'))

    def _generate_timeline(self):
        """
        Generate a timeline of content additions from summaries.
        Each entry contains the date, title, and description of the addition.
        """
        timeline_lines = ['# Added robots/pilots since the first public steam release']
        for from_to_version, additions in self.summaries.items():
            from_date, to_date = from_to_version.split('_to_')
            if self.lang_code == 'id':
                to_date = to_date
            elif self.lang_code == 'en':
                # 2025-11-15 -> November 15, 2025
                to_date = datetime.strptime(to_date, "%Y-%m-%d").strftime("%B %d, %Y")
            else:
                raise ValueError("lang_code invalid")
            
            if not additions:
                continue

            timeline_lines.append(f"## {to_date}")
            for addition in additions:
                timeline_lines.append(f"* {addition}")
            timeline_lines.append("")  # Add a blank line for spacing
               
        logger.info(f"Generated timeline with {len(timeline_lines)} entries.")
        return timeline_lines
    
    def _save_timeline(self, output_file:str):
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

if __name__ == "__main__":
    summaries_en = load_summaries(lang_code='en')
    ContentTimelineGenerator(summaries_en, lang_code='en')
    
    summaries_id = load_summaries(lang_code='id')
    ContentTimelineGenerator(summaries_id, lang_code='id')