import json
from loguru import logger
import os

from summarizer import get_archive_content

# RAN FROM REPO ROOT

ARCHIVE_DIR = 'archive'

# Setup logger
def setup_logger():
    logger.remove()
    logger.add(lambda msg: print(msg, end=''), level="INFO")
    logger.info("Logger initialized.")

def is_ref_str(str):
    return str.startswith('OBJID_')

def make_hashable(obj):
    """Convert a potentially nested structure to a hashable representation."""
    if isinstance(obj, dict):
        # Convert dict to sorted tuple of (key, value) pairs
        return tuple((k, make_hashable(v)) for k, v in sorted(obj.items()))
    elif isinstance(obj, list):
        # Convert list to tuple of hashable items
        return tuple(make_hashable(item) for item in obj)
    else:
        # Return the object as-is if it's already hashable
        return obj

def get_obj_ref_structure(data):
    """
    Get the minimal structure necessary to showcase where objects are referenced
    
    Example input data: {
        "module_classes_refs": [
            <ref>, <ref>, ...
        ]
        "module_faction_ref": <ref>
        "levels": {
            "constants": {}
            "variables": [
                {
                    "module_tag_ref": <ref>
                }
            ]
        }
    }

    Outputs: {
        "module_classes_refs": [
            "ref"
        ],
        "module_faction_ref": "ref"
        "levels": {
            "variables": [
                {
                    "module_tag_ref": "ref"
                }
            ]
        }
    }

    """
    result = {}
    
    for key, value in data.items():
        if isinstance(value, str) and is_ref_str(value):
            # If it's a reference string, include it with "ref" as value
            result[key] = "ref"
        elif isinstance(value, list):
            # Process lists to find references
            has_refs = False
            has_dict_with_refs = False
            processed_list = []
            
            for item in value:
                if isinstance(item, str) and is_ref_str(item):
                    # Mark that this list has references
                    has_refs = True
                elif isinstance(item, dict):
                    # Recursively process nested dictionaries in lists
                    nested_result = get_obj_ref_structure(item)
                    if nested_result:
                        processed_list.append(nested_result)
                        has_dict_with_refs = True
                # Non-ref strings and non-dict items are ignored
            
            # Create the result based on what was found
            if has_refs and has_dict_with_refs:
                # List has both direct refs and dicts with refs
                # Only deduplicate exact duplicates, not structural duplicates
                seen = set()
                unique_list = []
                for item in processed_list:
                    hashable_item = make_hashable(item)
                    if hashable_item not in seen:
                        seen.add(hashable_item)
                        unique_list.append(item)
                processed_list = unique_list
                processed_list.insert(0, "ref")  # Add "ref" at the beginning
                result[key] = processed_list
            elif has_refs:
                # List only has direct references
                result[key] = ["ref"]
            elif has_dict_with_refs:
                # List only has dicts with references - only deduplicate exact duplicates
                seen = set()
                unique_list = []
                for item in processed_list:
                    hashable_item = make_hashable(item)
                    if hashable_item not in seen:
                        seen.add(hashable_item)
                        unique_list.append(item)
                result[key] = unique_list
        elif isinstance(value, dict):
            # Recursively process nested dictionaries
            nested_result = get_obj_ref_structure(value)
            if nested_result:  # Only include if there are references in the nested structure
                result[key] = nested_result
    
    return result

def get_objs_ref_structure(objects):
    """Get the id structure of each obj and merge all objects together"""
    result = {}
    for obj in objects.values():
        obj_id_structure = get_obj_ref_structure(obj)
        result.update(obj_id_structure)
    return result

def get_objs_versions_ref_structure(versions: list, class_name: str):
    """Get the id structure of each version's objects and merge all versions together"""
    result = {}
    for version in versions:
        version_archive_content = get_archive_content(ARCHIVE_DIR, version, f'Objects/{class_name}.json')
        version_id_struct = get_objs_ref_structure(version_archive_content)
        result.update(version_id_struct)
    return result

def read_version_configs():
    with open('versions.json', 'r', encoding='utf-8') as f:
        version_configs = json.load(f)
    return version_configs

def main():
    setup_logger()

    version_configs = read_version_configs()
    versions_list = list(version_configs.keys())

    # Create entity_relationship dir
    entity_rel_dir = 'entity_relationships'
    os.makedirs(entity_rel_dir, exist_ok=True)
    # Empty it
    for file in os.listdir(entity_rel_dir):
        os.remove(os.path.join(entity_rel_dir, file))

    # Determine all class names by getting file names in latest version's archive dir
    class_names = os.listdir(os.path.join(ARCHIVE_DIR, versions_list[-1], 'Objects'))
    class_names = [class_name[:-len('.json')] for class_name in class_names if class_name.endswith('.json')]

    for class_name in class_names:
        id_struct = get_objs_versions_ref_structure(versions_list, class_name)
        if not id_struct:
            continue #if it has no references, dont bother creating a file
        logger.info(f"Id structure for {class_name} objects has {len(id_struct)} keys.")

        # Output to file
        with open(f'entity_relationships/{class_name}.json', 'w', encoding='utf-8') as f:
            json.dump(id_struct, f, indent=4)

if __name__ == '__main__':
    main()