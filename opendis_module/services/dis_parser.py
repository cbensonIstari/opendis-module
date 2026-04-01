"""Parse binary DIS PDU streams using opendis.

Reads a binary file containing concatenated DIS PDUs (no delimiter),
parses each PDU using opendis.PduFactory.createPdu(), and returns
structured data for all PDUs.
"""

import logging
import struct
from pathlib import Path
from typing import Any

from opendis.PduFactory import createPdu

logger = logging.getLogger(__name__)

# PDU type name mapping (IEEE 1278.1)
PDU_TYPE_NAMES: dict[int, str] = {
    1: "EntityStatePdu",
    2: "FirePdu",
    3: "DetonationPdu",
    4: "CollisionPdu",
    5: "ServiceRequestPdu",
    6: "ResupplyOfferPdu",
    7: "ResupplyReceivedPdu",
    8: "ResupplyCancelPdu",
    9: "RepairCompletePdu",
    10: "RepairResponsePdu",
    11: "CreateEntityPdu",
    12: "RemoveEntityPdu",
    13: "StartResumePdu",
    14: "StopFreezePdu",
    15: "AcknowledgePdu",
    16: "ActionRequestPdu",
    17: "ActionResponsePdu",
    20: "DataPdu",
    22: "CommentPdu",
    25: "TransmitterPdu",
    26: "SignalPdu",
    27: "ReceiverPdu",
}

# File size limits (from design challenge findings)
MAX_FILE_SIZE_BYTES = 1_073_741_824  # 1 GB — reject
WARN_FILE_SIZE_BYTES = 104_857_600  # 100 MB — warn


def _format_entity_id(eid: Any) -> dict[str, int]:
    """Extract entity ID triple from an opendis EntityID object."""
    return {
        "site": int(eid.siteID),
        "application": int(eid.applicationID),
        "entity": int(eid.entityID),
    }


def _format_entity_id_string(eid: Any) -> str:
    """Format entity ID as 'site.app.entity' string."""
    return f"{eid.siteID}.{eid.applicationID}.{eid.entityID}"


def _extract_pdu_fields(pdu: Any, index: int) -> dict[str, Any]:
    """Extract common and type-specific fields from a parsed PDU."""
    pdu_type = int(pdu.pduType)
    result: dict[str, Any] = {
        "index": index,
        "pdu_type": pdu_type,
        "pdu_type_name": PDU_TYPE_NAMES.get(pdu_type, f"Unknown({pdu_type})"),
        "protocol_version": int(pdu.protocolVersion),
        "exercise_id": int(pdu.exerciseID),
        "timestamp": int(pdu.timestamp),
        "length": int(pdu.length),
    }

    # EntityStatePdu (type 1)
    if pdu_type == 1:
        result["entity_id"] = _format_entity_id(pdu.entityID)
        result["force_id"] = int(pdu.forceId)
        result["entity_type"] = {
            "kind": int(pdu.entityType.entityKind),
            "domain": int(pdu.entityType.domain),
            "country": int(pdu.entityType.country),
            "category": int(pdu.entityType.category),
            "subcategory": int(pdu.entityType.subcategory),
        }
        result["entity_location"] = {
            "x": float(pdu.entityLocation.x),
            "y": float(pdu.entityLocation.y),
            "z": float(pdu.entityLocation.z),
        }
        result["entity_orientation"] = {
            "psi": float(pdu.entityOrientation.psi),
            "theta": float(pdu.entityOrientation.theta),
            "phi": float(pdu.entityOrientation.phi),
        }
        result["entity_linear_velocity"] = {
            "x": float(pdu.entityLinearVelocity.x),
            "y": float(pdu.entityLinearVelocity.y),
            "z": float(pdu.entityLinearVelocity.z),
        }

    # FirePdu (type 2)
    elif pdu_type == 2:
        result["firing_entity_id"] = _format_entity_id(pdu.firingEntityID)
        result["target_entity_id"] = _format_entity_id(pdu.targetEntityID)

    # DetonationPdu (type 3)
    elif pdu_type == 3:
        result["firing_entity_id"] = _format_entity_id(pdu.firingEntityID)
        result["target_entity_id"] = _format_entity_id(pdu.targetEntityID)
        result["location_ecef"] = {
            "x": float(pdu.location.x),
            "y": float(pdu.location.y),
            "z": float(pdu.location.z),
        }

    return result


def parse_dis_binary(data: bytes) -> list[tuple[Any, bytes]]:
    """Parse raw binary data into a list of (pdu_object, raw_bytes) tuples.

    PDUs are concatenated with no delimiter. Each PDU header contains:
    - byte 0: protocolVersion
    - byte 1: exerciseID
    - byte 2: pduType
    - byte 3: protocolFamily
    - bytes 4-7: timestamp (uint32)
    - bytes 8-9: length (uint16, big-endian)
    - bytes 10-11: padding

    Args:
        data: Raw binary DIS data.

    Returns:
        List of (parsed_pdu, raw_pdu_bytes) tuples.
    """
    pdus: list[tuple[Any, bytes]] = []
    offset = 0

    while offset < len(data):
        # Need at least 12 bytes for header
        if offset + 12 > len(data):
            logger.warning(
                f"Incomplete PDU header at offset {offset} "
                f"({len(data) - offset} bytes remaining). Stopping."
            )
            break

        # Read PDU length from header bytes 8-9 (big-endian uint16)
        pdu_length = struct.unpack_from(">H", data, offset + 8)[0]

        if pdu_length == 0:
            logger.warning(f"Zero-length PDU at offset {offset}. Stopping.")
            break

        if offset + pdu_length > len(data):
            logger.warning(
                f"Truncated PDU at offset {offset}: "
                f"header says {pdu_length} bytes but only "
                f"{len(data) - offset} available. Stopping."
            )
            break

        pdu_bytes = data[offset : offset + pdu_length]

        try:
            pdu = createPdu(pdu_bytes)
        except Exception as e:
            logger.warning(f"Failed to parse PDU at offset {offset}: {e}")
            pdu = None

        if pdu is not None:
            pdus.append((pdu, pdu_bytes))
        else:
            logger.warning(
                f"createPdu returned None at offset {offset} "
                f"(pduType={data[offset + 2] if offset + 3 <= len(data) else '?'}). Skipping."
            )

        offset += pdu_length

    return pdus


def parse_dis_file(filepath: str) -> dict[str, Any]:
    """Parse a DIS binary file and return structured JSON data.

    Args:
        filepath: Path to .dis or .bin file.

    Returns:
        Dict with source_file, pdu_count, pdu_type_breakdown, dis_version,
        exercise_id, and pdus list.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file exceeds size limits.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"DIS file not found: {filepath}")

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"DIS file too large ({file_size / 1e9:.2f} GB). "
            f"Maximum supported size is 1 GB."
        )
    if file_size > WARN_FILE_SIZE_BYTES:
        logger.warning(
            f"Large DIS file ({file_size / 1e6:.1f} MB). Processing may be slow."
        )

    if file_size == 0:
        return {
            "source_file": path.name,
            "pdu_count": 0,
            "pdu_type_breakdown": {},
            "dis_version": None,
            "exercise_id": None,
            "pdus": [],
        }

    data = path.read_bytes()
    parsed = parse_dis_binary(data)

    pdus_out: list[dict[str, Any]] = []
    type_breakdown: dict[str, int] = {}
    dis_version = None
    exercise_id = None

    for i, (pdu, _raw) in enumerate(parsed):
        fields = _extract_pdu_fields(pdu, i)
        pdus_out.append(fields)

        type_name = fields["pdu_type_name"]
        type_breakdown[type_name] = type_breakdown.get(type_name, 0) + 1

        if dis_version is None:
            dis_version = fields["protocol_version"]
        if exercise_id is None:
            exercise_id = fields["exercise_id"]

    return {
        "source_file": path.name,
        "pdu_count": len(pdus_out),
        "pdu_type_breakdown": type_breakdown,
        "dis_version": dis_version,
        "exercise_id": exercise_id,
        "pdus": pdus_out,
    }


def parse_dis_file_with_raw(filepath: str) -> list[tuple[dict[str, Any], bytes]]:
    """Parse a DIS file and return fields + raw bytes for each PDU.

    Used by ConvertDISToJSON when include_raw_bytes is True.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"DIS file not found: {filepath}")

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"DIS file too large ({file_size / 1e9:.2f} GB).")
    if file_size == 0:
        return []

    data = path.read_bytes()
    parsed = parse_dis_binary(data)

    result: list[tuple[dict[str, Any], bytes]] = []
    for i, (pdu, raw) in enumerate(parsed):
        fields = _extract_pdu_fields(pdu, i)
        result.append((fields, raw))

    return result
