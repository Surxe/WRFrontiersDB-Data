import pytest
import sys
import os
from unittest.mock import Mock, patch

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from objs_differ import search_dependent_objects, read_entity_relationships, get_versions_data


class TestSearchDependentObjects:
    """Test cases for search_dependent_objects function."""

    @pytest.fixture
    def all_versions_data(self):
        """Load all available version data from archive."""
        return get_versions_data("archive", ["2025-10-21", "2025-10-28", "2025-12-23", "2026-01-20", "2026-01-27", "2026-02-10", "2026-02-13"])
    
    @pytest.fixture
    def entity_relationships(self):
        """Load actual entity relationships from project."""
        return read_entity_relationships("entity_relationships")

    def do_generic_test(self, all_versions_data, entity_relationships, entity_class, obj_id, before_version, after_version):
        version_data_before = all_versions_data[before_version]
        version_data_after = all_versions_data[after_version]
        result = search_dependent_objects(
            entity_relationships=entity_relationships,
            version_data_before=version_data_before,
            version_data_after=version_data_after,
            entity_class=entity_class,
            obj_id=obj_id
        )
        return result
    
    def test_hitcher_added(self, all_versions_data, entity_relationships):
        # hitcher previously didnt exist, then was added immediately as prod ready
        assert self.do_generic_test(all_versions_data, entity_relationships, "CharacterModule", "BP_Module_Hitcher_Chassis.0", "2025-12-23", "2026-01-20") is True
    
    def test_hitcher_ability_localization_changed(self, all_versions_data, entity_relationships):
        # module was not changed, but its ability localization was changed
        assert self.do_generic_test(all_versions_data, entity_relationships, "Module", "DA_Module_TorsoHitcher.1", "2026-01-27", "2026-02-10") is True

    def test_decker_released(self, all_versions_data, entity_relationships):
        # decker existed but wasnt prod ready, then was released as prod ready
        assert self.do_generic_test(all_versions_data, entity_relationships, "Module", "DA_Module_ChassisKernel.2", "2025-10-21", "2025-10-28") is True

    # TODO: Add more test cases as functionality is implemented
    # - Test object added/removed scenarios
    # - Test direct content changes
    # - Test dependency changes
    # - Test structural differences (missing keys)
    # - Test circular dependency handling
    # - Test edge cases (empty data, missing classes, etc.)
