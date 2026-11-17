"""Offline checks for LiveKit outbound trunk ID validation.

These tests only read and replace process environment variables.
They do not create a LiveKit client, list trunks, dial, or call an API.
"""

import pytest

import make_call


def test_get_trunk_id_accepts_livekit_outbound_id(monkeypatch):
    monkeypatch.setenv("LIVEKIT_OUTBOUND_TRUNK_ID", "  ST_AbC123def456  ")
    assert make_call.get_trunk_id() == "ST_AbC123def456"


def test_get_trunk_id_accepts_hex_body(monkeypatch):
    monkeypatch.setenv("LIVEKIT_OUTBOUND_TRUNK_ID", "ST_0123456789ab")
    assert make_call.get_trunk_id() == "ST_0123456789ab"


@pytest.mark.parametrize(
    "trunk_id",
    [
        "",
        "ST",
        "ST_",
        "STOP",
        "STRING",
        "st_AbC123def456",
        "ST_AbC123def45",
        "ST_AbC123def4567",
        "TR_AbC123def456",
    ],
)
def test_get_trunk_id_rejects_invalid_ids(monkeypatch, trunk_id):
    monkeypatch.setenv("LIVEKIT_OUTBOUND_TRUNK_ID", trunk_id)
    with pytest.raises(ValueError):
        make_call.get_trunk_id()


def test_get_trunk_id_rejects_missing_variable(monkeypatch):
    monkeypatch.delenv("LIVEKIT_OUTBOUND_TRUNK_ID", raising=False)
    with pytest.raises(ValueError):
        make_call.get_trunk_id()
