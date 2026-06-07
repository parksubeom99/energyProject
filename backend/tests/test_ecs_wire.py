"""P2 M3-WIRE: supervisor hooks fire once per pipeline stage, and the opt-in
pre-action gate maps a denial to HTTP 403.

This test is pure and dependency-free: it monkeypatches the (best-effort,
opt-in) ``ecs_integration`` shim so its functions just record their calls. No
network, no running supervisor, no ecs_client/schema needed -- so it runs in the
normal suite. It proves the wiring added to ``main.py`` (which stages report,
in what order, and that a gate denial becomes a 403) without touching the
pipeline modules the rest of the suite already covers.

The real network path (ecs_client -> urllib -> /events with a valid C0
payload) is exercised separately against a stub collector; see the project's
P2 wiring notes / INTEGRATION.md.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ecs_integration  # noqa: E402
import main  # noqa: E402

# A trivially valid, parseable sample so parse_code does not 422.
SAMPLE = "def f(x):\n    return x + 1\n"


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def token(client):
    r = client.post(
        "/auth/token", json={"username": "admin", "password": "greenpulse"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_analyze_sync_emits_three_stage_events(client, token, monkeypatch):
    seen = []
    monkeypatch.setattr(
        ecs_integration, "observe", lambda agent_id, **kw: seen.append(agent_id)
    )
    r = client.post("/analyze/sync", json={"source_code": SAMPLE}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert seen == ["energy-parser", "energy-analyzer", "energy-scorer"]


def test_optimize_emits_five_stage_events(client, token, monkeypatch):
    seen = []
    monkeypatch.setattr(
        ecs_integration, "observe", lambda agent_id, **kw: seen.append(agent_id)
    )
    monkeypatch.setattr(ecs_integration, "gate", lambda *a, **k: None)
    r = client.post("/optimize", json={"source_code": SAMPLE}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert seen == [
        "energy-parser",
        "energy-analyzer",
        "energy-scorer",
        "energy-optimizer",
        "energy-verifier",
    ]


def test_optimize_gate_denied_maps_to_403(client, token, monkeypatch):
    def deny(*a, **k):
        raise ecs_integration.ActionDenied("blocked by policy")

    monkeypatch.setattr(ecs_integration, "gate", deny)
    monkeypatch.setattr(ecs_integration, "observe", lambda *a, **k: None)
    r = client.post("/optimize", json={"source_code": SAMPLE}, headers=_auth(token))
    assert r.status_code == 403, r.text
    assert "reason" in r.json()["detail"]


def test_shim_is_noop_when_disabled(monkeypatch):
    """With no ECS_SUPERVISOR_URL the shim is inert: observe/gate do nothing and
    nothing raises (the property the existing suite relies on)."""
    assert ecs_integration.enabled() is False
    assert ecs_integration.observe("energy-parser") is None
    assert ecs_integration.gate("energy-optimizer") is None
