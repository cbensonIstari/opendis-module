"""ParseDISCapture function — parse raw DIS capture files (PCAP or binary streams)."""

import json
import logging
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opendis_module.functions.base.function_io import Input, Output, OutputType
from opendis_module.functions.registry import register
from opendis_module.services.capture_parser import parse_dis_capture

logger = logging.getLogger(__name__)


class ParseDISCaptureInput(BaseModel):
    """Input schema for ParseDISCapture."""

    input_model: Input[str] = Field(
        ..., description="Path to DIS capture file (.pcap, .dis, or .bin)"
    )

    model_config = ConfigDict(extra="allow")


def parse_dis_capture_fn(input_json: str, temp_dir: str) -> List[Output]:
    """Parse a DIS capture file and produce entity timelines + summary statistics.

    Accepts raw binary DIS streams (.dis, .bin) and PCAP capture files (.pcap).
    Extracts all PDUs, groups EntityStatePdu records by entity ID, builds
    per-entity timelines (position, orientation, damage state), and computes
    summary statistics.

    Args:
        input_json: JSON string with input_model pointing to capture file.
        temp_dir: Directory for output files.

    Returns:
        List of Output items (capture_json, metadata).
    """
    logger.info("Starting ParseDISCapture execution.")

    # 1. Parse input
    try:
        function_input = ParseDISCaptureInput.model_validate_json(input_json)
    except ValidationError as e:
        raise ValueError(f"Invalid input for ParseDISCapture: {e}") from e

    outputs: List[Output] = []
    capture_file_path = function_input.input_model.value

    # 2. Parse capture file
    try:
        result = parse_dis_capture(capture_file_path)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"ParseDISCapture failed: {e}") from e

    # 3. Write output files
    capture_json_path = Path(temp_dir) / "capture.json"
    metadata_path = Path(temp_dir) / "metadata.json"

    capture_json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info(
        f"Parsed {result['total_pdus']} PDUs from {result['capture_format']} capture, "
        f"{result['entity_count']} entities to {capture_json_path}"
    )

    metadata = {
        "function": "ParseDISCapture",
        "source_file": result["source_file"],
        "capture_format": result["capture_format"],
        "total_pdus": result["total_pdus"],
        "entity_count": result["entity_count"],
        "pdu_type_breakdown": result["pdu_type_breakdown"],
        "statistics": result["statistics"],
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    outputs.append(
        Output(name="capture_json", type=OutputType.FILE, path=str(capture_json_path))
    )
    outputs.append(
        Output(name="metadata", type=OutputType.FILE, path=str(metadata_path))
    )

    return outputs


register("ParseDISCapture", parse_dis_capture_fn)
