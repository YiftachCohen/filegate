"""Fact backends: answer narrow yes/no questions about a file, as probabilities.

Every backend implements `answer(file, kind) -> {fact_id: probability}` for the
facts configured under `facts.<kind>`. `risk()` folds the answers into one score.
"""
from __future__ import annotations


def get(cfg: dict):
    name = cfg["backend"]
    if name == "regex":
        from .regex import RegexFacts
        return RegexFacts(cfg)
    if name == "nano":
        from .nano import NanoFacts
        return NanoFacts(cfg)
    if name == "systemone":
        from .systemone import SystemOneFacts
        return SystemOneFacts(cfg)
    if name == "head":
        from ..head import HeadScorer
        return HeadScorer(cfg)
    raise ValueError(f"unknown backend {name!r} (regex | nano | systemone | head)")


def risk(answers: dict, kind_facts: dict) -> float:
    """Max over risk facts; `role: discount` facts (e.g. ui_only) scale the score down by up to half."""
    raise_ = [p for k, p in answers.items() if kind_facts.get(k, {}).get("role") != "discount"]
    score = max(raise_, default=0.0)
    for k, p in answers.items():
        if kind_facts.get(k, {}).get("role") == "discount":
            score *= 1 - 0.5 * p
    return score


def state(f: dict) -> str:
    return f"File path: {f['path']}\n\n{f.get('text', '')}"
