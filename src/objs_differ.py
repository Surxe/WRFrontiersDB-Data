# Determines if an object has changed between two versions
# Accounts for production readiness status on both versions
# Accounts for dependent objects of each version

import json
import os
from loguru import logger
from typing import Literal

from summarizer import read_entity_relationships
from summarizer import setup_logger

setup_logger()

def load_json(object_file: str):
    # Json load
    with open(object_file, "r", encoding="utf-8") as f:
        return json.load(f)

def ref_to_id(ref: str):
    """OBJID_CharacterModule::char_123 -> char_123"""
    return ref.split("::")[-1]

def get_versions_data(archive_dir: str, which_versions: Literal['all', 'latest']='latest'):
    """
    Get data from all versions in the archive directory.
    
    Args:
        archive_dir: Path to the archive directory
        which_versions: Which versions to get - 'all' or 'latest'
    
    Returns:
        {
            "2026-02-10": {
                "Ability": {...},
                "BotAIPreset": {...},
                ...
            }
        }
    """
    all_versions_data = {}
    version_names = [d for d in os.listdir(archive_dir) if os.path.isdir(os.path.join(archive_dir, d))]
    logger.debug(f"Version names: {version_names}")

    if which_versions == 'latest':
        # Get the latest version
        version_names.sort()
        version_names = [version_names[-1]]
    elif which_versions == 'all':
        pass
    else:
        raise ValueError(f"Invalid versions value: {which_versions}")
        
    # Get all versions
    for version_name in version_names:
        version_dir = os.path.join(archive_dir, version_name)
        objects_dir = os.path.join(version_dir, "Objects")
        all_versions_data[version_name] = {}
        for object_file in os.listdir(objects_dir):
            object_name = object_file.split(".")[0]
            object_data = load_json(os.path.join(objects_dir, object_file))
            all_versions_data[version_name][object_name] = object_data
            logger.debug(f"Loaded {object_name} from {version_dir} with {len(object_data)} keys")

    return all_versions_data

def read_entity_dependencies():
    path = "entity_dependencies.json"
    return load_json(path)

def is_prod_ready(parse_object_class: str, 
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

def do_shit(my_entity_relationships: dict, parse_objects_data: dict):
    """

    Searches the entity's relationships for string fields. String fields will be a parse object class. 
    That same location in the parse_objects_data will have a object reference which can be converted to an object id.
    The object id's will be printed.
    Args:
        my_entity_relationships: {
            "Module": {
                "character_module_mounts": [
                    {
                        "character_ref": "CharacterModule",
                    }
                ]
            }
        }
        parse_objects_data: {
            "Module": {
                "character_module_mounts": [
                    {
                        "character_ref": "OBJID_CharacterModule::char_123",
                        "mount": "Side"
                    }
                ]
            }
        }

    Prints "char_123" for each character_ref
    """
    
    def traverse_and_extract(entity_data: dict|list|str, parse_data: dict|list|str, path: str = ""):
        """Recursively traverse entity relationships and extract object IDs from parse data."""
        if isinstance(entity_data, dict):
            for key, value in entity_data.items():
                current_path = f"{path}.{key}" if path else key
                traverse_and_extract(value, parse_data.get(key, {}), current_path)
        elif isinstance(entity_data, list):
            for i, item in enumerate(entity_data):
                current_path = f"{path}[{i}]" if path else f"[{i}]"
                traverse_and_extract(item, parse_data[i] if i < len(parse_data) else {}, current_path)
        elif isinstance(entity_data, str):
            # Found a string field - this is a parse object class
            # Look for the corresponding reference in parse data
            if parse_data and isinstance(parse_data, str) and parse_data.startswith("OBJID_"):
                obj_id = ref_to_id(parse_data)
                print(f"{path}: {entity_data} -> {obj_id}")
    
    # Process each entity class
    for entity_class, relationships in my_entity_relationships.items():
        if entity_class in parse_objects_data:
            print(f"\nProcessing entity class: {entity_class}")
            traverse_and_extract(relationships, parse_objects_data[entity_class])



class ObjsDiffer:
    def __init__(self, archive_dir: str):
        self.entity_relationships = read_entity_relationships("entity_relationships")
        self.entity_dependencies = read_entity_dependencies()
        self.all_versions_data = get_versions_data(archive_dir, "latest")

        do_shit(self.entity_relationships["Module"], self.all_versions_data["2026-02-10"]["Module"]["DA_Module_Ability_AmmoGenerator.1"])

    def has_obj_changed(self, 
                        parse_object_class: str, 
                        version_datas_before: dict, 
                        version_datas_after: dict, 
                        obj_before: dict, 
                        before_is_prod_ready: bool, 
                        obj_after: dict, 
                        after_is_prod_ready: bool
    ):
        """
        Check if this object has changed between versions, accounting for its dependent objects.
        
        Returns:
            bool: True if the object is production ready andhas changed, False otherwise
        """
        # Could merge some of these conditions, but this is more explicit imo

        if not obj_before and not obj_after:
            raise ValueError("Both obj_before and obj_after are None")
        elif obj_before and not obj_after: #object was removed
            return True
        elif not obj_before and obj_after: #object was added
            # Only consider it changed if its now prod ready
            if not after_is_prod_ready:
                return False
            else:
                return True
        elif obj_before and obj_after: #object still exists
            # If it wasnt prod ready, but now is, consider it changed
            if not before_is_prod_ready and after_is_prod_ready:
                return True
            # If it was prod ready, but now is not, consider it removed (changed)
            elif before_is_prod_ready and not after_is_prod_ready:
                return True
            # If it wasnt prod ready, and still isnt, dont consider it changed
            elif not before_is_prod_ready and not after_is_prod_ready:
                return False
            # If it was prod ready, and still is, check if the object itself changed
            elif before_is_prod_ready and after_is_prod_ready:
                if obj_before != obj_after: #if the direct content has changed, we already know its changed
                    return True
                else:
                    # Check if any dependent objects have changed
                    class_dependencies = self.entity_dependencies[parse_object_class]
                    class_relationships = self.entity_relationships[parse_object_class]

                    # Iterate class relationship key value pairs recursively till arriving at a string
                    # That string will be another object class to check
                    
                    pass


        else:
            raise ValueError("Unexpected state")

if __name__ == "__main__":
    differ = ObjsDiffer("archive")
    
    print("ObjsDiffer initialized")