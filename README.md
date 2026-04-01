# opendis-module

Istari integration module for parsing IEEE 1278.1 DIS (Distributed Interactive Simulation) binary PDU streams. Converts raw DIS protocol data into structured JSON for entity tracking, scenario analysis, protocol validation, and digital thread integration.

**Domain:** 2.6 Mission Models
**Standard:** IEEE 1278.1-2012 (DIS Protocol v7)
**Pattern:** A: Pure Python (opendis)

| | |
|---|---|
| **Platform** | [Live System](https://demo.istari.app/systems/ab9cb5f9-ee0a-4204-b918-a4bb540cb10c) |
| **Functions** | 5 |
| **Tests** | 20/20 unit, 5/5 binary, 5/5 platform E2E |
| **Binary** | `opendis_module` (PyInstaller, macOS arm64) |

---

## Architecture

```
                          ┌──────────────────────┐
                          │  Istari Agent         │
                          │  Job dispatch         │
                          └──────┬───────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  opendis_module binary    │
                    │  (__main__.py CLI)        │
                    │  ParseDISStream           │
                    │  ExtractEntityStates      │
                    │  AnalyzeScenario          │
                    │  ConvertDISToJSON         │
                    │  ValidateDISStream        │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
     ┌────────▼───────┐  ┌──────▼────────┐  ┌──────▼──────────┐
     │  dis_parser.py  │  │ ecef_convert  │  │ dis_validator   │
     │  PDU decoding   │  │ ECEF→geodetic │  │ protocol checks │
     └────────────────┘  └───────────────┘  └─────────────────┘
              │
              ▼
     ┌────────────────┐
     │  opendis lib   │
     │  IEEE 1278.1   │
     └────────────────┘
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| opendis | >=1.0 | IEEE 1278.1 DIS protocol implementation |
| pydantic | ^2.0 | Input/output validation |
| Python | >=3.12,<3.13 | Runtime |

---

## Functions

### 1. ParseDISStream

Parse a binary DIS PDU stream into structured JSON. Decodes all PDU types (EntityState, Fire, Detonation) with full field extraction.

**Input:** `.dis` or `.bin` file containing DIS PDU binary data
**Output:** `pdus.json` + `metadata.json`

<details>
<summary>Sample output (from platform job 1de6b878-cb6a-4d32-be0d-f69351023cfc)</summary>

```json
{
  "source_file": "scenario_basic.dis",
  "pdu_count": 35,
  "pdu_type_breakdown": {
    "EntityStatePdu": 30,
    "FirePdu": 3,
    "DetonationPdu": 2
  },
  "dis_version": 7,
  "exercise_id": 1,
  "pdus": [
    {
      "index": 0,
      "pdu_type": 1,
      "pdu_type_name": "EntityStatePdu",
      "protocol_version": 7,
      "exercise_id": 1,
      "timestamp": 0,
      "length": 144,
      "entity_id": { "site": 42, "application": 1, "entity": 1 },
      "force_id": 1,
      "entity_type": {
        "kind": 1, "domain": 1, "country": 225,
        "category": 1, "subcategory": 1
      },
      "entity_location": {
        "x": 4500000.0, "y": 200000.0, "z": 4200000.0
      },
      "entity_orientation": {
        "psi": 1.57, "theta": 0.0, "phi": 0.0
      },
      "entity_linear_velocity": {
        "x": 10.0, "y": 0.0, "z": 0.0
      }
    }
  ]
}
```
</details>

[Download sample output](https://demo.istari.app/artifacts/a311b153-44ae-469f-b537-986a3aec7bff) (25,497 bytes)

---

### 2. ExtractEntityStates

Extract entity state timelines with automatic ECEF-to-geodetic coordinate conversion. Optionally filter by entity ID.

**Input:** `.dis` or `.bin` file + optional `entity_id` parameter
**Output:** `entities.json` + `metadata.json`

<details>
<summary>Sample output (from platform job 7f3b973b-a91e-4e23-86fa-0072f8f81bc5)</summary>

```json
{
  "source_file": "scenario_basic.dis",
  "entity_count": 3,
  "entities": [
    {
      "entity_id": { "site": 42, "application": 1, "entity": 1 },
      "entity_id_string": "42.1.1",
      "track": [
        {
          "timestamp": 0,
          "position_ecef": {
            "x": 4500000.0, "y": 200000.0, "z": 4200000.0
          },
          "position_geodetic": {
            "latitude_deg": 43.195398,
            "longitude_deg": 2.544804,
            "altitude_m": -209430.026
          },
          "orientation_rad": {
            "psi": 1.57, "theta": 0.0, "phi": 0.0
          },
          "linear_velocity": {
            "x": 10.0, "y": 0.0, "z": 0.0
          }
        }
      ]
    }
  ]
}
```
</details>

---

### 3. AnalyzeScenario

Analyze a DIS scenario: entity counts, fire/detonation events, engagement timeline, force composition.

**Input:** `.dis` or `.bin` file
**Output:** `scenario_analysis.json` + `metadata.json`

<details>
<summary>Sample output (from platform job 380b9893-813a-4990-8465-7a5553e05f23)</summary>

```json
{
  "source_file": "scenario_combat.dis",
  "scenario_summary": {
    "total_pdus": 50,
    "duration_seconds": 9.5,
    "first_timestamp": 0,
    "last_timestamp": 9500,
    "dis_version": 7,
    "exercise_id": 1
  },
  "entity_count": 2,
  "entity_summary": [
    {
      "entity_id": "42.1.1",
      "state_update_count": 20,
      "first_seen_timestamp": 0,
      "last_seen_timestamp": 9500
    },
    {
      "entity_id": "42.1.2",
      "state_update_count": 20,
      "first_seen_timestamp": 0,
      "last_seen_timestamp": 9500
    }
  ],
  "pdu_type_breakdown": {
    "EntityStatePdu": 40,
    "FirePdu": 5,
    "DetonationPdu": 5
  },
  "fire_events": [
    {
      "timestamp": 2000,
      "firing_entity": "42.1.1",
      "target_entity": "42.1.2"
    }
  ],
  "detonation_events": [
    {
      "timestamp": 2500,
      "firing_entity": "42.1.1",
      "target_entity": "42.1.2"
    }
  ],
  "interactions": {
    "total_fire_events": 5,
    "total_detonation_events": 5,
    "unique_engagements": 1
  }
}
```
</details>

---

### 4. ConvertDISToJSON

Full DIS-to-JSON conversion with optional raw byte inclusion. Similar to ParseDISStream but includes file metadata and optionally hex-encoded raw PDU bytes.

**Input:** `.dis` or `.bin` file + optional `include_raw_bytes` parameter (string `"true"`/`"false"`)
**Output:** `dis_data.json` + `metadata.json`

<details>
<summary>Sample output (from platform job 1b151b13-0575-4b5e-9ae7-233cfbe4e6ac)</summary>

```json
{
  "source_file": "scenario_basic.dis",
  "pdu_count": 35,
  "pdu_type_breakdown": {
    "EntityStatePdu": 30,
    "FirePdu": 3,
    "DetonationPdu": 2
  },
  "dis_version": 7,
  "exercise_id": 1,
  "file_size_bytes": 4816,
  "pdus": ["...35 PDU objects with full field extraction..."]
}
```

Metadata:
```json
{
  "function": "ConvertDISToJSON",
  "source_file": "scenario_basic.dis",
  "pdu_count": 35,
  "include_raw_bytes": false
}
```
</details>

---

### 5. ValidateDISStream

Validate a DIS stream against protocol compliance rules: version consistency, exercise ID validity, timestamp ordering, PDU length integrity, and entity ID uniqueness per force.

**Input:** `.dis` or `.bin` file
**Output:** `validation.json` + `metadata.json`

<details>
<summary>Sample output (from platform job 3dae26aa-3f53-4823-be01-18f5392dae43)</summary>

```json
{
  "source_file": "scenario_basic.dis",
  "is_valid": true,
  "summary": {
    "total_pdus": 35,
    "checks_passed": 5,
    "checks_failed": 0,
    "violations_count": 0
  },
  "checks": [
    {
      "name": "pdu_version",
      "description": "All PDUs use DIS v7 (IEEE 1278.1-2012)",
      "passed": true,
      "details": "35/35 PDUs have version=7"
    },
    {
      "name": "exercise_id_valid",
      "description": "All exercise IDs are > 0",
      "passed": true,
      "details": "All PDUs have exercise_id in [1]"
    },
    {
      "name": "timestamp_ordering",
      "description": "Timestamps are non-decreasing",
      "passed": true,
      "details": "Timestamps monotonically increase from 0 to 9000"
    },
    {
      "name": "pdu_length_integrity",
      "description": "PDU declared length matches actual bytes read",
      "passed": true
    },
    {
      "name": "entity_id_consistency",
      "description": "Entity IDs are unique per force",
      "passed": true
    }
  ],
  "violations": []
}
```
</details>

---

## Platform Verification

Deployed and verified on the Istari platform. All 5 functions reached COMPLETED through the full job lifecycle.

**System:** [https://demo.istari.app/systems/ab9cb5f9-ee0a-4204-b918-a4bb540cb10c](https://demo.istari.app/systems/ab9cb5f9-ee0a-4204-b918-a4bb540cb10c)
**Agent:** `e0fddacb-5ff2-4e47-b5df-9b64228e7f55`

| Function | Status | Job ID | Duration | Artifacts |
|----------|--------|--------|----------|-----------|
| ParseDISStream | COMPLETED | `1de6b878-cb6a-4d32-be0d-f69351023cfc` | 60s | pdus.json (25KB), metadata.json |
| ExtractEntityStates | COMPLETED | `7f3b973b-a91e-4e23-86fa-0072f8f81bc5` | 46s | entities.json (19KB), metadata.json |
| AnalyzeScenario | COMPLETED | `380b9893-813a-4990-8465-7a5553e05f23` | 45s | scenario_analysis.json (2KB), metadata.json |
| ConvertDISToJSON | COMPLETED | `1b151b13-0575-4b5e-9ae7-233cfbe4e6ac` | 45s | dis_data.json (26KB), metadata.json |
| ValidateDISStream | COMPLETED | `3dae26aa-3f53-4823-be01-18f5392dae43` | 45s | validation.json (1KB), metadata.json |

**Status timeline (all functions):**
```
PENDING -> CLAIMED -> VALIDATING -> RUNNING -> UPLOADING -> COMPLETED
```

**Digital thread:** 6 configurations, 13 tracked files, baseline + per-function snapshots, 8 README versions.

### Test Summary

| Layer | Result |
|-------|--------|
| Unit tests (pytest) | 20/20 passed |
| Binary validation (PyInstaller) | 5/5 functions |
| Platform E2E (Istari agent) | 5/5 COMPLETED |

**Test classes:** TestParseDISStream (5), TestExtractEntityStates (4), TestAnalyzeScenario (3), TestConvertDISToJSON (2), TestValidateDISStream (2), TestIstariWrapperFormat (1), TestParameterCoercion (3).

---

## Use Cases

- **Simulation replay analysis** -- Parse recorded DIS exercises to extract entity movements, engagements, and scenario timelines
- **Protocol compliance validation** -- Verify DIS streams meet IEEE 1278.1 standards before federation
- **Entity tracking** -- Extract individual entity trajectories with ECEF-to-geodetic conversion for mapping
- **After-action review** -- Analyze combat scenarios: who fired at whom, when, outcomes
- **Data interchange** -- Convert binary DIS to JSON for downstream analytics, dashboards, or digital thread integration

---

## Build

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install opendis pydantic pyinstaller
pyinstaller --onefile --collect-all opendis --name opendis_module opendis_module/__main__.py
cp dist/opendis_module .
```

## Test

```bash
pip install pytest pytest-cov ruff
PYTHONPATH=. python -m pytest tests/test_core.py -v
```

## Install on Agent

```bash
stari module lint
stari module publish
stari module install opendis-module-1.0.0.zip
# Restart agent to pick up new module
```

---

## Project Structure

```
opendis-module/
  opendis_module/
    __init__.py
    __main__.py            # CLI entrypoint
    module_config.py       # Config loader
    logging_config.py      # Logging setup
    functions/
      registry.py          # Function dispatch
      parse_dis_stream.py  # ParseDISStream
      extract_entity_states.py  # ExtractEntityStates
      analyze_scenario.py  # AnalyzeScenario
      convert_dis_to_json.py    # ConvertDISToJSON
      validate_dis_stream.py    # ValidateDISStream
    services/
      dis_parser.py        # Core PDU decoding (opendis)
      dis_converter.py     # DIS-to-JSON conversion
      dis_validator.py     # Protocol compliance checks
      ecef_convert.py      # ECEF-to-geodetic math
      entity_extractor.py  # Entity timeline extraction
      scenario_analyzer.py # Scenario analysis
  tests/
    conftest.py            # Programmatic DIS fixture generation
    test_core.py           # 20 unit tests
    test_inputs/           # Binary DIS fixtures
    results/
      platform_test_report.json  # Platform E2E evidence
  scripts/macos/
    install.sh / build.sh / test_unit.sh / clean.sh
  module_manifest.json     # Istari manifest
  module_config.json       # Runtime config
  pyproject.toml           # Poetry project
```

---

## Manifest

**Module:** `@istari:opendis-module` v1.0.0
**OS:** macOS 26
**Agent:** >=9.0.0

| Function Key | Input | Optional Params | Output |
|-------------|-------|-----------------|--------|
| `@istari:ParseDISStream` | `.dis`/`.bin` | -- | pdus.json, metadata.json |
| `@istari:ExtractEntityStates` | `.dis`/`.bin` | `entity_id` (int) | entities.json, metadata.json |
| `@istari:AnalyzeScenario` | `.dis`/`.bin` | -- | scenario_analysis.json, metadata.json |
| `@istari:ConvertDISToJSON` | `.dis`/`.bin` | `include_raw_bytes` (bool) | dis_data.json, metadata.json |
| `@istari:ValidateDISStream` | `.dis`/`.bin` | -- | validation.json, metadata.json |

---

## Quality Gates

| Gate | Verdict | Timestamp |
|------|---------|-----------|
| challenge-build | PASS (0 critical, 0 high) | 2026-04-01T12:49:00Z |
| challenge-test | PASS (0 critical, 0 high) | 2026-04-01T09:03:00Z |
| challenge-docs | PASS | 2026-04-01 |
