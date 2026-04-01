"""AnalyzeScenario function — analyze DIS scenario recordings."""

import json
import logging
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opendis_module.functions.base.function_io import Input, Output, OutputType
from opendis_module.functions.registry import register
from opendis_module.services.scenario_analyzer import analyze_scenario

logger = logging.getLogger(__name__)


class AnalyzeScenarioInput(BaseModel):
    """Input schema for AnalyzeScenario."""

    input_model: Input[str] = Field(
        ..., description="Path to DIS binary file (.dis or .bin)"
    )

    model_config = ConfigDict(extra="allow")


def analyze_scenario_fn(input_json: str, temp_dir: str) -> List[Output]:
    """Analyze a DIS recording for scenario statistics.

    Args:
        input_json: JSON string with input_model pointing to .dis/.bin file.
        temp_dir: Directory for output files.

    Returns:
        List of Output items (scenario_analysis_json, metadata).
    """
    logger.info("Starting AnalyzeScenario execution.")

    # 1. Parse input
    try:
        function_input = AnalyzeScenarioInput.model_validate_json(input_json)
    except ValidationError as e:
        raise ValueError(f"Invalid input for AnalyzeScenario: {e}") from e

    outputs: List[Output] = []
    dis_file_path = function_input.input_model.value

    # 2. Analyze scenario
    try:
        result = analyze_scenario(dis_file_path)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"AnalyzeScenario failed: {e}") from e

    # 3. Write output files
    analysis_json_path = Path(temp_dir) / "scenario_analysis.json"
    metadata_path = Path(temp_dir) / "metadata.json"

    analysis_json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info(
        f"Analyzed scenario: {result['entity_count']} entities, "
        f"{result['interactions']['total_fire_events']} fire events"
    )

    metadata = {
        "function": "AnalyzeScenario",
        "source_file": result["source_file"],
        "entity_count": result["entity_count"],
        "total_pdus": result["scenario_summary"]["total_pdus"],
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    outputs.append(
        Output(
            name="scenario_analysis_json",
            type=OutputType.FILE,
            path=str(analysis_json_path),
        )
    )
    outputs.append(
        Output(name="metadata", type=OutputType.FILE, path=str(metadata_path))
    )

    return outputs


register("AnalyzeScenario", analyze_scenario_fn)
