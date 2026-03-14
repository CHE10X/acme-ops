#!/usr/bin/env python3
"""Bonfire V3 router facade."""

from __future__ import annotations

import time
from typing import Any, Dict

from bonfire.bonfire_logger import append_event, _iso_now
from bonfire.collector.session_tracker import get_or_start_session
from bonfire.collector.tool_tracker import emit_routing_signal
try:
    from bonfire.collector.token_hook import record_route_decision
except Exception:  # pragma: no cover
    record_route_decision = None

from bonfire.governor.token_governor import apply_mitigation, preflight
from bonfire.optimizer.optimizer import optimize_model
from bonfire.predictor.predictor import predict


def _coerce_str(value: Any, default: str = "") -> str:
    try:
        value = str(value)
    except Exception:
        return default
    value = value.strip()
    return value or default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        value = int(value)
        if value < 0:
            return default
        return value
    except Exception:
        return default


def _build_context(agent_context: Dict[str, Any] | None) -> Dict[str, Any]:
    context = dict(agent_context or {})
    context["agent_id"] = _coerce_str(context.get("agent_id"), "unknown")
    context["session_id"] = _coerce_str(context.get("session_id"), "")
    context["lane"] = _coerce_str(context.get("lane"), "interactive")
    context["requested_model"] = _coerce_str(context.get("requested_model") or context.get("model"), "claude-sonnet")
    context["prompt"] = _coerce_str(context.get("prompt"), "")
    context.setdefault("tool_invocations", _coerce_int(context.get("tool_invocations"), 0))
    return context


def _log_router_decision(payload: Dict[str, Any]) -> None:
    if record_route_decision is not None:
        try:
            record_route_decision(**payload)
            return
        except Exception:
            pass

    # Fallback decision event to avoid hard dependency on token_hook internals.
    event = {
        "timestamp": _iso_now(),
        "event": "router_decision",
        "agent_id": payload.get("agent_id", "unknown"),
        "session_id": payload.get("session_id") or "unknown",
        "model": _coerce_str(payload.get("selected_model") or payload.get("requested_model"), "unknown"),
        "prompt_tokens": _coerce_int(payload.get("predicted_prompt_tokens"), -1),
        "completion_tokens": _coerce_int(payload.get("predicted_completion_tokens"), -1),
        "total_tokens": _coerce_int(payload.get("predicted_total_tokens"), -1),
        "tool_used": "model_router",
        "latency_ms": _coerce_int(payload.get("decision_ms"), 0),
        "status": payload.get("status", "ok"),
        "lane": _coerce_str(payload.get("selected_lane"), "interactive"),
        "session_runway": _coerce_str(payload.get("governor_action"), "allow"),
        "decision": payload,
    }
    append_event(event)


def route(agent_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run the full V3 routing pipeline and return a structured decision."""
    context = _build_context(agent_context)
    started = time.perf_counter()

    agent_id = context["agent_id"]
    lane = context["lane"]
    requested_model = context["requested_model"]
    prompt = context["prompt"]
    original_session_id = context.get("session_id") or None

    # Attach stable session id and keep existing session lifecycle behavior.
    session_id = get_or_start_session(agent_id, session_id=original_session_id)
    context["session_id"] = session_id

    # Predictor estimates.
    prediction = predict(context)
    prediction["agent_id"] = agent_id
    prediction["session_id"] = session_id

    # Optimizer classifies request tier/model choice before governor checks.
    optimization = optimize_model(
        requested_model=requested_model,
        lane=lane,
        predicted_tokens=prediction["total_tokens"],
        prompt=prompt,
    )

    optimized_model = optimization.get("model", requested_model)

    # Governor preflight determines whether lane/model is allowed and if action is required.
    gov_decision = preflight(
        agent_id=agent_id,
        lane=lane,
        model=optimized_model,
        prompt=prompt,
        session_id=session_id,
        requested_chain_models=None,
        predicted_tokens=prediction["total_tokens"],
    )
    final = apply_mitigation(
        agent_id=agent_id,
        decision=gov_decision,
        prompt=prompt,
        route_model=optimized_model,
    )

    decision_status = _coerce_str(gov_decision.get("status"), "ALLOW")
    action = _coerce_str(final.get("action"), "allow")
    if action == "reject":
        selected_model = None
        status = final.get("status") or "TOKEN_BUDGET_EXCEEDED"
    else:
        selected_model = _coerce_str(final.get("route_model") or final.get("model") or optimized_model, requested_model)
        status = "ok"

    final_lane = final.get("final_lane") or final.get("lane") or lane

    decision = {
        "agent_id": agent_id,
        "session_id": session_id,
        "requested_model": requested_model,
        "selected_model": selected_model,
        "selected_lane": _coerce_str(final_lane, lane),
        "decision_ms": _coerce_int(int((time.perf_counter() - started) * 1000), 0),
        "status": status,
        "governor_action": action,
        "governor_status": _coerce_str(final.get("status"), decision_status),
        "predicted_prompt_tokens": prediction["prompt_tokens"],
        "predicted_completion_tokens": prediction["completion_tokens"],
        "predicted_total_tokens": prediction["total_tokens"],
        "model_tier": _coerce_str(optimization.get("model_tier"), "medium"),
        "optimizer_reason": _coerce_str(optimization.get("decision_reason"), "adaptive_select"),
        "route_tool": "model_router",
    }

    # Keep a small audit trail without altering the existing runtime token/event contract.
    _log_router_decision(decision)

    try:
        emit_routing_signal(
            agent_id=agent_id,
            session_id=session_id,
            model=_coerce_str(selected_model or requested_model, requested_model),
            predicted_tokens=prediction["total_tokens"],
            lane=decision["selected_lane"],
            governor_action=decision["governor_action"],
        )
    except Exception:
        pass

    return decision


def select_model(agent_context: Dict[str, Any] | None = None) -> str | None:
    """Hook-compatible selector used by runtime callers."""
    decision = route(agent_context)
    return decision.get("selected_model")
