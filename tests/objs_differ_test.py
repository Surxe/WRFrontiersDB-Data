import pytest
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from objs_differ import has_obj_changed, read_entity_relationships, get_versions_data, is_prod_ready


class TestObjDiffer:
    """Test cases for ObjsDiffer class."""

    @pytest.fixture
    def all_versions_data(self):
        """Load all available version data from archive."""
        return get_versions_data("archive", ["2025-08-12", "2025-08-19", "2025-10-21", "2025-10-28", "2025-12-23", "2026-01-20", "2026-01-27", "2026-02-10", "2026-02-13"])
    
    @pytest.fixture
    def entity_relationships(self):
        """Load actual entity relationships from project."""
        return read_entity_relationships("entity_relationships")

    def do_generic_test(self, all_versions_data, entity_relationships, entity_class, obj_id, before_version, after_version):
        version_data_before = all_versions_data[before_version]
        version_data_after = all_versions_data[after_version]
        result = has_obj_changed(
            entity_relationships,
            entity_class,
            version_data_before,
            version_data_after,
            obj_id,
            is_prod_ready(entity_class, version_data_before[entity_class].get(obj_id)),
            is_prod_ready(entity_class, version_data_after[entity_class].get(obj_id))
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

    def test_nonexistent_object(self, all_versions_data, entity_relationships):
        # object doesn't exist at all
        with pytest.raises(ValueError):
            self.do_generic_test(all_versions_data, entity_relationships, "Module", "DA_Module_ChassisKernel.20", "2025-10-21", "2025-10-28")

    def test_unchanged_object(self, all_versions_data, entity_relationships):
        # module was not changed, but its ability localization was changed
        assert self.do_generic_test(all_versions_data, entity_relationships, "Module", "DA_Module_ChassisHitcher.2", "2026-01-27", "2026-02-10") is False

    def test_progression_table_changed(self, all_versions_data, entity_relationships):
        # modules were added to progression table directly
        assert self.do_generic_test(all_versions_data, entity_relationships, "ProgressionTable", "DA_ProgressionTable.0", "2026-01-27", "2026-02-10") is True

    def test_progression_table_unchanged(self, all_versions_data, entity_relationships):
        # progression table was not changed, but module in it was changed. this is dependency-check exception, so it shouldnt be changed
        assert self.do_generic_test(all_versions_data, entity_relationships, "ProgressionTable", "DA_ProgressionTable.0", "2025-08-12", "2025-08-19") is False