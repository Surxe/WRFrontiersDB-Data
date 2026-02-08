import json
from loguru import logger
import os

from summarizer import get_archive_content

# Creates entity_relationships dir with json files of each class's minimal structure necessary to showcase where objects are referenced
# These files are not used for anything, they're just for reference
# Before the files are generated, their dict content is used to generate in placeholder.py

# RAN FROM REPO ROOT

ARCHIVE_DIR = 'archive'

# Setup logger
def setup_logger():
    logger.remove()
    logger.add(lambda msg: print(msg, end=''), level="INFO")
    logger.info("Logger initialized.")

def is_ref_str(str):
    return str.startswith('OBJID_')

def ref_to_cls(ref):
    """OBJID_Class::<id> -> Class"""
    return ref.split('::')[0].split('OBJID_')[1]

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
            'OBJID_ModuleClass::<id>', ...
        ]
        "module_faction_ref": 'OBJID_ModuleFaction::<id>'
        "levels": {
            "constants": {}
            "variables": [
                {
                    "module_tag_ref": 'OBJID_ModuleTag::<id>'
                }
            ]
        }
    }

    Outputs: {
        "module_classes_refs": [
            "ModuleClass"
        ],
        "module_faction_ref": "ModuleFaction"
        "levels": {
            "variables": [
                {
                    "module_tag_ref": "ModuleTag"
                }
            ]
        }
    }

    """
    result = {}
    
    for key, value in data.items():
        if isinstance(value, str) and is_ref_str(value):
            cls = ref_to_cls(value)
            # If it's a reference string, include it with "ref" as value
            result[key] = cls
        elif isinstance(value, list):
            # Process lists to find references
            has_refs = False
            has_dict_with_refs = False
            processed_list = []
            cls = None

            for item in value:
                if isinstance(item, str) and is_ref_str(item):
                    # Mark that this list has references
                    new_cls = ref_to_cls(item)
                    if cls and cls != new_cls:
                        raise ValueError(f"List has multiple classes: {cls} and {new_cls}")
                    cls = new_cls
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
                processed_list.insert(0, cls)  # Add "ref" at the beginning
                result[key] = processed_list
            elif has_refs:
                # List only has direct references
                result[key] = [cls]
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
        obj_ref_structure = get_obj_ref_structure(obj)
        result.update(obj_ref_structure)
    return result

def get_objs_versions_ref_structure(versions: list, class_name: str):
    """Get the id structure of each version's objects and merge all versions together"""
    result = {}
    for version in versions:
        version_archive_content = get_archive_content(ARCHIVE_DIR, version, f'Objects/{class_name}.json')
        version_ref_struct = get_objs_ref_structure(version_archive_content)
        result.update(version_ref_struct)
    return result

def read_version_configs():
    with open('versions.json', 'r', encoding='utf-8') as f:
        version_configs = json.load(f)
    return version_configs

def get_ref_structs():
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

    ref_structs = {}
    for class_name in class_names:
        ref_struct = get_objs_versions_ref_structure(versions_list, class_name)
        if not ref_struct:
            continue #if it has no references, dont bother creating a file
        logger.info(f"Id structure for {class_name} objects has {len(ref_struct)} keys.")

        ref_structs[class_name] = ref_struct

        # Output to file
        with open(f'entity_relationships/{class_name}.json', 'w', encoding='utf-8') as f:
            json.dump(ref_struct, f, indent=4)

    return ref_structs

def get_unique_string_values(nested_dict: dict):
    """
    Get the dependencies of an object.

    Example for ModuleCategory class:
    obj_ref_struct: {
        "module_type_ui_stats": [
            {
                "module_stat_ref": "ModuleStat"
            }
        ],
        "ui_stats_refs": [
            "ModuleStat"
        ]
    }

    Returns: [
        "ModuleStat"
    ]

    """

    # Iterate over all nested values recursively and return a list of all unique strings
    unique_strings = set()
    
    def extract_strings(obj):
        if isinstance(obj, str):
            unique_strings.add(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                extract_strings(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_strings(item)
        # Ignore other types
    
    extract_strings(nested_dict)
    return sorted(list(unique_strings))

def get_dependencies(ref_structs: dict[str, dict]):
    dependencies = {}
    for class_name, ref_struct in ref_structs.items():
        class_dependencies = get_unique_string_values(ref_struct)
        dependencies[class_name] = class_dependencies
        logger.info(f"Dependencies for {class_name}: {class_dependencies}")

    # Output to file
    with open('entity_dependencies.json', 'w', encoding='utf-8') as f:
        json.dump(dependencies, f, indent=4)

    return dependencies

def main():
    setup_logger()
    ref_structs = get_ref_structs()
    dependencies = get_dependencies(ref_structs)

if __name__ == '__main__':
    main()