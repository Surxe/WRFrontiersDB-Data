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

def is_id_key(key):
    # Return true if the key ends with '_id' or '_ids'
    return key.endswith('_id') or key.endswith('_ids')

def print_id_keys(my_dict):
    """
    Iterate dictionary recursively, printing all id keys
    """
    for key, value in my_dict.items():
        if is_id_key(key):
            print(key)
        if isinstance(value, dict):
            print_id_keys(value)

def get_obj_id_structure(my_dict):
    """
    Get the minimal structure necessary to showcase where the id keys are referenced
    
    Example input my_dict: {
        "module_classes_ids": [
            <id>, <id>, ...
        ]
        "module_faction_id": <id>
        "levels": {
            "constants": {}
            "variables": [
                {
                    "module_tag_id": <id>
                }
            ]
        }
    }

    Outputs: {
        "module_classes_ids": [
            "id"
        ],
        "module_faction_id": "id"
        "levels": {
            "variables": [
                {
                    "module_tag_id": "id"
                }
            ]
        }
    }

    """
    result = {}
    
    for key, value in my_dict.items():
        if is_id_key(key):
            # If it's an ID key, include it with "id" as value
            if isinstance(value, list):
                # For lists of IDs, include a list with single "id"
                result[key] = ["id"]
            else:
                # For single ID values, use "id"
                result[key] = "id"
        elif isinstance(value, dict):
            # Recursively process nested dictionaries
            nested_result = get_obj_id_structure(value)
            if nested_result:  # Only include if there are ID keys in the nested structure
                result[key] = nested_result
        elif isinstance(value, list):
            # Process lists to find objects with ID keys
            processed_list = []
            for item in value:
                if isinstance(item, dict):
                    nested_result = get_obj_id_structure(item)
                    if nested_result:
                        processed_list.append(nested_result)
                # Non-dict items in lists are ignored unless they're direct ID values (handled above)
            
            if processed_list:  # Only include the list if it has items with ID keys
                result[key] = processed_list
    
    return result

def get_objs_id_structure(objects):
    """Get the id structure of each obj and merge all objects together"""
    result = {}
    for obj in objects.values():
        obj_id_structure = get_obj_id_structure(obj)
        result.update(obj_id_structure)
    return result

def get_objs_versions_id_structure(versions: list, class_name: str):
    """Get the id structure of each version's objects and merge all versions together"""
    result = {}
    for version in versions:
        version_archive_content = get_archive_content(ARCHIVE_DIR, version, f'Objects/{class_name}.json')
        version_id_struct = get_objs_id_structure(version_archive_content)
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
        id_struct = get_objs_versions_id_structure(versions_list, class_name)
        if not id_struct:
            continue #if it has no references, dont bother creating a file
        logger.info(f"Id structure for {class_name} objects has {len(id_struct)} keys.")

        # Output to file
        with open(f'entity_relationships/{class_name}.json', 'w', encoding='utf-8') as f:
            json.dump(id_struct, f, indent=4)

if __name__ == '__main__':
    main()