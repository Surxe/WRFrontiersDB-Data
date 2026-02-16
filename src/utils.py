from loguru import logger
import os
import json

def setup_logger():
    format_with_color = "<level>{level}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    logger.remove()
    logger.add(lambda msg: print(msg, end=''), level="INFO", format=format_with_color)
    logger.debug("Logger initialized.")

def read_entity_relationships(entity_relationships_dir: str):
    rels = {} #keyed by class name, extracted by class name.json
    for file in os.listdir(entity_relationships_dir):
        if file.endswith('.json'):
            with open(os.path.join(entity_relationships_dir, file), 'r', encoding='utf-8') as f:
                data = json.load(f)
                class_name = file[:-len('.json')]
                rels[class_name] = data
                logger.debug(f"Loaded entity relationship for {class_name} with {len(data)} entries.")
    return rels