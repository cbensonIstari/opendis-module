"""Core tests for opendis-module — covers all 5 functions and 15 test cases from spec."""

import json
import tempfile
from pathlib import Path

import pytest

from opendis_module.services.dis_converter import convert_dis_to_json
from opendis_module.services.dis_parser import parse_dis_file
from opendis_module.services.dis_validator import validate_dis_stream
from opendis_module.services.ecef_convert import ecef_to_geodetic
from opendis_module.services.entity_extractor import extract_entity_states
from opendis_module.services.scenario_analyzer import analyze_scenario


# ── L1: Parse multi-PDU stream ──────────────────────────────────────────────
class TestParseDISStream:
    def test_parse_scenario(self, scenario_file):
        """L1: Parse multi-PDU stream returns JSON with pdu_count and type breakdown."""
        result = parse_dis_file(scenario_file)
        assert result["pdu_count"] > 0
        assert "EntityStatePdu" in result["pdu_type_breakdown"]
        assert "FirePdu" in result["pdu_type_breakdown"]
        assert "DetonationPdu" in result["pdu_type_breakdown"]
        assert result["dis_version"] == 7
        assert result["exercise_id"] == 1
        assert len(result["pdus"]) == result["pdu_count"]

    def test_parse_single_entity(self, single_entity_file):
        """L2: Parse single entity returns all EntityStatePdu entries."""
        result = parse_dis_file(single_entity_file)
        assert result["pdu_count"] == 10
        for pdu in result["pdus"]:
            assert pdu["pdu_type"] == 1
            assert pdu["pdu_type_name"] == "EntityStatePdu"

    def test_parse_empty_file(self, empty_file):
        """L13: Empty file returns empty PDU list."""
        result = parse_dis_file(empty_file)
        assert result["pdu_count"] == 0
        assert result["pdus"] == []

    def test_parse_nonexistent_file(self):
        """L12: Nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_dis_file("/tmp/nonexistent_dis_file.dis")

    def test_parse_truncated_pdu(self, invalid_file):
        """L14: Truncated PDU is handled gracefully — parses what it can."""
        result = parse_dis_file(invalid_file)
        # Should not crash; may return 0 PDUs (since the only PDU is truncated)
        assert isinstance(result["pdu_count"], int)
        assert isinstance(result["pdus"], list)


# ── L3-L5: Extract Entity States ─────────────────────────────────────────────
class TestExtractEntityStates:
    def test_extract_all_entities(self, scenario_file):
        """L3: Extract all entities returns multiple entity tracks."""
        result = extract_entity_states(scenario_file)
        assert result["entity_count"] == 3
        for entity in result["entities"]:
            assert "entity_id" in entity
            assert "entity_id_string" in entity
            assert "track" in entity
            assert entity["state_count"] > 0

    def test_extract_filtered_entity(self, scenario_file):
        """L4: Extract filtered entity returns single entity track."""
        result = extract_entity_states(scenario_file, entity_id_filter=1)
        assert result["entity_count"] == 1
        entity = result["entities"][0]
        assert entity["entity_id"]["entity"] == 1
        assert entity["state_count"] == 10

    def test_ecef_to_geodetic_plausible(self, single_entity_file):
        """L5: ECEF to geodetic produces plausible lat/lon/alt."""
        result = extract_entity_states(single_entity_file)
        assert result["entity_count"] >= 1
        for entity in result["entities"]:
            for point in entity["track"]:
                geo = point["position_geodetic"]
                assert -90 <= geo["latitude_deg"] <= 90
                assert -180 <= geo["longitude_deg"] <= 180
                # Altitude should be reasonable (not NaN, not extreme)
                assert -1e6 < geo["altitude_m"] < 1e8

    def test_ecef_known_point(self):
        """Direct ECEF to geodetic test with a known point."""
        # Approximate: (0, 0, 6378137) should be near lat=90, lon=0, alt=~21km
        lat, lon, alt = ecef_to_geodetic(6378137.0, 0.0, 0.0)
        assert abs(lat) < 1  # Near equator
        assert abs(lon) < 1  # Near prime meridian
        assert abs(alt) < 100  # Near surface


# ── L6-L7: Analyze Scenario ──────────────────────────────────────────────────
class TestAnalyzeScenario:
    def test_analyze_scenario_basic(self, scenario_file):
        """L6: Analyze scenario returns entity_count, fire_events, detonation_events."""
        result = analyze_scenario(scenario_file)
        assert result["entity_count"] == 3
        assert len(result["fire_events"]) > 0
        assert len(result["detonation_events"]) > 0
        assert result["scenario_summary"]["total_pdus"] > 0

    def test_scenario_duration(self, scenario_file):
        """L7: Scenario duration is > 0."""
        result = analyze_scenario(scenario_file)
        assert result["scenario_summary"]["duration_seconds"] > 0

    def test_scenario_interactions(self, scenario_file):
        """Interactions summary computed correctly."""
        result = analyze_scenario(scenario_file)
        interactions = result["interactions"]
        assert interactions["total_fire_events"] == 3
        assert interactions["total_detonation_events"] == 2
        assert interactions["unique_engagements"] >= 1


# ── L8-L9: Convert DIS to JSON ───────────────────────────────────────────────
class TestConvertDISToJSON:
    def test_convert_basic(self, scenario_file):
        """L8: Convert to JSON with all fields preserved."""
        result = convert_dis_to_json(scenario_file)
        assert result["pdu_count"] > 0
        assert "file_size_bytes" in result
        assert result["file_size_bytes"] > 0
        for pdu in result["pdus"]:
            assert "pdu_type" in pdu
            assert "pdu_type_name" in pdu

    def test_convert_with_raw_bytes(self, scenario_file):
        """L9: Convert with include_raw_bytes=true includes hex strings."""
        result = convert_dis_to_json(scenario_file, include_raw_bytes=True)
        assert result["pdu_count"] > 0
        for pdu in result["pdus"]:
            assert "raw_bytes" in pdu
            assert isinstance(pdu["raw_bytes"], str)
            # Should be valid hex
            bytes.fromhex(pdu["raw_bytes"])


# ── L10-L11: Validate DIS Stream ─────────────────────────────────────────────
class TestValidateDISStream:
    def test_validate_good_stream(self, scenario_file):
        """L10: Valid stream returns is_valid=true, all checks passed."""
        result = validate_dis_stream(scenario_file)
        assert result["is_valid"] is True
        assert result["summary"]["checks_failed"] == 0
        assert result["summary"]["checks_passed"] > 0
        assert len(result["violations"]) == 0

    def test_validate_empty_file(self, empty_file):
        """L11 variant: Empty file returns is_valid=false."""
        result = validate_dis_stream(empty_file)
        assert result["is_valid"] is False
        assert len(result["violations"]) > 0


# ── L15: Istari wrapper format ────────────────────────────────────────────────
class TestIstariWrapperFormat:
    def test_wrapper_input_format(self, scenario_file):
        """L15: Module handles Istari wrapper input format correctly."""
        from opendis_module.functions.parse_dis_stream import parse_dis_stream

        input_json = json.dumps({
            "input_model": {
                "type": "user_model",
                "value": scenario_file,
            }
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = parse_dis_stream(input_json, temp_dir)
            assert len(outputs) == 2
            # Check output files exist
            for output in outputs:
                assert Path(output.path).exists()

            # Read the PDUs JSON
            pdus_output = next(o for o in outputs if o.name == "pdus_json")
            content = json.loads(Path(pdus_output.path).read_text())
            assert content["pdu_count"] > 0


# ── Parameter coercion tests (design challenge findings) ─────────────────────
class TestParameterCoercion:
    def test_entity_id_string_coercion(self, scenario_file):
        """entity_id parameter arrives as string — must be coerced to int."""
        from opendis_module.functions.extract_entity_states import extract_entity_states_fn

        input_json = json.dumps({
            "input_model": {"type": "user_model", "value": scenario_file},
            "entity_id": {"type": "parameter", "value": "1"},
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = extract_entity_states_fn(input_json, temp_dir)
            assert len(outputs) == 2
            entities_output = next(o for o in outputs if o.name == "entities_json")
            content = json.loads(Path(entities_output.path).read_text())
            assert content["entity_count"] == 1

    def test_include_raw_bytes_string_coercion(self, scenario_file):
        """include_raw_bytes parameter arrives as string 'true'."""
        from opendis_module.functions.convert_dis_to_json import convert_dis_to_json_fn

        input_json = json.dumps({
            "input_model": {"type": "user_model", "value": scenario_file},
            "include_raw_bytes": {"type": "parameter", "value": "true"},
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = convert_dis_to_json_fn(input_json, temp_dir)
            assert len(outputs) == 2
            data_output = next(o for o in outputs if o.name == "dis_data_json")
            content = json.loads(Path(data_output.path).read_text())
            assert "raw_bytes" in content["pdus"][0]

    def test_include_raw_bytes_false_string(self, scenario_file):
        """include_raw_bytes parameter as string 'false'."""
        from opendis_module.functions.convert_dis_to_json import convert_dis_to_json_fn

        input_json = json.dumps({
            "input_model": {"type": "user_model", "value": scenario_file},
            "include_raw_bytes": {"type": "parameter", "value": "false"},
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = convert_dis_to_json_fn(input_json, temp_dir)
            data_output = next(o for o in outputs if o.name == "dis_data_json")
            content = json.loads(Path(data_output.path).read_text())
            assert "raw_bytes" not in content["pdus"][0]
