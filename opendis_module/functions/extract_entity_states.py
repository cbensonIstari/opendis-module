"""ExtractEntityStates function — extract entity state timelines with ECEF-to-geodetic."""

import json
import logging
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opendis_module.functions.base.function_io import Input, Output, OutputType
from opendis_module.functions.registry import register
from opendis_module.services.entity_extractor import extract_entity_states

logger = logging.getLogger(__name__)


class ExtractEntityStatesInput(BaseModel):
    """Input schema for ExtractEntityStates."""

    input_model: Input[str] = Field(
        ..., description="Path to DIS binary file (.dis or .bin)"
    )
    entity_id: Input[str] | None = Field(
        default=None, description="Optional entity ID filter"
    )

    model_config = ConfigDict(extra="allow")


def extract_entity_states_fn(input_json: str, temp_dir: str) -> List[Output]:
    """Extract entity state timelines from a DIS binary file.

    Args:
        input_json: JSON string with input_model and optional entity_id.
        temp_dir: Directory for output files.

    Returns:
        List of Output items (entities_json, metadata).
    """
    logger.info("Starting ExtractEntityStates execution.")

    # 1. Parse input
    try:
        function_input = ExtractEntityStatesInput.model_validate_json(input_json)
    except ValidationError as e:
        raise ValueError(f"Invalid input for ExtractEntityStates: {e}") from e

    outputs: List[Output] = []
    dis_file_path = function_input.input_model.value

    # 2. Parse entity_id parameter — string to int coercion (design challenge finding #1)
    entity_id_filter: int | None = None
    if function_input.entity_id is not None:
        raw_val = function_input.entity_id.value
        try:
            entity_id_filter = int(raw_val)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"entity_id must be an integer, got: {raw_val!r}"
            ) from e

    # 3. Extract entity states
    try:
        result = extract_entity_states(dis_file_path, entity_id_filter)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"ExtractEntityStates failed: {e}") from e

    # 4. Write output files
    entities_json_path = Path(temp_dir) / "entities.json"
    metadata_path = Path(temp_dir) / "metadata.json"

    entities_json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info(
        f"Extracted {result['entity_count']} entities to {entities_json_path}"
    )

    metadata = {
        "function": "ExtractEntityStates",
        "source_file": result["source_file"],
        "entity_count": result["entity_count"],
        "entity_id_filter": entity_id_filter,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    outputs.append(
        Output(name="entities_json", type=OutputType.FILE, path=str(entities_json_path))
    )
    outputs.append(
        Output(name="metadata", type=OutputType.FILE, path=str(metadata_path))
    )

    return outputs


register("ExtractEntityStates", extract_entity_states_fn)
