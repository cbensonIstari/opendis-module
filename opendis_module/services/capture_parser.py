"""Parse DIS capture files — raw binary (.dis/.bin) and PCAP (.pcap) formats.

Extracts all DIS PDUs from capture files, groups EntityStatePdu records by
entity ID, builds per-entity timelines (position, orientation, damage state),
and computes summary statistics.

PCAP parsing is lightweight (no dpkt/scapy dependency) — reads the global
header to detect endianness, iterates packet records, strips Ethernet +
IP + UDP headers to reach the DIS payload.
"""

import logging
import math
import struct
from pathlib import Path
from typing import Any

from opendis_module.services.dis_parser import (
    MAX_FILE_SIZE_BYTES,
    WARN_FILE_SIZE_BYTES,
    _extract_pdu_fields,
    _format_entity_id,
    _format_entity_id_string,
    parse_dis_binary,
)
from opendis_module.services.ecef_convert import ecef_to_geodetic

logger = logging.getLogger(__name__)

# PCAP magic numbers
PCAP_MAGIC_LE = 0xA1B2C3D4
PCAP_MAGIC_BE = 0xD4C3B2A1
PCAP_MAGIC_NS_LE = 0xA1B23C4D  # Nanosecond-resolution variant
PCAP_MAGIC_NS_BE = 0x4D3CB2A1

# Ethernet + IP + UDP header sizes (standard, no options)
ETH_HEADER_LEN = 14
IP_HEADER_MIN_LEN = 20
UDP_HEADER_LEN = 8

# DIS default port
DIS_DEFAULT_PORT = 3000


def _detect_pcap(data: bytes) -> bool:
    """Check if data starts with a PCAP magic number."""
    if len(data) < 4:
        return False
    magic = struct.unpack_from("<I", data, 0)[0]
    return magic in (PCAP_MAGIC_LE, PCAP_MAGIC_BE, PCAP_MAGIC_NS_LE, PCAP_MAGIC_NS_BE)


def _parse_pcap_packets(data: bytes) -> list[bytes]:
    """Extract raw DIS payloads from a PCAP file.

    Supports standard libpcap format (both endiannesses).
    Strips Ethernet/IP/UDP headers to get to the DIS payload.
    Only extracts UDP packets (IP protocol 17).

    Returns:
        List of raw DIS payload byte strings (one per packet).
    """
    if len(data) < 24:
        raise ValueError("PCAP file too short for global header (need 24 bytes).")

    magic = struct.unpack_from("<I", data, 0)[0]

    if magic in (PCAP_MAGIC_LE, PCAP_MAGIC_NS_LE):
        endian = "<"
    elif magic in (PCAP_MAGIC_BE, PCAP_MAGIC_NS_BE):
        endian = ">"
    else:
        raise ValueError(f"Not a valid PCAP file (magic: 0x{magic:08X}).")

    # Global header: magic(4) + version_major(2) + version_minor(2) +
    #   thiszone(4) + sigfigs(4) + snaplen(4) + network(4) = 24 bytes
    # network field: 1 = Ethernet
    network = struct.unpack_from(f"{endian}I", data, 20)[0]
    if network != 1:
        logger.warning(
            f"PCAP link type is {network}, not Ethernet (1). "
            "Will attempt to parse but may fail."
        )

    offset = 24
    payloads: list[bytes] = []

    while offset + 16 <= len(data):
        # Packet header: ts_sec(4) + ts_usec(4) + incl_len(4) + orig_len(4)
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack_from(
            f"{endian}IIII", data, offset
        )
        offset += 16

        if offset + incl_len > len(data):
            logger.warning(
                f"Truncated PCAP packet at offset {offset - 16}. Stopping."
            )
            break

        packet_data = data[offset : offset + incl_len]
        offset += incl_len

        # Strip Ethernet header
        if len(packet_data) < ETH_HEADER_LEN:
            continue

        eth_type = struct.unpack_from(">H", packet_data, 12)[0]
        if eth_type != 0x0800:  # Not IPv4
            continue

        ip_data = packet_data[ETH_HEADER_LEN:]
        if len(ip_data) < IP_HEADER_MIN_LEN:
            continue

        # IP header: version+IHL in first byte, protocol at byte 9
        ihl = (ip_data[0] & 0x0F) * 4
        protocol = ip_data[9]

        if protocol != 17:  # Not UDP
            continue

        if len(ip_data) < ihl + UDP_HEADER_LEN:
            continue

        udp_data = ip_data[ihl:]
        # UDP header: src_port(2) + dst_port(2) + length(2) + checksum(2)
        udp_payload = udp_data[UDP_HEADER_LEN:]

        if len(udp_payload) >= 12:  # Minimum DIS PDU header size
            payloads.append(udp_payload)

    return payloads


def parse_dis_capture(filepath: str) -> dict[str, Any]:
    """Parse a DIS capture file and produce entity timelines + statistics.

    Supports:
    - Raw binary DIS streams (.dis, .bin) — concatenated PDUs
    - PCAP files (.pcap) — extracts DIS from UDP payloads

    Args:
        filepath: Path to capture file.

    Returns:
        Dict with:
        - source_file: filename
        - capture_format: "pcap" or "raw_binary"
        - total_pdus: total PDU count
        - pdu_type_breakdown: {type_name: count}
        - entity_count: number of unique entities
        - entities: list of entity timelines (position, orientation, damage)
        - statistics: summary stats (duration, avg update rate, etc.)
        - all_pdus: list of all parsed PDU records

    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If file exceeds size limits or cannot be parsed.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Capture file not found: {filepath}")

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"Capture file too large ({file_size / 1e9:.2f} GB). "
            f"Maximum supported size is 1 GB."
        )
    if file_size > WARN_FILE_SIZE_BYTES:
        logger.warning(f"Large capture file ({file_size / 1e6:.1f} MB). Processing may be slow.")

    if file_size == 0:
        return _empty_result(path.name, "raw_binary")

    data = path.read_bytes()
    is_pcap = _detect_pcap(data)

    if is_pcap:
        capture_format = "pcap"
        # Extract DIS payloads from PCAP packets
        try:
            payloads = _parse_pcap_packets(data)
        except ValueError as e:
            raise ValueError(f"Failed to parse PCAP file: {e}") from e

        if not payloads:
            return _empty_result(path.name, capture_format)

        # Parse each payload as a DIS PDU stream (each packet may contain one PDU)
        all_parsed = []
        for payload in payloads:
            parsed = parse_dis_binary(payload)
            all_parsed.extend(parsed)
    else:
        capture_format = "raw_binary"
        all_parsed = parse_dis_binary(data)

    if not all_parsed:
        return _empty_result(path.name, capture_format)

    # Extract fields from all PDUs
    all_pdu_records: list[dict[str, Any]] = []
    type_breakdown: dict[str, int] = {}
    dis_version = None
    exercise_id = None

    for i, (pdu, _raw) in enumerate(all_parsed):
        fields = _extract_pdu_fields(pdu, i)
        all_pdu_records.append(fields)

        type_name = fields["pdu_type_name"]
        type_breakdown[type_name] = type_breakdown.get(type_name, 0) + 1

        if dis_version is None:
            dis_version = fields["protocol_version"]
        if exercise_id is None:
            exercise_id = fields["exercise_id"]

    # Group entity states by entity ID
    entities_map: dict[str, dict[str, Any]] = {}

    for pdu, _raw in all_parsed:
        pdu_type = int(pdu.pduType)
        if pdu_type != 1:  # Only EntityStatePdu
            continue

        eid = pdu.entityID
        eid_string = _format_entity_id_string(eid)

        if eid_string not in entities_map:
            entities_map[eid_string] = {
                "entity_id": _format_entity_id(eid),
                "entity_id_string": eid_string,
                "force_id": int(pdu.forceId),
                "entity_type": {
                    "kind": int(pdu.entityType.entityKind),
                    "domain": int(pdu.entityType.domain),
                    "country": int(pdu.entityType.country),
                    "category": int(pdu.entityType.category),
                    "subcategory": int(pdu.entityType.subcategory),
                },
                "timeline": [],
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

        timeline_point = {
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
            "damage_state": _extract_damage_state(pdu),
        }

        entities_map[eid_string]["timeline"].append(timeline_point)

    # Build entity list with per-entity statistics
    entities_list = []
    for eid_string, entity_data in entities_map.items():
        timeline = entity_data["timeline"]
        entity_data["state_count"] = len(timeline)

        # Per-entity stats
        if len(timeline) >= 2:
            timestamps = [p["timestamp"] for p in timeline]
            min_ts, max_ts = min(timestamps), max(timestamps)
            entity_data["first_timestamp"] = min_ts
            entity_data["last_timestamp"] = max_ts

            speeds = [p["velocity_mps"]["speed"] for p in timeline]
            entity_data["speed_stats"] = {
                "min_mps": round(min(speeds), 3),
                "max_mps": round(max(speeds), 3),
                "avg_mps": round(sum(speeds) / len(speeds), 3),
            }
        else:
            entity_data["first_timestamp"] = timeline[0]["timestamp"] if timeline else None
            entity_data["last_timestamp"] = timeline[0]["timestamp"] if timeline else None
            entity_data["speed_stats"] = None

        entities_list.append(entity_data)

    # Compute global statistics
    statistics = _compute_statistics(all_pdu_records, entities_list)

    return {
        "source_file": path.name,
        "capture_format": capture_format,
        "file_size_bytes": file_size,
        "dis_version": dis_version,
        "exercise_id": exercise_id,
        "total_pdus": len(all_pdu_records),
        "pdu_type_breakdown": type_breakdown,
        "entity_count": len(entities_list),
        "entities": entities_list,
        "statistics": statistics,
        "all_pdus": all_pdu_records,
    }


def _extract_damage_state(pdu: Any) -> str:
    """Extract damage state from EntityStatePdu appearance bits.

    IEEE 1278.1 EntityAppearance bits 3-4 encode damage:
    00 = no damage, 01 = slight, 10 = moderate, 11 = destroyed
    """
    appearance = int(pdu.entityAppearance)
    damage_bits = (appearance >> 3) & 0x03
    damage_map = {0: "no_damage", 1: "slight", 2: "moderate", 3: "destroyed"}
    return damage_map.get(damage_bits, "unknown")


def _compute_statistics(
    all_pdus: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute summary statistics across the entire capture."""
    if not all_pdus:
        return {
            "duration_seconds": 0,
            "total_entity_state_updates": 0,
            "total_fire_events": 0,
            "total_detonation_events": 0,
            "avg_update_rate_hz": 0,
            "entity_count": 0,
        }

    timestamps = [p["timestamp"] for p in all_pdus]
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    # DIS timestamp is in units of 2^31 = ~1.676 hours. Convert to seconds.
    # Each tick = (3600 / 2^31) seconds ~= 1.676e-6 seconds
    duration_ticks = max_ts - min_ts
    duration_seconds = duration_ticks * (3600.0 / (2**31)) if duration_ticks > 0 else 0

    entity_state_count = sum(1 for p in all_pdus if p["pdu_type"] == 1)
    fire_count = sum(1 for p in all_pdus if p["pdu_type"] == 2)
    detonation_count = sum(1 for p in all_pdus if p["pdu_type"] == 3)

    avg_update_rate = (
        entity_state_count / duration_seconds if duration_seconds > 0 else 0
    )

    return {
        "duration_seconds": round(duration_seconds, 3),
        "total_entity_state_updates": entity_state_count,
        "total_fire_events": fire_count,
        "total_detonation_events": detonation_count,
        "avg_update_rate_hz": round(avg_update_rate, 3),
        "entity_count": len(entities),
    }


def _empty_result(filename: str, capture_format: str) -> dict[str, Any]:
    """Return an empty result for files with no parseable PDUs."""
    return {
        "source_file": filename,
        "capture_format": capture_format,
        "file_size_bytes": 0,
        "dis_version": None,
        "exercise_id": None,
        "total_pdus": 0,
        "pdu_type_breakdown": {},
        "entity_count": 0,
        "entities": [],
        "statistics": {
            "duration_seconds": 0,
            "total_entity_state_updates": 0,
            "total_fire_events": 0,
            "total_detonation_events": 0,
            "avg_update_rate_hz": 0,
            "entity_count": 0,
        },
        "all_pdus": [],
    }
