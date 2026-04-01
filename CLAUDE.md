# opendis-module

Istari integration module for IEEE 1278.1 DIS (Distributed Interactive Simulation) protocol parsing.

## What This Is

A PyInstaller-packaged Python module that the Istari agent runs as a CLI binary. It parses binary DIS PDU streams into structured JSON. Five functions: ParseDISStream, ExtractEntityStates, AnalyzeScenario, ConvertDISToJSON, ValidateDISStream.

## Build

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install opendis pydantic pyinstaller
pyinstaller --onefile --collect-all opendis --name opendis_module opendis_module/__main__.py
cp dist/opendis_module .
```

## Test

```bash
PYTHONPATH=. python -m pytest tests/test_core.py -v
```

## Key Files

- `opendis_module/__main__.py` — CLI entrypoint, argument parsing, function dispatch
- `opendis_module/functions/registry.py` — function registration and lookup
- `opendis_module/services/dis_parser.py` — core PDU decoding via opendis library
- `opendis_module/services/ecef_convert.py` — ECEF-to-geodetic coordinate conversion
- `opendis_module/services/dis_validator.py` — protocol compliance checks (5 rules)
- `module_manifest.json` — Istari manifest with 5 function keys
- `tests/conftest.py` — programmatic binary DIS fixture generation
- `tests/results/platform_test_report.json` — platform E2E evidence (5/5 COMPLETED)

## Architecture

Each function is registered via `@register("FunctionName")` decorator in `functions/`. Functions call services in `services/` for core logic. The CLI dispatches by function name string.

Services:
- `dis_parser.py` — decodes raw bytes into PDU objects using opendis library. 1GB file size limit, 100MB warning threshold.
- `ecef_convert.py` — converts ECEF coordinates to geodetic (lat/lon/alt) using WGS-84 ellipsoid math.
- `dis_validator.py` — 5 compliance checks: version, exercise ID, timestamp ordering, PDU length, entity ID uniqueness.
- `entity_extractor.py` — groups EntityStatePdu by entity ID, builds position timelines.
- `scenario_analyzer.py` — counts entities, fire/detonation events, engagement relationships.

## Conventions

- All function outputs are JSON wrapped in Istari output format (`[{"name": "...", "type": "file", "path": "..."}]`)
- Parameters arrive as strings from the platform — use int()/bool() coercion with error handling
- Test fixtures are generated programmatically in conftest.py using opendis library (not hand-crafted hex)
- DIS coordinates are ECEF (Earth-Centered Earth-Fixed) — always provide geodetic conversion for human readability

## Platform

- System: https://demo.istari.app/systems/ab9cb5f9-ee0a-4204-b918-a4bb540cb10c
- Agent: e0fddacb-5ff2-4e47-b5df-9b64228e7f55
- All 5 functions verified COMPLETED on platform
