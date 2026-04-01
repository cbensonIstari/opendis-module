"""Full DIS-to-JSON conversion.

Converts all PDUs in a DIS binary file to structured JSON with all fields preserved.
Optionally includes raw bytes as hex strings.
"""

import logging
from pathlib import Path
from typing import Any

from opendis_module.services.dis_parser import (
    parse_dis_file,
    parse_dis_file_with_raw,
)

logger = logging.getLogger(__name__)


def convert_dis_to_json(
    filepath: str,
    include_raw_bytes: bool = False,
) -> dict[str, Any]:
    """Convert a DIS binary file to full JSON representation.

    Args:
        filepath: Path to .dis or .bin file.
        include_raw_bytes: If True, include hex-encoded raw bytes for each PDU.

    Returns:
        Dict with source_file, file_size_bytes, pdu_count, dis_version, and pdus list.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"DIS file not found: {filepath}")

    file_size = path.stat().st_size

    if not include_raw_bytes:
        result = parse_dis_file(filepath)
        result["file_size_bytes"] = file_size
        return result

    # With raw bytes
    parsed = parse_dis_file_with_raw(filepath)

    pdus_out: list[dict[str, Any]] = []
    type_breakdown: dict[str, int] = {}
    dis_version = None

    for fields, raw in parsed:
        fields["raw_bytes"] = raw.hex()
        pdus_out.append(fields)

        type_name = fields["pdu_type_name"]
        type_breakdown[type_name] = type_breakdown.get(type_name, 0) + 1

        if dis_version is None:
            dis_version = fields["protocol_version"]

    return {
        "source_file": path.name,
        "file_size_bytes": file_size,
        "pdu_count": len(pdus_out),
        "pdu_type_breakdown": type_breakdown,
        "dis_version": dis_version,
        "pdus": pdus_out,
    }
