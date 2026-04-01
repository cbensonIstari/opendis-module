"""Extract entity state timelines from DIS binary streams.

Groups EntityStatePdu records by entity ID, converts ECEF positions
to geodetic (lat/lon/alt) via WGS-84, and extracts orientations and velocities.
"""

import logging
import math
from pathlib import Path
from typing import Any

from opendis_module.services.dis_parser import (
    MAX_FILE_SIZE_BYTES,
    WARN_FILE_SIZE_BYTES,
    _format_entity_id,
    _format_entity_id_string,
    parse_dis_binary,
)
from opendis_module.services.ecef_convert import ecef_to_geodetic

logger = logging.getLogger(__name__)


def extract_entity_states(
    filepath: str,
    entity_id_filter: int | None = None,
) -> dict[str, Any]:
    """Extract entity state timelines from a DIS binary file.

    Args:
        filepath: Path to .dis or .bin file.
        entity_id_filter: If provided, only extract states for this entity ID.
            Matches against the entityID field (not site or application).

    Returns:
        Dict with source_file, entity_count, and entities list.
        Each entity has entity_id, entity_id_string, state_count, and track.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"DIS file not found: {filepath}")

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"DIS file too large ({file_size / 1e9:.2f} GB).")
    if file_size == 0:
        return {
            "source_file": path.name,
            "entity_count": 0,
            "entities": [],
        }

    if file_size > WARN_FILE_SIZE_BYTES:
        logger.warning(f"Large DIS file ({file_size / 1e6:.1f} MB).")

    data = path.read_bytes()
    parsed = parse_dis_binary(data)

    # Group entity states by entity ID string
    entities_map: dict[str, dict[str, Any]] = {}

    for pdu, _raw in parsed:
        pdu_type = int(pdu.pduType)
        if pdu_type != 1:  # Only EntityStatePdu
            continue

        eid = pdu.entityID
        eid_num = int(eid.entityID)

        # Apply entity_id filter if specified
        if entity_id_filter is not None and eid_num != entity_id_filter:
            continue

        eid_string = _format_entity_id_string(eid)

        if eid_string not in entities_map:
            entities_map[eid_string] = {
                "entity_id": _format_entity_id(eid),
                "entity_id_string": eid_string,
                "track": [],
            }

        # ECEF to geodetic conversion
        x = float(pdu.entityLocation.x)
        y = float(pdu.entityLocation.y)
        z = float(pdu.entityLocation.z)
        lat, lon, alt = ecef_to_geodetic(x, y, z)

        vx = float(pdu.entityLinearVelocity.x)
        vy = float(pdu.entityLinearVelocity.y)
        vz = float(pdu.entityLinearVelocity.z)
        speed = math.sqrt(vx**2 + vy**2 + vz**2)

        track_point = {
            "timestamp": int(pdu.timestamp),
            "position_ecef": {"x": x, "y": y, "z": z},
            "position_geodetic": {
                "latitude_deg": round(lat, 6),
                "longitude_deg": round(lon, 6),
                "altitude_m": round(alt, 3),
            },
            "orientation_rad": {
                "psi": float(pdu.entityOrientation.psi),
                "theta": float(pdu.entityOrientation.theta),
                "phi": float(pdu.entityOrientation.phi),
            },
            "velocity_mps": {
                "x": vx,
                "y": vy,
                "z": vz,
                "speed": round(speed, 3),
            },
        }

        entities_map[eid_string]["track"].append(track_point)

    # Build output
    entities_list = []
    for eid_string, entity_data in entities_map.items():
        entity_data["state_count"] = len(entity_data["track"])
        entities_list.append(entity_data)

    return {
        "source_file": path.name,
        "entity_count": len(entities_list),
        "entities": entities_list,
    }
