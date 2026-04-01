"""ConvertDISToJSON function — full DIS-to-JSON conversion."""

import json
import logging
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opendis_module.functions.base.function_io import Input, Output, OutputType
from opendis_module.functions.registry import register
from opendis_module.services.dis_converter import convert_dis_to_json

logger = logging.getLogger(__name__)


class ConvertDISToJSONInput(BaseModel):
    """Input schema for ConvertDISToJSON."""

    input_model: Input[str] = Field(
        ..., description="Path to DIS binary file (.dis or .bin)"
    )
    include_raw_bytes: Input[str] | None = Field(
        default=None,
        description="If 'true', include hex-encoded raw bytes for each PDU",
    )

    model_config = ConfigDict(extra="allow")


def _parse_bool_param(raw: str | None) -> bool:
    """Parse a string boolean parameter — design challenge finding #2.

    Parameters arrive as strings from the platform. Explicit parsing of
    'true'/'false' to bool.
    """
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    lower = str(raw).strip().lower()
    if lower in ("true", "1", "yes"):
        return True
    if lower in ("false", "0", "no", ""):
        return False
    raise ValueError(f"Cannot parse '{raw}' as boolean. Expected 'true' or 'false'.")


def convert_dis_to_json_fn(input_json: str, temp_dir: str) -> List[Output]:
    """Convert a DIS binary file to full JSON with all fields preserved.

    Args:
        input_json: JSON string with input_model and optional include_raw_bytes.
        temp_dir: Directory for output files.

    Returns:
        List of Output items (dis_data_json, metadata).
    """
    logger.info("Starting ConvertDISToJSON execution.")

    # 1. Parse input
    try:
        function_input = ConvertDISToJSONInput.model_validate_json(input_json)
    except ValidationError as e:
        raise ValueError(f"Invalid input for ConvertDISToJSON: {e}") from e

    outputs: List[Output] = []
    dis_file_path = function_input.input_model.value

    # 2. Parse include_raw_bytes — string to bool coercion (design challenge finding #2)
    raw_val = (
        function_input.include_raw_bytes.value
        if function_input.include_raw_bytes is not None
        else None
    )
    include_raw = _parse_bool_param(raw_val)

    # 3. Convert
    try:
        result = convert_dis_to_json(dis_file_path, include_raw)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"ConvertDISToJSON failed: {e}") from e

    # 4. Write output files
    dis_data_path = Path(temp_dir) / "dis_data.json"
    metadata_path = Path(temp_dir) / "metadata.json"

    dis_data_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info(f"Converted {result['pdu_count']} PDUs to JSON at {dis_data_path}")

    metadata = {
        "function": "ConvertDISToJSON",
        "source_file": result["source_file"],
        "pdu_count": result["pdu_count"],
        "include_raw_bytes": include_raw,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    outputs.append(
        Output(name="dis_data_json", type=OutputType.FILE, path=str(dis_data_path))
    )
    outputs.append(
        Output(name="metadata", type=OutputType.FILE, path=str(metadata_path))
    )

    return outputs


register("ConvertDISToJSON", convert_dis_to_json_fn)
