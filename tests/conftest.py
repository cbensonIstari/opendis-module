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
