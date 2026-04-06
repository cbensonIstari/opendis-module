"""Programmatic DIS binary test file creation using opendis.

Creates binary DIS files containing EntityStatePdu, FirePdu, and DetonationPdu
records for testing all 5 module functions.
"""

import struct
from io import BytesIO

import pytest
from opendis.DataOutputStream import DataOutputStream
from opendis.dis7 import DetonationPdu, EntityStatePdu, FirePdu


def _serialize_pdu(pdu) -> bytes:
    """Serialize an opendis PDU to bytes, fixing the length field in the header."""
    stream = BytesIO()
    out = DataOutputStream(stream)
    pdu.serialize(out)
    data = stream.getvalue()
    # Fix length at header bytes 8-9 (big-endian uint16)
    actual_len = len(data)
    data = data[:8] + struct.pack(">H", actual_len) + data[10:]
    return data


def _make_entity_state(
    site=42, app=1, entity_id=1, timestamp=0,
    x=4500000.0, y=200000.0, z=4200000.0,
    psi=1.57, theta=0.0, phi=0.0,
    vx=10.0, vy=0.0, vz=0.0,
    force_id=1,
) -> bytes:
    """Create and serialize an EntityStatePdu."""
    pdu = EntityStatePdu()
    pdu.pduType = 1
    pdu.protocolFamily = 1
    pdu.protocolVersion = 7
    pdu.exerciseID = 1
    pdu.pduStatus = 0
    pdu.entityAppearance = 0
    pdu.capabilities = 0
    pdu.timestamp = timestamp
    pdu.entityID.entityID = entity_id
    pdu.entityID.siteID = site
    pdu.entityID.applicationID = app
    pdu.entityLocation.x = x
    pdu.entityLocation.y = y
    pdu.entityLocation.z = z
    pdu.entityOrientation.psi = psi
    pdu.entityOrientation.theta = theta
    pdu.entityOrientation.phi = phi
    pdu.entityLinearVelocity.x = vx
    pdu.entityLinearVelocity.y = vy
    pdu.entityLinearVelocity.z = vz
    pdu.forceId = force_id
    pdu.entityType.entityKind = 1
    pdu.entityType.domain = 1
    pdu.entityType.country = 225
    pdu.entityType.category = 1
    pdu.entityType.subcategory = 1
    return _serialize_pdu(pdu)


def _make_fire(
    site=42, app=1, firing_id=1, target_id=2, timestamp=5000
) -> bytes:
    """Create and serialize a FirePdu."""
    pdu = FirePdu()
    pdu.pduType = 2
    pdu.protocolFamily = 2
    pdu.protocolVersion = 7
    pdu.exerciseID = 1
    pdu.pduStatus = 0
    pdu.timestamp = timestamp
    pdu.firingEntityID.siteID = site
    pdu.firingEntityID.applicationID = app
    pdu.firingEntityID.entityID = firing_id
    pdu.targetEntityID.siteID = site
    pdu.targetEntityID.applicationID = app
    pdu.targetEntityID.entityID = target_id
    return _serialize_pdu(pdu)


def _make_detonation(
    site=42, app=1, firing_id=1, target_id=2, timestamp=5500,
    x=4500100.0, y=200050.0, z=4200020.0,
) -> bytes:
    """Create and serialize a DetonationPdu."""
    pdu = DetonationPdu()
    pdu.pduType = 3
    pdu.protocolFamily = 2
    pdu.protocolVersion = 7
    pdu.exerciseID = 1
    pdu.pduStatus = 0
    pdu.timestamp = timestamp
    pdu.firingEntityID.siteID = site
    pdu.firingEntityID.applicationID = app
    pdu.firingEntityID.entityID = firing_id
    pdu.targetEntityID.siteID = site
    pdu.targetEntityID.applicationID = app
    pdu.targetEntityID.entityID = target_id
    pdu.location.x = x
    pdu.location.y = y
    pdu.location.z = z
    return _serialize_pdu(pdu)


def _build_pcap_file(dis_payloads: list[bytes]) -> bytes:
    """Build a minimal PCAP file wrapping DIS payloads in Ethernet/IP/UDP.

    Creates a valid libpcap file with:
    - Global header (magic, version 2.4, Ethernet link type)
    - One packet record per DIS payload, each wrapped in Eth/IP/UDP headers
    """
    # PCAP global header (little-endian)
    # magic(4) + ver_major(2) + ver_minor(2) + thiszone(4) + sigfigs(4) + snaplen(4) + network(4)
    global_header = struct.pack(
        "<IHHiIII",
        0xA1B2C3D4,  # magic
        2, 4,         # version 2.4
        0,            # timezone offset
        0,            # timestamp accuracy
        65535,        # snaplen
        1,            # Ethernet
    )

    packets = b""
    for i, payload in enumerate(dis_payloads):
        udp_len = 8 + len(payload)
        ip_total_len = 20 + udp_len
        frame_len = 14 + ip_total_len

        # Ethernet header: dst(6) + src(6) + type(2) = 14 bytes
        eth = b"\x00" * 6 + b"\x00" * 6 + struct.pack(">H", 0x0800)

        # IP header (20 bytes, no options): ver+IHL, DSCP, total_len, id, flags+frag,
        # TTL, protocol(17=UDP), checksum(0), src_ip, dst_ip
        ip_header = struct.pack(
            ">BBHHHBBH4s4s",
            0x45,  # version 4, IHL 5
            0,     # DSCP
            ip_total_len,
            0,     # identification
            0,     # flags + fragment offset
            64,    # TTL
            17,    # protocol = UDP
            0,     # checksum (0 = not computed)
            b"\xC0\xA8\x01\x01",  # src: 192.168.1.1
            b"\xEF\x01\x01\x01",  # dst: 239.1.1.1 (DIS multicast)
        )

        # UDP header: src_port(2) + dst_port(2) + length(2) + checksum(2)
        udp_header = struct.pack(">HHHH", 3000, 3000, udp_len, 0)

        packet_data = eth + ip_header + udp_header + payload

        # PCAP packet header: ts_sec(4) + ts_usec(4) + incl_len(4) + orig_len(4)
        pkt_header = struct.pack("<IIII", i, 0, len(packet_data), len(packet_data))
        packets += pkt_header + packet_data

    return global_header + packets


@pytest.fixture(scope="session")
def test_inputs_dir(tmp_path_factory):
    """Create a session-scoped directory with DIS test files."""
    d = tmp_path_factory.mktemp("test_inputs")

    # --- sample_scenario.dis: multi-entity scenario ---
    # 3 entities, 10 states each, plus fire and detonation events
    # Build as (timestamp, bytes) tuples and sort to ensure monotonic timestamps
    pdu_list: list[tuple[int, bytes]] = []
    for ts_step in range(10):
        ts = ts_step * 1000
        # Entity 1
        pdu_list.append((ts, _make_entity_state(
            entity_id=1, timestamp=ts,
            x=4500000.0 + ts_step * 100,
            y=200000.0, z=4200000.0,
        )))
        # Entity 2
        pdu_list.append((ts, _make_entity_state(
            entity_id=2, timestamp=ts,
            x=4500000.0, y=200000.0 + ts_step * 100,
            z=4200000.0, force_id=2,
        )))
        # Entity 3
        pdu_list.append((ts, _make_entity_state(
            entity_id=3, timestamp=ts,
            x=4500000.0, y=200000.0,
            z=4200000.0 + ts_step * 100, force_id=2,
        )))

    # Fire events (entity 1 fires at entity 2, multiple times)
    for i in range(3):
        ts = 3000 + i * 1000
        pdu_list.append((ts, _make_fire(
            firing_id=1, target_id=2, timestamp=ts
        )))

    # Detonation events
    for i in range(2):
        ts = 3500 + i * 1000
        pdu_list.append((ts, _make_detonation(
            firing_id=1, target_id=2, timestamp=ts,
        )))

    # Sort by timestamp to ensure monotonic ordering
    pdu_list.sort(key=lambda x: x[0])
    scenario_data = b"".join(data for _, data in pdu_list)

    (d / "sample_scenario.dis").write_bytes(scenario_data)

    # --- sample_single_entity.dis: single entity, 10 states ---
    single_data = b""
    for ts_step in range(10):
        ts = ts_step * 500
        single_data += _make_entity_state(
            entity_id=1, timestamp=ts,
            x=4500000.0 + ts_step * 50,
            y=200000.0 + ts_step * 25,
            z=4200000.0,
        )
    (d / "sample_single_entity.dis").write_bytes(single_data)

    # --- sample_invalid.dis: truncated/malformed ---
    # Take a valid PDU and truncate it
    valid = _make_entity_state()
    invalid_data = valid[:20]  # Truncated mid-PDU
    (d / "sample_invalid.dis").write_bytes(invalid_data)

    # --- empty.dis ---
    (d / "empty.dis").write_bytes(b"")

    # --- sample_capture.pcap: DIS PDUs wrapped in PCAP format ---
    # Build a minimal valid PCAP file with Ethernet/IP/UDP encapsulation
    pcap_data = _build_pcap_file([
        _make_entity_state(entity_id=1, timestamp=0, x=4500000.0, y=200000.0, z=4200000.0),
        _make_entity_state(entity_id=1, timestamp=1000, x=4500100.0, y=200000.0, z=4200000.0),
        _make_entity_state(entity_id=2, timestamp=0, x=4500000.0, y=200100.0, z=4200000.0, force_id=2),
        _make_entity_state(entity_id=2, timestamp=1000, x=4500000.0, y=200200.0, z=4200000.0, force_id=2),
        _make_fire(firing_id=1, target_id=2, timestamp=1500),
        _make_detonation(firing_id=1, target_id=2, timestamp=2000),
    ])
    (d / "sample_capture.pcap").write_bytes(pcap_data)

    return d


@pytest.fixture
def scenario_file(test_inputs_dir):
    return str(test_inputs_dir / "sample_scenario.dis")


@pytest.fixture
def single_entity_file(test_inputs_dir):
    return str(test_inputs_dir / "sample_single_entity.dis")


@pytest.fixture
def invalid_file(test_inputs_dir):
    return str(test_inputs_dir / "sample_invalid.dis")


@pytest.fixture
def empty_file(test_inputs_dir):
    return str(test_inputs_dir / "empty.dis")


@pytest.fixture
def pcap_file(test_inputs_dir):
    return str(test_inputs_dir / "sample_capture.pcap")
