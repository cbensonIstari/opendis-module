"""ParseDISStream function — parse binary DIS PDU streams."""

import json
import logging
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opendis_module.functions.base.function_io import Input, Output, OutputType
from opendis_module.functions.registry import register
from opendis_module.services.dis_parser import parse_dis_file

logger = logging.getLogger(__name__)


class ParseDISStreamInput(BaseModel):
    """Input schema for ParseDISStream."""

    input_model: Input[str] = Field(
        ..., description="Path to DIS binary file (.dis or .bin)"
    )

    model_config = ConfigDict(extra="allow")


def parse_dis_stream(input_json: str, temp_dir: str) -> List[Output]:
    """Parse a binary DIS file and extract all PDUs as structured JSON.

    Args:
        input_json: JSON string with input_model pointing to .dis/.bin file.
        temp_dir: Directory for output files.

    Returns:
        List of Output items (pdus_json, metadata).
    """
    logger.info("Starting ParseDISStream execution.")

    # 1. Parse input
    try:
        function_input = ParseDISStreamInput.model_validate_json(input_json)
    except ValidationError as e:
        raise ValueError(f"Invalid input for ParseDISStream: {e}") from e

    outputs: List[Output] = []
    dis_file_path = function_input.input_model.value

    # 2. Parse DIS file
    try:
        result = parse_dis_file(dis_file_path)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"ParseDISStream failed: {e}") from e

    # 3. Write output files
    pdus_json_path = Path(temp_dir) / "pdus.json"
    metadata_path = Path(temp_dir) / "metadata.json"

    pdus_json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info(f"Wrote {result['pdu_count']} PDUs to {pdus_json_path}")

    metadata = {
        "function": "ParseDISStream",
        "source_file": result["source_file"],
        "pdu_count": result["pdu_count"],
        "dis_version": result["dis_version"],
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    outputs.append(Output(name="pdus_json", type=OutputType.FILE, path=str(pdus_json_path)))
    outputs.append(Output(name="metadata", type=OutputType.FILE, path=str(metadata_path)))

    return outputs


register("ParseDISStream", parse_dis_stream)
