"""Best-effort ECS supervisor wiring (P2 M3-WIRE).

Reports each pipeline stage of energyProject to the el_supervisor collector
(``POST /events``, post-hoc audit) and, optionally, gates a stage before it
runs (``POST /decisions``). The integration is **entirely opt-in** and
**best-effort**, so it can never change or break the host pipeline:

- **Disabled unless ``ECS_SUPERVISOR_URL`` is set.** With it unset (the default,
  and what the existing test suite runs with) every call here is a no-op, so
  behavior is byte-for-byte unchanged.
- **Reporting never raises into the host.** Every ``report_action`` call is
  wrapped in ``try/except``; a down, slow, or misconfigured supervisor is
  swallowed silently. Observation must not be able to break optimization.
- **ecs_client stays frozen and dependency-light.** ``ecs_client`` (stdlib +
  the frozen C0 ``schema`` only) is imported from the el_supervisor repo, whose
  root is taken from ``ECS_SUPERVISOR_PATH``. Any import failure simply leaves
  the integration disabled.

Gating is the one place that may deny: it is opt-in via ``ECS_GATE_STAGES``
(comma-separated agent ids) and, when a listed stage is denied, ``ActionDenied``
is raised on purpose -- the whole point of a pre-action gate is that a denied
action does not run. ``main.py`` maps that to an HTTP 403.

Environment:
- ``ECS_SUPERVISOR_URL``   e.g. ``http://localhost:8001`` (enables the wiring)
- ``ECS_SUPERVISOR_PATH``  filesystem path to the el_supervisor repo root
                           (so ``ecs_client`` / ``schema`` are importable)
- ``ECS_GATE_STAGES``      comma-separated agent ids to gate, e.g.
                           ``energy-optimizer`` (default: none)
"""
from __future__ import annotations

import os
import sys
from typing import Optional

_URL = os.getenv("ECS_SUPERVISOR_URL")
_GATE_STAGES = {
    s.strip() for s in os.getenv("ECS_GATE_STAGES", "").split(",") if s.strip()
}

_client = None
_enabled = False


class ActionDenied(Exception):
    """Local stand-in so callers can ``except ActionDenied`` even when the real
    ecs_client could not be imported. Replaced by the real class on success."""


def _try_import() -> None:
    """Wire up the client once, best-effort. Leaves the integration disabled on
    any problem (no URL, ecs_client not importable, bad config)."""
    global _client, _enabled, ActionDenied
    if not _URL:
        return
    try:
        path = os.getenv("ECS_SUPERVISOR_PATH")
        if path and path not in sys.path:
            sys.path.insert(0, path)
        from ecs_client import EcsClient
        from ecs_client.client import ActionDenied as _RealDenied

        _client = EcsClient(_URL)
        ActionDenied = _RealDenied  # type: ignore[misc]
        _enabled = True
    except Exception:
        _client = None
        _enabled = False


_try_import()


def enabled() -> bool:
    """True only when the supervisor wiring is active."""
    return _enabled


def observe(agent_id: str, *, operation_name: str = "invoke_agent",
            tool_name: Optional[str] = None) -> None:
    """Post-hoc: report a completed stage to ``/events``. Never raises."""
    if not _enabled:
        return
    try:
        _client.report_action(
            provider_name="energyProject",
            operation_name=operation_name,
            agent_id=agent_id,
            tool_name=tool_name,
        )
    except Exception:
        # Best-effort: a supervisor problem must never break the pipeline.
        pass


def gate(agent_id: str, *, operation_name: str = "invoke_agent",
         ecs_policy_action: Optional[str] = None,
         ecs_actor: Optional[str] = None) -> None:
    """Pre-action: ask ``/decisions`` before a stage runs.

    Only stages listed in ``ECS_GATE_STAGES`` are gated; for everything else
    this is a no-op. On a listed stage, ``ActionDenied`` from the supervisor is
    allowed to propagate so the caller can refuse to run the action.

    ``ecs_policy_action`` lets a caller express a domain verdict in the frozen
    C0 governance vocabulary (``"warn"`` / ``"block"``); the supervisor's
    deterministic ruleset scores ``block`` as a denial. Article 12 requires an
    actor whenever a policy action is set, so ``ecs_actor`` must accompany a
    non-None ``ecs_policy_action`` (the client enforces this before any network).
    """
    if not _enabled or agent_id not in _GATE_STAGES:
        return
    _client.guard(
        provider_name="energyProject",
        operation_name=operation_name,
        agent_id=agent_id,
        ecs_policy_action=ecs_policy_action,
        ecs_actor=ecs_actor,
    )
