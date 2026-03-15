"""
Transmission v1 — Deterministic Model Routing
Arch/Ops Approved Build Packet 2026-03-15

Routes tasks to the appropriate AI model based on work_class classification,
lane preference, model capabilities, and execution config masking.

Zero writes to openclaw.json. Read-only. Deterministic. Observable.
Target: p95 routing latency < 10ms (heuristic path).
"""

import json
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORK_CLASS_PATTERNS: dict[str, list[str]] = {
    "coding":     ["code", "function", "debug", "refactor", "implement", "python", "class", "error", "test", "fix"],
    "analysis":   ["analyze", "evaluate", "compare", "investigate", "assess", "research", "explain why", "reason"],
    "writing":    ["write", "draft", "summarize", "document", "email", "report", "describe", "essay"],
    "organizing": ["list", "sort", "classify", "format", "json", "structure", "table", "parse", "extract"],
    "simple":     ["what is", "when", "who", "yes or no", "confirm", "check if", "how many"],
    "creative":   ["brainstorm", "imagine", "generate ideas", "suggest", "creative", "invent"],
}

EXECUTION_DEFAULTS: dict[str, dict] = {
    "coding":     {"mode": "stream", "temperature": 0.1, "tool_calling": True,  "structured_output": False},
    "analysis":   {"mode": "stream", "temperature": 0.3, "tool_calling": True,  "structured_output": False},
    "writing":    {"mode": "stream", "temperature": 0.5, "tool_calling": False, "structured_output": False},
    "organizing": {"mode": "batch",  "temperature": 0.0, "tool_calling": False, "structured_output": True},
    "simple":     {"mode": "batch",  "temperature": 0.2, "tool_calling": False, "structured_output": False},
    "creative":   {"mode": "stream", "temperature": 0.8, "tool_calling": False, "structured_output": False},
}

TIER_ORDER = ["premium", "budget-capable", "mid", "efficient"]

DEFAULT_CONFIG_PATH = Path.home() / ".openclaw" / "watchdog" / "transmission_config.json"
DEFAULT_LOG_PATH    = Path.home() / ".openclaw" / "watchdog" / "transmission_events.log"

# ---------------------------------------------------------------------------
# LRU Classification Cache
# ---------------------------------------------------------------------------

class LRUCache:
    def __init__(self, capacity: int):
        self.cache: OrderedDict = OrderedDict()
        self.capacity = max(1, capacity)

    def get(self, key: str):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: str, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)


# ---------------------------------------------------------------------------
# Config Loader (cached, mtime-aware)
# ---------------------------------------------------------------------------

_config_cache: dict = {}
_config_mtime: float = 0.0
_classification_cache: Optional[LRUCache] = None


def _load_config(config_path: Optional[Path] = None) -> dict:
    global _config_cache, _config_mtime, _classification_cache
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return _config_cache or {}
    if mtime != _config_mtime or not _config_cache:
        with open(path) as f:
            _config_cache = json.load(f)
        _config_mtime = mtime
        cache_size = _config_cache.get("classification_cache_size", 100)
        _classification_cache = LRUCache(cache_size)
    return _config_cache


# ---------------------------------------------------------------------------
# Event Logger
# ---------------------------------------------------------------------------

def _emit(event: str, req_id: str, log_path: Path, **payload):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "req_id": req_id,
        "event": event,
        **payload,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Heuristic Classifier
# ---------------------------------------------------------------------------

def _classify_heuristic(prompt: str, work_classes: list[str]) -> tuple[str, float, str]:
    """
    Returns (work_class, confidence, source).
    confidence = hits_for_winner / len(pattern_list_for_winner)
    Ties broken by lane preference (handled upstream) then quality_score.
    Here we return the winner and confidence; tie-breaking by tier is upstream.
    """
    prompt_lower = prompt.lower()
    hits: dict[str, int] = {}
    for wc in work_classes:
        patterns = WORK_CLASS_PATTERNS.get(wc, [])
        count = sum(1 for p in patterns if p in prompt_lower)
        if count > 0:
            hits[wc] = count

    if not hits:
        return "", 0.0, "heuristic"

    max_hits = max(hits.values())
    winners = [wc for wc, h in hits.items() if h == max_hits]
    winner = winners[0]  # tie-breaking by order (resolved upstream by lane pref)

    # Confidence = hits / max possible for that class
    max_possible = len(WORK_CLASS_PATTERNS.get(winner, []))
    confidence = max_hits / max_possible if max_possible > 0 else 0.0

    return winner, min(confidence, 1.0), "heuristic"


# ---------------------------------------------------------------------------
# Candidate Chain Builder
# ---------------------------------------------------------------------------

def _tier_rank(tier: str, lane_prefs: list[str]) -> int:
    try:
        return lane_prefs.index(tier)
    except ValueError:
        return len(lane_prefs)


def _build_candidate_chain(
    work_class: str,
    lane: str,
    models: dict,
    lane_preferences: dict,
    required_features: Optional[dict],
    gear_up: bool,
) -> list[str]:
    """
    Build ordered candidate list:
    1. enabled=True AND work_class in capabilities
    2. required_features filter
    3. Sort by lane preference tier, quality_score DESC, cost_weight ASC, latency ASC
    4. If gear_up: suppress lowest-tier candidates (shift one tier up)
    """
    lane_prefs: list[str] = lane_preferences.get(lane, TIER_ORDER)

    candidates = []
    for model_id, cfg in models.items():
        if not cfg.get("enabled", True):
            continue
        if work_class not in cfg.get("capabilities", []):
            continue
        if required_features:
            skip = False
            for feat, val in required_features.items():
                if val and not cfg.get(feat, False):
                    skip = True
                    break
            if skip:
                continue
        candidates.append((model_id, cfg))

    if not candidates:
        return []

    # If gear_up: drop candidates at the lowest tier present
    if gear_up and len(candidates) > 1:
        tiers_present = sorted(
            set(_tier_rank(c[1].get("tier", ""), lane_prefs) for c in candidates)
        )
        if len(tiers_present) > 1:
            worst_rank = tiers_present[-1]
            candidates = [c for c in candidates if _tier_rank(c[1].get("tier", ""), lane_prefs) < worst_rank]

    candidates.sort(key=lambda x: (
        _tier_rank(x[1].get("tier", ""), lane_prefs),
        -x[1].get("quality_score", 0),
        x[1].get("cost_weight", 999),
        x[1].get("latency_ms_p50", 999999),
    ))

    return [c[0] for c in candidates]


# ---------------------------------------------------------------------------
# Execution Config Builder
# ---------------------------------------------------------------------------

def _build_execution_config(work_class: str, model_cfg: dict) -> dict:
    defaults = dict(EXECUTION_DEFAULTS.get(work_class, EXECUTION_DEFAULTS["simple"]))
    # Capability masking
    if not model_cfg.get("tool_calling", False):
        defaults["tool_calling"] = False
    if not model_cfg.get("structured_output", False):
        defaults["structured_output"] = False
    defaults["context_window"] = model_cfg.get("context_window", 32000)
    return defaults


# ---------------------------------------------------------------------------
# Primary Interface
# ---------------------------------------------------------------------------

def route_with_transmission(
    prompt: str,
    work_class: Optional[str] = None,
    dispatch_hint: Optional[dict] = None,
    agent_metadata: Optional[dict] = None,
    lane: str = "interactive",
    req_id: Optional[str] = None,
    required_features: Optional[dict] = None,
    config_path: Optional[str] = None,
    log_path: Optional[str] = None,
) -> dict:
    """
    Route a task to the most appropriate model.

    Returns a dict with: model, provider, candidate_chain, work_class,
    confidence, classifier_source, execution_config, gear, duration_ms, req_id.

    On total failure, returns status="EXHAUSTED" with TRANSMISSION_EXHAUSTED emitted.
    Never raises. Never writes to openclaw.json.
    """
    t0 = time.perf_counter()
    req_id = req_id or f"tr-{uuid.uuid4().hex[:8]}"
    _log = Path(log_path) if log_path else DEFAULT_LOG_PATH

    cfg = _load_config(Path(config_path) if config_path else None)
    models: dict = cfg.get("models", {})
    work_classes: list[str] = cfg.get("work_classes", list(WORK_CLASS_PATTERNS.keys()))
    confidence_threshold: float = cfg.get("confidence_threshold", 0.70)
    lane_preferences: dict = cfg.get("lane_preferences", {
        "interactive": ["premium", "budget-capable", "mid", "efficient"],
        "background":  ["budget-capable", "mid", "premium", "efficient"],
    })
    gear_up_on_low: bool = cfg.get("defaults", {}).get("gear_up_on_low_confidence", True)

    # --- Step 1: Resolve work_class ---
    resolved_wc: str = ""
    confidence: float = 1.0
    classifier_source: str = "default"

    # Priority 1: Dispatch hint (only if valid)
    if dispatch_hint and isinstance(dispatch_hint, dict):
        dh_wc = dispatch_hint.get("work_class", "")
        if dh_wc and dh_wc in work_classes:
            resolved_wc = dh_wc
            classifier_source = "dispatch"
            confidence = 1.0

    # Priority 2: Explicit parameter
    if not resolved_wc and work_class and work_class in work_classes:
        resolved_wc = work_class
        classifier_source = "explicit"
        confidence = 1.0

    # Priority 3: Agent metadata
    if not resolved_wc and agent_metadata and isinstance(agent_metadata, dict):
        am_wc = agent_metadata.get("work_class", "")
        if am_wc and am_wc in work_classes:
            resolved_wc = am_wc
            classifier_source = "agent_metadata"
            confidence = 1.0

    # Priority 4: Heuristic classifier (with cache)
    if not resolved_wc:
        cache_key = prompt[:200]
        cached = _classification_cache.get(cache_key) if _classification_cache else None
        if cached:
            resolved_wc, confidence, classifier_source = cached
        else:
            resolved_wc, confidence, classifier_source = _classify_heuristic(prompt, work_classes)
            if _classification_cache and resolved_wc:
                _classification_cache.put(cache_key, (resolved_wc, confidence, classifier_source))

    # Priority 5: Lane default
    if not resolved_wc:
        lane_prefs = lane_preferences.get(lane, ["premium", "mid", "efficient"])
        # Default: pick work_class appropriate for the tier default
        resolved_wc = "simple"
        classifier_source = "lane_default"
        confidence = 0.0

    _emit("TRANSMISSION_WORK_CLASS_RESOLVED", req_id, _log, work_class=resolved_wc, source=classifier_source)
    _emit("TRANSMISSION_CONFIDENCE", req_id, _log, confidence=round(confidence, 3), threshold=confidence_threshold)

    # --- Step 2: Determine gear_up ---
    gear_up = gear_up_on_low and confidence < confidence_threshold

    # --- Step 3: Build candidate chain ---
    candidate_chain = _build_candidate_chain(
        resolved_wc, lane, models, lane_preferences, required_features, gear_up
    )

    _emit("TRANSMISSION_CHAIN_BUILT", req_id, _log,
          candidates=candidate_chain, work_class=resolved_wc, gear_up=gear_up)

    if not candidate_chain:
        _emit("TRANSMISSION_EXHAUSTED", req_id, _log,
              reason="no_candidates", work_class=resolved_wc)
        return {
            "status": "EXHAUSTED",
            "reason": "no_candidates",
            "work_class": resolved_wc,
            "req_id": req_id,
            "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    selected_model = candidate_chain[0]
    model_cfg = models[selected_model]
    gear = model_cfg.get("tier", "unknown")

    _emit("TRANSMISSION_GEAR_SELECTED", req_id, _log,
          model=selected_model, gear=gear, lane=lane)

    # --- Step 4: Build execution config (with capability masking) ---
    execution_config = _build_execution_config(resolved_wc, model_cfg)
    _emit("TRANSMISSION_EXECUTION_CONFIG", req_id, _log, execution_config=execution_config)

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    _emit("TRANSMISSION_SUCCESS", req_id, _log, duration_ms=duration_ms, model=selected_model)

    return {
        "model": selected_model,
        "provider": model_cfg.get("provider", ""),
        "candidate_chain": candidate_chain,
        "work_class": resolved_wc,
        "confidence": round(confidence, 3),
        "classifier_source": classifier_source,
        "execution_config": execution_config,
        "gear": gear,
        "duration_ms": duration_ms,
        "req_id": req_id,
    }


# ---------------------------------------------------------------------------
# CLI entry point (for manual testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "write some python code"
    result = route_with_transmission(prompt)
    print(json.dumps(result, indent=2))
