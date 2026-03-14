#!/usr/bin/env python3
"""Preflight governance checks for token and behavior controls."""

from __future__ import annotations

import time
from typing import Any, Dict

from bonfire.budgets.budget_manager import precheck, get_all_alerts_config, record_usage
from bonfire.collector.session_tracker import get_session_start
from bonfire.runtime.agent_throttle import check_agent, update_thresholds
from bonfire.runtime.model_guard import allowed_lanes_for_agent, enforce_model, normalize_for_chain
from bonfire.collector.session_tracker import terminate_session
from bonfire.bonfire_logger import append_alert
from bonfire.predictor.token_predictor import threshold_mitigation
from bonfire.risk.agent_risk_score import record_escalation, score_for


def _to_int(value: Any, default: int = 0) -> int:
    try:
        n = int(value)
        return n if n >= 0 else default
    except Exception:
        return default


def _estimate_tokens(text: str) -> int:
    return max(0, _to_int(len((text or "")), 0) // 4)


def _norm_agent(agent_id: str) -> str:
    return (agent_id or "unknown").strip().lower()


def _session_duration_secs(agent_id: str, session_id: str | None) -> float:
    if not session_id:
        return 0.0
    started = get_session_start(agent_id, session_id=session_id)
    if not started:
        return 0.0
    try:
        return max(0.0, time.time() - started)
    except Exception:
        return 0.0


def _fallback_allow(agent_id: str, lane: str, model: str, reason: str | None = None) -> Dict[str, Any]:
    return {
        "action": "allow",
        "status": "GOVERNOR_FALLBACK_ALLOW",
        "agent_id": agent_id,
        "lane": lane,
        "model": model,
        "reason": reason or "governor_failure",
        "estimated_tokens": 0,
        "mitigation": "none",
    }


_CRITICAL_AGENTS = {"watchdog", "sentinel", "agent911"}


def preflight(
    *,
    agent_id: str,
    lane: str,
    model: str,
    prompt: str,
    session_id: str | None,
    requested_chain_models: list[str] | None = None,
    predicted_tokens: int | None = None,
) -> Dict[str, Any]:
    """Run governance checks before a model call.

    Returns a decision dictionary that includes action + status.
    """
    try:
        lane = lane or "interactive"
        model = (model or "").strip() or "claude-sonnet"
        estimate = _estimate_tokens(prompt)
        if predicted_tokens is not None:
            estimate = _to_int(predicted_tokens, estimate)

        predicted_action = threshold_mitigation(estimate, lane)
        if predicted_action == "reject" and _norm_agent(agent_id) not in _CRITICAL_AGENTS:
            append_alert(f"GOVERNOR predictive_reject agent={agent_id} lane={lane} predicted={estimate}")
            return {
                "action": "reject",
                "status": "PREDICTIVE_TOKEN_BUDGET_EXCEEDED",
                "agent_id": agent_id,
                "lane": lane,
                "model": model,
                "estimated_tokens": estimate,
                "mitigation": "reject",
                "reason": "predictive_burn_exceeded",
            }
        if predicted_action == "downgrade" and _norm_agent(agent_id) not in _CRITICAL_AGENTS:
            append_alert(f"GOVERNOR predictive_downgrade agent={agent_id} lane={lane} predicted={estimate}")

        allowed_lanes = allowed_lanes_for_agent(agent_id)
        if not allowed_lanes:
            allowed_lanes = ["interactive"]
        if lane not in allowed_lanes:
            # move to a permitted lane when possible
            next_lane = "interactive"
            if "background" in allowed_lanes:
                next_lane = "background"
            elif "system" in allowed_lanes:
                next_lane = "system"
            else:
                next_lane = allowed_lanes[0]

            append_alert(
                f"GOVERNOR lane_violation agent={agent_id} requested={lane} selected={next_lane}"
            )
            lane = next_lane

        guarded_model, model_mitigation = enforce_model(agent_id, lane, model)
        if model_mitigation == "downgrade":
            append_alert(
                f"GOVERNOR model_mitigated agent={agent_id} lane={lane} original={model} updated={guarded_model}"
            )
        guarded_model = normalize_for_chain(guarded_model) if guarded_model else guarded_model

        budget_decision = precheck(agent_id, lane, guarded_model, session_id, estimate)
        decision = dict(budget_decision)
        decision["lane"] = lane
        decision["model"] = guarded_model

        if decision.get("status") != "ALLOW" and decision.get("action") == "move_to_lane":
            # keep moving to background lane and continue with same mitigation model.
            decision["lane"] = lane
            decision["model"] = guarded_model

        # Runaway policy tuned from budget alerts configuration.
        if _norm_agent(agent_id) not in _CRITICAL_AGENTS:
            risk = score_for(agent_id, session_id=session_id)
            risk_score = int(risk.get("risk_score", 0))
            if risk_score >= 90:
                append_alert(
                    f"GOVERNOR runaway_risk agent={agent_id} level={risk.get('risk_level')} score={risk_score}"
                )
                decision = {
                    "action": "terminate",
                    "status": "RUNAWAY_RISK_TERMINATE",
                    "agent_id": agent_id,
                    "lane": lane,
                    "model": guarded_model,
                    "estimated_tokens": estimate,
                    "mitigation": "terminate",
                    "reason": "runaway_risk_score",
                }
                if session_id:
                    try:
                        terminate_session(agent_id, session_id=session_id)
                    except Exception:
                        pass
                return decision
            elif risk_score >= 60 and lane == "interactive":
                lane = "background"
                append_alert(
                    f"GOVERNOR risk_lane_downgrade agent={agent_id} score={risk_score} lane={lane}"
                )
                record_escalation(agent_id)
        alerts = get_all_alerts_config()
        try:
            update_thresholds(
                requests_per_minute=alerts.get("requests_per_minute", 120),
                token_growth_per_min=alerts.get("agent_token_growth_per_min", 8000),
                tool_loop_count_per_min=alerts.get("tool_loop_count_per_min", 20),
                session_duration_limit_s=alerts.get("session_duration_limit_s", 14400),
                cooldown_seconds=alerts.get("runaway_cooldown_seconds", 60),
            )
        except Exception:
            pass

        # Run runaway guard after budget context; session duration may still terminate throttled agents.
        duration = _session_duration_secs(agent_id, session_id)
        run_result = check_agent(agent_id, session_id=session_id, session_duration_s=duration, pending_tokens=estimate)
        decision["runaway"] = run_result

        # If governor says terminate, prefer explicit reject/terminate semantics.
        if run_result.get("action") == "terminate":
            decision.update(
                {
                    "action": "terminate",
                    "status": run_result.get("status", "RUNAWAY_AGENT_TERMINATED"),
                    "mitigation": "terminate",
                    "reason": run_result.get("reason", "runaway"),
                }
            )
            if session_id:
                try:
                    terminate_session(agent_id, session_id=session_id)
                except Exception:
                    pass
            return decision

        if run_result.get("action") == "delay":
            decision.update(
                {
                    "action": "delay",
                    "status": run_result.get("status", "RUNAWAY_AGENT_PAUSED"),
                    "mitigation": "delay",
                    "reason": run_result.get("reason", "runaway"),
                    "delay_seconds": run_result.get("delay_seconds", 0),
                }
            )
            return decision

        # budget decision may ask for downgrade
        if decision.get("action") == "downgrade":
            decision["model"] = normalize_for_chain(guarded_model)
            decision["status"] = "MODEL_BUDGET_REWRITE"
            decision["mitigation"] = "downgrade"

        if predicted_action == "downgrade" and decision.get("action") == "allow":
            decision["action"] = "downgrade"
            decision["status"] = "PREDICTIVE_MODEL_REWRITE"
            decision["mitigation"] = "downgrade"
            decision["model"] = normalize_for_chain("claude-sonnet")
            decision["reason"] = "predictive_downgrade"
            record_escalation(agent_id)

        return decision

    except Exception:
        return _fallback_allow(agent_id, lane, model)


def on_request_complete(agent_id: str, lane: str, model: str, session_id: str | None, tokens: int) -> None:
    try:
        record_usage(agent_id, lane, model, session_id, _to_int(tokens, 0))
    except Exception:
        pass


def apply_mitigation(agent_id: str, decision: Dict[str, Any], prompt: str, route_model: str) -> Dict[str, Any]:
    """Normalize model/router inputs after preflight."""
    lane = decision.get("lane", "interactive")
    model = decision.get("model") or route_model
    status = decision.get("status", "ALLOW")
    if status == "GOVERNOR_FALLBACK_ALLOW":
        return decision

    action = decision.get("action", "allow")

    if action == "reject":
        decision["route_model"] = None
        decision["final_lane"] = lane
    elif action == "delay":
        delay = int(decision.get("delay_seconds", 60) or 0)
        decision["route_model"] = model
        decision["final_lane"] = lane
        decision["delay_seconds"] = delay
        if delay > 0:
            time.sleep(delay)
    elif action in ("move_to_lane", "move_lane"):
        decision["final_lane"] = lane
        decision["route_model"] = model
    elif action == "downgrade":
        decision["route_model"] = model
        decision["final_lane"] = lane
    elif action == "terminate":
        decision["route_model"] = None
        decision["final_lane"] = lane
    else:
        decision["route_model"] = model
        decision["final_lane"] = lane
    return decision
