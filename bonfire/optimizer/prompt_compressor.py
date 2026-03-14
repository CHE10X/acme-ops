#!/usr/bin/env python3
"""Prompt optimization/compression heuristics for Bonfire v3."""

from __future__ import annotations

import hashlib
from collections import Counter


def _short_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:8]


def _dedupe_lines(prompt: str) -> tuple[str, list[str]]:
    seen = {}
    out = []
    rules = []
    for line in (prompt or "").splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            ref = _short_hash(key)[:6]
            out.append(f"[dedup:{ref}]")
            rules.append(f"dedupe_line:{ref}")
            continue
        seen[key] = 1
        if normalized.lower().startswith(("system:", "assistant:", "user:")):
            out.append(normalized)
        else:
            out.append(normalized)
    return "\n".join(out), rules


def _context_truncate(prompt: str, max_chars: int = 6000) -> tuple[str, list[str]]:
    if len(prompt) <= max_chars:
        return prompt, []
    hash_ref = _short_hash(prompt)[:8]
    head = prompt[: max_chars // 2].strip()
    tail = prompt[-(max_chars // 3):].strip()
    compressed = f"{head}\n[compressed:{hash_ref} context]\n{tail}"
    return compressed, [f"context_hash:{hash_ref}"]


def compress_prompt(prompt: str) -> dict:
    """Return a compressed prompt variant and metadata."""
    original = (prompt or "").strip()
    if not original:
        return {
            "prompt": "",
            "compressed": False,
            "original_chars": 0,
            "compressed_chars": 0,
            "compression_ratio": 1.0,
            "rules": [],
        }

    collapsed = "\n".join(part.strip() for part in original.splitlines())
    deduped, dedupe_rules = _dedupe_lines(collapsed)
    truncated, truncate_rules = _context_truncate(deduped)
    rules = list({*dedupe_rules, *truncate_rules})

    original_len = len(original)
    compressed_len = len(truncated)
    return {
        "prompt": truncated,
        "compressed": compressed_len < original_len,
        "original_chars": original_len,
        "compressed_chars": compressed_len,
        "compression_ratio": float(compressed_len) / max(1, original_len),
        "rules": rules,
    }


def prompt_optimization_recommendations() -> list[str]:
    """Static recommendations consumed by operator commands."""
    common = Counter(
        [
            "Move repeated system instructions to session setup.",
            "Trim unnecessary logs/trace payloads before tool calls.",
            "Use concise summaries after long context windows.",
            "Prefer explicit result schema and avoid verbose restatements.",
        ]
    )
    return [msg for msg, _ in common.most_common()]

