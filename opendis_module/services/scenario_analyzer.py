"""Analyze DIS scenario recordings.

Extracts entity counts, fire/detonation events, interaction timeline,
scenario duration, and PDU type breakdown from a DIS binary file.
"""

import logging
from pathlib import Path
from typing import Any

from opendis_module.services.dis_parser import (
    MAX_FILE_SIZE_BYTES,
    PDU_TYPE_NAMES,
    WARN_FILE_SIZE_BYTES,
    _format_entity_id_string,
    parse_dis_binary,
)

logger = logging.getLogger(__name__)


def analyze_scenario(filepath: str) -> dict[str, Any]:
    """Analyze a DIS recording for scenario statistics.

    Args:
        filepath: Path to .dis or .bin file.

    Returns:
        Dict with scenario_summary, entity_summary, entity_count,
        pdu_type_breakdown, fire_events, detonation_events, interactions.
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
            "scenario_summary": {
                "total_pdus": 0,
                "duration_seconds": 0.0,
                "first_timestamp": None,
                "last_timestamp": None,
                "dis_version": None,
                "exercise_id": None,
            },
            "entity_summary": [],
            "entity_count": 0,
            "pdu_type_breakdown": {},
            "fire_events": [],
            "detonation_events": [],
            "interactions": {
                "total_fire_events": 0,
                "total_detonation_events": 0,
                "unique_engagements": 0,
            },
        }

    if file_size > WARN_FILE_SIZE_BYTES:
        logger.warning(f"Large DIS file ({file_size / 1e6:.1f} MB).")

    data = path.read_bytes()
    parsed = parse_dis_binary(data)

    type_breakdown: dict[str, int] = {}
    entity_states: dict[str, list[int]] = {}  # eid_string -> [timestamps]
    fire_events: list[dict[str, Any]] = []
    detonation_events: list[dict[str, Any]] = []
    all_timestamps: list[int] = []
    dis_version = None
    exercise_id = None
    engagements: set[tuple[str, str]] = set()

    for pdu, _raw in parsed:
        pdu_type = int(pdu.pduType)
        type_name = PDU_TYPE_NAMES.get(pdu_type, f"Unknown({pdu_type})")
        type_breakdown[type_name] = type_breakdown.get(type_name, 0) + 1
        timestamp = int(pdu.timestamp)
        all_timestamps.append(timestamp)

        if dis_version is None:
            dis_version = int(pdu.protocolVersion)
        if exercise_id is None:
            exercise_id = int(pdu.exerciseID)

        # EntityStatePdu (type 1)
        if pdu_type == 1:
            eid_string = _format_entity_id_string(pdu.entityID)
            if eid_string not in entity_states:
                entity_states[eid_string] = []
            entity_states[eid_string].append(timestamp)

        # FirePdu (type 2)
        elif pdu_type == 2:
            firing = _format_entity_id_string(pdu.firingEntityID)
            target = _format_entity_id_string(pdu.targetEntityID)
            fire_events.append({
                "timestamp": timestamp,
                "firing_entity": firing,
                "target_entity": target,
            })
            engagements.add((firing, target))

        # DetonationPdu (type 3)
        elif pdu_type == 3:
            firing = _format_entity_id_string(pdu.firingEntityID)
            target = _format_entity_id_string(pdu.targetEntityID)
            det_data: dict[str, Any] = {
                "timestamp": timestamp,
                "firing_entity": firing,
                "target_entity": target,
            }
            try:
                det_data["location_ecef"] = {
                    "x": float(pdu.location.x),
                    "y": float(pdu.location.y),
                    "z": float(pdu.location.z),
                }
            except (AttributeError, TypeError):
                pass
            detonation_events.append(det_data)
            engagements.add((firing, target))

    # Build entity summary
    entity_summary = []
    for eid_string, timestamps in entity_states.items():
        entity_summary.append({
            "entity_id": eid_string,
            "state_update_count": len(timestamps),
            "first_seen_timestamp": min(timestamps),
            "last_seen_timestamp": max(timestamps),
        })

    # Compute duration
    first_ts = min(all_timestamps) if all_timestamps else None
    last_ts = max(all_timestamps) if all_timestamps else None
    if first_ts is not None and last_ts is not None:
        duration_seconds = (last_ts - first_ts) / 1000.0
    else:
        duration_seconds = 0.0

    return {
        "source_file": path.name,
        "scenario_summary": {
            "total_pdus": len(parsed),
            "duration_seconds": round(duration_seconds, 3),
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
            "dis_version": dis_version,
            "exercise_id": exercise_id,
        },
        "entity_summary": entity_summary,
        "entity_count": len(entity_states),
        "pdu_type_breakdown": type_breakdown,
        "fire_events": fire_events,
        "detonation_events": detonation_events,
        "interactions": {
            "total_fire_events": len(fire_events),
            "total_detonation_events": len(detonation_events),
            "unique_engagements": len(engagements),
        },
    }
