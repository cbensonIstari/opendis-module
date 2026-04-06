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


# ── PlotScenario ────────────────────────────────────────────────────────────
class TestPlotScenario:
    def test_plot_scenario_produces_png(self, scenario_file):
        """PlotScenario produces a PNG file with entity trajectories."""
        from opendis_module.functions.plot_scenario import plot_scenario

        input_json = json.dumps({
            "input_model": {"type": "user_model", "value": scenario_file},
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = plot_scenario(input_json, temp_dir)
            assert len(outputs) == 2

            plot_output = next(o for o in outputs if o.name == "scenario_plot_png")
            assert Path(plot_output.path).exists()
            assert Path(plot_output.path).suffix == ".png"
            # PNG files start with magic bytes
            png_data = Path(plot_output.path).read_bytes()
            assert png_data[:4] == b"\x89PNG"
            assert len(png_data) > 1000  # Non-trivial image

            metadata_output = next(o for o in outputs if o.name == "metadata")
            metadata = json.loads(Path(metadata_output.path).read_text())
            assert metadata["function"] == "PlotScenario"
            assert metadata["entity_count"] == 3
            assert metadata["pdu_count"] > 0
            assert metadata["output_dpi"] == 200

    def test_plot_scenario_single_entity(self, single_entity_file):
        """PlotScenario works with a single entity."""
        from opendis_module.functions.plot_scenario import plot_scenario

        input_json = json.dumps({
            "input_model": {"type": "user_model", "value": single_entity_file},
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = plot_scenario(input_json, temp_dir)
            assert len(outputs) == 2
            plot_output = next(o for o in outputs if o.name == "scenario_plot_png")
            assert Path(plot_output.path).exists()
            metadata = json.loads(
                Path(next(o for o in outputs if o.name == "metadata").path).read_text()
            )
            assert metadata["entity_count"] == 1

    def test_plot_scenario_empty_file(self, empty_file):
        """PlotScenario handles empty DIS file gracefully (no entities)."""
        from opendis_module.functions.plot_scenario import plot_scenario

        input_json = json.dumps({
            "input_model": {"type": "user_model", "value": empty_file},
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = plot_scenario(input_json, temp_dir)
            assert len(outputs) == 2
            metadata = json.loads(
                Path(next(o for o in outputs if o.name == "metadata").path).read_text()
            )
            assert metadata["entity_count"] == 0
            assert metadata["pdu_count"] == 0

    def test_plot_scenario_nonexistent_file(self):
        """PlotScenario raises ValueError for nonexistent file."""
        from opendis_module.functions.plot_scenario import plot_scenario

        input_json = json.dumps({
            "input_model": {"type": "user_model", "value": "/tmp/nonexistent.dis"},
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(ValueError, match="PlotScenario failed"):
                plot_scenario(input_json, temp_dir)

    def test_plot_scenario_registered(self):
        """PlotScenario is registered in FUNCTIONS."""
        from opendis_module.functions.registry import FUNCTIONS
        assert "PlotScenario" in FUNCTIONS


# ── ParseDISCapture ────────────────────────────────────────────────────────
class TestParseDISCapture:
    def test_parse_raw_binary_capture(self, scenario_file):
        """ParseDISCapture handles raw binary DIS files (.dis)."""
        from opendis_module.services.capture_parser import parse_dis_capture

        result = parse_dis_capture(scenario_file)
        assert result["capture_format"] == "raw_binary"
        assert result["total_pdus"] > 0
        assert result["entity_count"] == 3
        assert "EntityStatePdu" in result["pdu_type_breakdown"]
        assert result["statistics"]["total_entity_state_updates"] > 0
        assert result["statistics"]["entity_count"] == 3

    def test_parse_pcap_capture(self, pcap_file):
        """ParseDISCapture handles PCAP files with DIS payloads."""
        from opendis_module.services.capture_parser import parse_dis_capture

        result = parse_dis_capture(pcap_file)
        assert result["capture_format"] == "pcap"
        assert result["total_pdus"] == 6  # 4 entity states + 1 fire + 1 detonation
        assert result["entity_count"] == 2
        assert "EntityStatePdu" in result["pdu_type_breakdown"]
        assert "FirePdu" in result["pdu_type_breakdown"]
        assert "DetonationPdu" in result["pdu_type_breakdown"]

    def test_entity_timelines(self, scenario_file):
        """ParseDISCapture groups entities and builds timelines with positions."""
        from opendis_module.services.capture_parser import parse_dis_capture

        result = parse_dis_capture(scenario_file)
        for entity in result["entities"]:
            assert "entity_id" in entity
            assert "entity_id_string" in entity
            assert "timeline" in entity
            assert entity["state_count"] > 0
            for point in entity["timeline"]:
                assert "timestamp" in point
                assert "position_ecef" in point
                assert "position_geodetic" in point
                assert "orientation_rad" in point
                assert "velocity_mps" in point
                assert "damage_state" in point
                geo = point["position_geodetic"]
                assert -90 <= geo["latitude_deg"] <= 90
                assert -180 <= geo["longitude_deg"] <= 180

    def test_entity_speed_stats(self, scenario_file):
        """ParseDISCapture computes per-entity speed statistics."""
        from opendis_module.services.capture_parser import parse_dis_capture

        result = parse_dis_capture(scenario_file)
        for entity in result["entities"]:
            if entity["state_count"] >= 2:
                assert entity["speed_stats"] is not None
                assert "min_mps" in entity["speed_stats"]
                assert "max_mps" in entity["speed_stats"]
                assert "avg_mps" in entity["speed_stats"]

    def test_damage_state_extraction(self, scenario_file):
        """ParseDISCapture extracts damage state from entity appearance bits."""
        from opendis_module.services.capture_parser import parse_dis_capture

        result = parse_dis_capture(scenario_file)
        for entity in result["entities"]:
            for point in entity["timeline"]:
                assert point["damage_state"] in (
                    "no_damage", "slight", "moderate", "destroyed", "unknown"
                )

    def test_statistics_summary(self, scenario_file):
        """ParseDISCapture produces correct summary statistics."""
        from opendis_module.services.capture_parser import parse_dis_capture

        result = parse_dis_capture(scenario_file)
        stats = result["statistics"]
        assert stats["total_entity_state_updates"] == 30  # 3 entities * 10 states
        assert stats["total_fire_events"] == 3
        assert stats["total_detonation_events"] == 2
        assert stats["entity_count"] == 3
        assert stats["duration_seconds"] >= 0

    def test_empty_file(self, empty_file):
        """ParseDISCapture handles empty files gracefully."""
        from opendis_module.services.capture_parser import parse_dis_capture

        result = parse_dis_capture(empty_file)
        assert result["total_pdus"] == 0
        assert result["entity_count"] == 0
        assert result["entities"] == []
        assert result["all_pdus"] == []

    def test_nonexistent_file(self):
        """ParseDISCapture raises FileNotFoundError for missing files."""
        from opendis_module.services.capture_parser import parse_dis_capture

        with pytest.raises(FileNotFoundError):
            parse_dis_capture("/tmp/nonexistent_capture.pcap")

    def test_istari_wrapper_format(self, scenario_file):
        """ParseDISCapture works with Istari wrapper input format."""
        from opendis_module.functions.parse_dis_capture import parse_dis_capture_fn

        input_json = json.dumps({
            "input_model": {
                "type": "user_model",
                "value": scenario_file,
            }
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = parse_dis_capture_fn(input_json, temp_dir)
            assert len(outputs) == 2

            capture_output = next(o for o in outputs if o.name == "capture_json")
            assert Path(capture_output.path).exists()
            content = json.loads(Path(capture_output.path).read_text())
            assert content["total_pdus"] > 0
            assert content["entity_count"] == 3

            metadata_output = next(o for o in outputs if o.name == "metadata")
            metadata = json.loads(Path(metadata_output.path).read_text())
            assert metadata["function"] == "ParseDISCapture"
            assert metadata["total_pdus"] > 0

    def test_pcap_istari_wrapper(self, pcap_file):
        """ParseDISCapture Istari wrapper works with PCAP files."""
        from opendis_module.functions.parse_dis_capture import parse_dis_capture_fn

        input_json = json.dumps({
            "input_model": {
                "type": "user_model",
                "value": pcap_file,
            }
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = parse_dis_capture_fn(input_json, temp_dir)
            assert len(outputs) == 2

            capture_output = next(o for o in outputs if o.name == "capture_json")
            content = json.loads(Path(capture_output.path).read_text())
            assert content["capture_format"] == "pcap"
            assert content["entity_count"] == 2

    def test_registered(self):
        """ParseDISCapture is registered in FUNCTIONS."""
        from opendis_module.functions.registry import FUNCTIONS
        assert "ParseDISCapture" in FUNCTIONS
