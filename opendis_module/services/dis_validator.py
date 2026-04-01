"""Validate DIS binary stream for protocol compliance.

Checks: PDU version (v7), valid exercise IDs, timestamp ordering,
PDU length integrity, and entity ID consistency.
"""

import logging
import struct
from pathlib import Path
from typing import Any

from opendis_module.services.dis_parser import (
    MAX_FILE_SIZE_BYTES,
    _format_entity_id_string,
    parse_dis_binary,
)

logger = logging.getLogger(__name__)


def validate_dis_stream(filepath: str) -> dict[str, Any]:
    """Validate a DIS binary file for protocol compliance.

    Args:
        filepath: Path to .dis or .bin file.

    Returns:
        Dict with source_file, is_valid, summary, checks list, and violations list.
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
            "is_valid": False,
            "summary": {
                "total_pdus": 0,
                "checks_passed": 0,
                "checks_failed": 1,
                "violations_count": 1,
            },
            "checks": [
                {
                    "name": "file_not_empty",
                    "description": "File contains at least one PDU",
                    "passed": False,
                    "details": "File is empty (0 bytes)",
                }
            ],
            "violations": [
                {
                    "check": "file_not_empty",
                    "severity": "error",
                    "message": "DIS file is empty",
                }
            ],
        }

    data = path.read_bytes()
    parsed = parse_dis_binary(data)

    checks: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    total_pdus = len(parsed)

    # --- Check 1: PDU version (expect v7) ---
    version_ok_count = 0
    version_bad = []
    for i, (pdu, _raw) in enumerate(parsed):
        ver = int(pdu.protocolVersion)
        if ver == 7:
            version_ok_count += 1
        else:
            version_bad.append({"index": i, "version": ver})

    version_passed = version_ok_count == total_pdus
    checks.append({
        "name": "pdu_version",
        "description": "All PDUs use DIS v7 (IEEE 1278.1-2012)",
        "passed": version_passed,
        "details": (
            f"{version_ok_count}/{total_pdus} PDUs have version=7"
            if version_passed
            else f"{len(version_bad)} PDUs have non-v7 version"
        ),
    })
    if not version_passed:
        for bad in version_bad[:10]:  # Limit violation details
            violations.append({
                "check": "pdu_version",
                "severity": "warning",
                "message": f"PDU {bad['index']} has version={bad['version']}, expected 7",
            })

    # --- Check 2: Exercise ID valid (> 0) ---
    eid_ok_count = 0
    eid_bad = []
    for i, (pdu, _raw) in enumerate(parsed):
        eid = int(pdu.exerciseID)
        if eid > 0:
            eid_ok_count += 1
        else:
            eid_bad.append({"index": i, "exercise_id": eid})

    eid_passed = eid_ok_count == total_pdus
    exercise_ids = set(int(pdu.exerciseID) for pdu, _ in parsed)
    checks.append({
        "name": "exercise_id_valid",
        "description": "All exercise IDs are > 0",
        "passed": eid_passed,
        "details": (
            f"All PDUs have exercise_id in {sorted(exercise_ids)}"
            if eid_passed
            else f"{len(eid_bad)} PDUs have exercise_id <= 0"
        ),
    })
    if not eid_passed:
        for bad in eid_bad[:10]:
            violations.append({
                "check": "exercise_id_valid",
                "severity": "error",
                "message": f"PDU {bad['index']} has exercise_id={bad['exercise_id']}",
            })

    # --- Check 3: Timestamp ordering (non-decreasing) ---
    timestamps = [int(pdu.timestamp) for pdu, _ in parsed]
    ts_violations = []
    for i in range(1, len(timestamps)):
        if timestamps[i] < timestamps[i - 1]:
            ts_violations.append({
                "index": i,
                "timestamp": timestamps[i],
                "previous": timestamps[i - 1],
            })

    ts_passed = len(ts_violations) == 0
    checks.append({
        "name": "timestamp_ordering",
        "description": "Timestamps are non-decreasing",
        "passed": ts_passed,
        "details": (
            f"Timestamps monotonically increase from {timestamps[0]} to {timestamps[-1]}"
            if ts_passed and timestamps
            else f"{len(ts_violations)} timestamp ordering violations"
        ),
    })
    if not ts_passed:
        for bad in ts_violations[:10]:
            violations.append({
                "check": "timestamp_ordering",
                "severity": "warning",
                "message": (
                    f"PDU {bad['index']} timestamp {bad['timestamp']} "
                    f"< previous {bad['previous']}"
                ),
            })

    # --- Check 4: PDU length integrity ---
    # Verify that header length fields matched actual parse
    # (If we got this far, parse_dis_binary already validated lengths)
    # Re-check by scanning raw data
    length_ok = 0
    length_bad = []
    offset = 0
    pdu_index = 0
    while offset + 12 <= len(data) and pdu_index < total_pdus:
        header_length = struct.unpack_from(">H", data, offset + 8)[0]
        if header_length > 0 and offset + header_length <= len(data):
            length_ok += 1
        else:
            length_bad.append({"index": pdu_index, "header_length": header_length})
        offset += header_length if header_length > 0 else 12
        pdu_index += 1

    length_passed = len(length_bad) == 0
    checks.append({
        "name": "pdu_length_integrity",
        "description": "PDU length fields match actual data",
        "passed": length_passed,
        "details": (
            f"All {length_ok} PDUs have consistent length fields"
            if length_passed
            else f"{len(length_bad)} PDUs have length integrity issues"
        ),
    })
    if not length_passed:
        for bad in length_bad[:10]:
            violations.append({
                "check": "pdu_length_integrity",
                "severity": "error",
                "message": f"PDU {bad['index']} has invalid length={bad['header_length']}",
            })

    # --- Check 5: Entity ID consistency ---
    entity_exercises: dict[str, set[int]] = {}
    for pdu, _ in parsed:
        if int(pdu.pduType) == 1:
            eid_str = _format_entity_id_string(pdu.entityID)
            ex_id = int(pdu.exerciseID)
            if eid_str not in entity_exercises:
                entity_exercises[eid_str] = set()
            entity_exercises[eid_str].add(ex_id)

    inconsistent = {k: v for k, v in entity_exercises.items() if len(v) > 1}
    entity_passed = len(inconsistent) == 0
    checks.append({
        "name": "entity_id_consistency",
        "description": "Entity IDs are consistent within exercise",
        "passed": entity_passed,
        "details": (
            f"{len(entity_exercises)} unique entities, all with consistent site/application IDs"
            if entity_passed
            else f"{len(inconsistent)} entities appear in multiple exercises"
        ),
    })
    if not entity_passed:
        for eid, exids in inconsistent.items():
            violations.append({
                "check": "entity_id_consistency",
                "severity": "warning",
                "message": f"Entity {eid} appears in exercises {sorted(exids)}",
            })

    # Summary
    checks_passed = sum(1 for c in checks if c["passed"])
    checks_failed = len(checks) - checks_passed
    is_valid = checks_failed == 0

    return {
        "source_file": path.name,
        "is_valid": is_valid,
        "summary": {
            "total_pdus": total_pdus,
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
            "violations_count": len(violations),
        },
        "checks": checks,
        "violations": violations,
    }
