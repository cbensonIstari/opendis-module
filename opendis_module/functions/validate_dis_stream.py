"""ValidateDISStream function — validate DIS stream compliance."""

import json
import logging
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opendis_module.functions.base.function_io import Input, Output, OutputType
from opendis_module.functions.registry import register
from opendis_module.services.dis_validator import validate_dis_stream

logger = logging.getLogger(__name__)


class ValidateDISStreamInput(BaseModel):
    """Input schema for ValidateDISStream."""

    input_model: Input[str] = Field(
        ..., description="Path to DIS binary file (.dis or .bin)"
    )

    model_config = ConfigDict(extra="allow")


def validate_dis_stream_fn(input_json: str, temp_dir: str) -> List[Output]:
    """Validate a DIS binary file for protocol compliance.

    Args:
        input_json: JSON string with input_model pointing to .dis/.bin file.
        temp_dir: Directory for output files.

    Returns:
        List of Output items (validation_json, metadata).
    """
    logger.info("Starting ValidateDISStream execution.")

    # 1. Parse input
    try:
        function_input = ValidateDISStreamInput.model_validate_json(input_json)
    except ValidationError as e:
        raise ValueError(f"Invalid input for ValidateDISStream: {e}") from e

    outputs: List[Output] = []
    dis_file_path = function_input.input_model.value

    # 2. Validate
    try:
        result = validate_dis_stream(dis_file_path)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"ValidateDISStream failed: {e}") from e

    # 3. Write output files
    validation_path = Path(temp_dir) / "validation.json"
    metadata_path = Path(temp_dir) / "metadata.json"

    validation_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info(
        f"Validation complete: is_valid={result['is_valid']}, "
        f"{result['summary']['checks_passed']}/{result['summary']['checks_passed'] + result['summary']['checks_failed']} checks passed"
    )

    metadata = {
        "function": "ValidateDISStream",
        "source_file": result["source_file"],
        "is_valid": result["is_valid"],
        "checks_passed": result["summary"]["checks_passed"],
        "checks_failed": result["summary"]["checks_failed"],
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    outputs.append(
        Output(
            name="validation_json", type=OutputType.FILE, path=str(validation_path)
        )
    )
    outputs.append(
        Output(name="metadata", type=OutputType.FILE, path=str(metadata_path))
    )

    return outputs


register("ValidateDISStream", validate_dis_stream_fn)
